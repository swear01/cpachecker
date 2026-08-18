// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.logging.Level;
import org.checkerframework.checker.nullness.qual.Nullable;
import org.sosy_lab.cpachecker.cpa.predicate.LlmApiUrl;
import org.sosy_lab.common.log.LogManager;

/**
 * DeepSeek chat API client for predicate proposals.
 *
 * <p>Configuration via environment: {@code DEEPSEEK_API_KEY}, {@code DEEPSEEK_MODEL},
 * {@code VGUIDE_LLM_THINKING} ({@code disabled}|{@code enabled}, default {@code disabled}),
 * {@code VGUIDE_LLM_REASONING_EFFORT} ({@code low}|{@code medium}|{@code high}|{@code max} when
 * thinking is enabled, default {@code high}), and the mutually exclusive paired-evaluation
 * directories {@code VGUIDE_LLM_RECORD_DIR} and {@code VGUIDE_LLM_REPLAY_DIR}.
 */
public final class PredicateProposalClient {

  private static final String DEFAULT_MODEL = "deepseek-v4-pro";
  private static final ObjectMapper JSON = new ObjectMapper();

  private final LogManager logger;
  private final URI apiUrl;
  private final String apiKey;
  private final String model;
  private final boolean thinkingEnabled;
  private final @Nullable String reasoningEffort;
  private final int maxCompletionTokens;
  private final int timeoutSeconds;
  private final int retryAttempts;
  private final int retryBackoffMs;
  private final HttpClient http;
  private final @Nullable LlmResponseCache responseCache;

  /** Returns a client when live API access or response replay is configured. */
  public static @Nullable PredicateProposalClient createOptional(LogManager pLogger) {
    return createOptional(pLogger, readPositiveIntEnv("VGUIDE_LLM_MAX_COMPLETION_TOKENS", 1024));
  }

  /** Returns a client when live API access or response replay is configured. */
  public static @Nullable PredicateProposalClient createOptional(
      LogManager pLogger, int pMaxCompletionTokens) {
    String key = System.getenv("DEEPSEEK_API_KEY");
    String replayDir = System.getenv("VGUIDE_LLM_REPLAY_DIR");
    if ((key == null || key.isBlank()) && (replayDir == null || replayDir.isBlank())) {
      return null;
    }
    return new PredicateProposalClient(pLogger, pMaxCompletionTokens);
  }

  public PredicateProposalClient(LogManager pLogger) {
    this(pLogger, readPositiveIntEnv("VGUIDE_LLM_MAX_COMPLETION_TOKENS", 1024));
  }

  public PredicateProposalClient(LogManager pLogger, int pMaxCompletionTokens) {
    logger = pLogger;
    responseCache = responseCacheFromEnvironment();
    apiUrl =
        responseCache != null && responseCache.mode() == LlmResponseCache.Mode.REPLAY
            ? URI.create(LlmApiUrl.DEFAULT_API_URL)
            : LlmApiUrl.validate(System.getenv("VGUIDE_LLM_API_URL"));
    String configuredApiKey = System.getenv("DEEPSEEK_API_KEY");
    apiKey = configuredApiKey == null ? "" : configuredApiKey;
    if (apiKey.isBlank()
        && (responseCache == null || responseCache.mode() != LlmResponseCache.Mode.REPLAY)) {
      throw new IllegalStateException("DEEPSEEK_API_KEY is required for VGuide LLM client");
    }
    String configuredModel = System.getenv("DEEPSEEK_MODEL");
    model = configuredModel == null || configuredModel.isBlank() ? DEFAULT_MODEL : configuredModel;
    logger.log(Level.INFO, "VGuide LLM model: ", model);
    thinkingEnabled = thinkingEnabledFromEnv();
    reasoningEffort = thinkingEnabled ? reasoningEffortFromEnv() : null;
    logger.log(
        Level.INFO,
        "VGuide LLM thinking: ",
        thinkingEnabled ? "enabled" : "disabled");
    if (thinkingEnabled && reasoningEffort != null) {
      logger.log(Level.INFO, "VGuide LLM reasoning_effort: ", reasoningEffort);
    }
    maxCompletionTokens = Math.max(256, pMaxCompletionTokens);
    logger.log(Level.INFO, "VGuide LLM max_completion_tokens: ", maxCompletionTokens);
    if (responseCache != null) {
      logger.log(Level.INFO, "VGuide LLM response mode: ", responseCache.mode().name());
    }
    timeoutSeconds = readPositiveIntEnv("VGUIDE_LLM_TIMEOUT_SEC", 120);
    retryAttempts = Math.max(0, readPositiveIntEnv("VGUIDE_LLM_RETRY_ATTEMPTS", 2));
    retryBackoffMs = Math.max(0, readPositiveIntEnv("VGUIDE_LLM_RETRY_BACKOFF_MS", 2000));
    http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(30)).build();
  }

  /** Call LLM with system + user messages; returns content and API {@code usage}. */
  public LlmProposalResult proposeWithUsage(PromptMessages messages)
      throws IOException, InterruptedException {
    long t0 = System.currentTimeMillis();
    String body = buildRequestBody(messages);
    LlmResponseCache.Request cachedRequest =
        responseCache == null ? null : responseCache.nextRequest(body);
    if (responseCache != null && responseCache.mode() == LlmResponseCache.Mode.REPLAY) {
      try {
        return responseCache.replay(Objects.requireNonNull(cachedRequest));
      } catch (IOException e) {
        throw new IllegalStateException("LLM response replay failed without live fallback", e);
      }
    }
    HttpRequest req =
        HttpRequest.newBuilder()
            .uri(apiUrl)
            .header("Authorization", "Bearer " + apiKey)
            .header("Content-Type", "application/json")
            .timeout(Duration.ofSeconds(timeoutSeconds))
            .POST(HttpRequest.BodyPublishers.ofString(body, StandardCharsets.UTF_8))
            .build();
    HttpResponse<String> resp = sendWithRetries(req);
    if (resp.statusCode() != 200) {
      throw new IOException("DeepSeek API " + resp.statusCode() + ": " + resp.body());
    }
    JsonNode root = JSON.readTree(resp.body());
    JsonNode content = root.at("/choices/0/message/content");
    if (!content.isTextual()) {
      throw new IOException("No text content in LLM response");
    }
    JsonNode usage = root.path("usage");
    long latency = System.currentTimeMillis() - t0;
    logger.log(Level.FINE, "VGuide LLM response length: ", content.asText().length());
    if (usage.isObject() && usage.has("prompt_tokens")) {
      logger.log(
          Level.FINE,
          "VGuide LLM usage prompt_tokens=",
          usage.path("prompt_tokens").asInt(),
          " completion_tokens=",
          usage.path("completion_tokens").asInt());
    }
    LlmProposalResult result =
        new LlmProposalResult(
            content.asText(),
            usage.isMissingNode() ? null : usage,
            latency,
            t0,
            cachedRequest == null ? requestHash(body) : cachedRequest.requestHash(),
            responseCache == null ? "live" : "live_recorded");
    if (responseCache != null) {
      try {
        responseCache.record(Objects.requireNonNull(cachedRequest), result);
      } catch (IOException e) {
        throw new IllegalStateException("LLM response recording failed", e);
      }
    }
    return result;
  }

  /** Legacy: single user message (no system). */
  public LlmProposalResult proposeWithUsage(String userPrompt)
      throws IOException, InterruptedException {
    return proposeWithUsage(new PromptMessages("", userPrompt));
  }

  public String propose(String userPrompt) throws IOException, InterruptedException {
    return proposeWithUsage(userPrompt).content();
  }

  public String propose(PromptMessages messages) throws IOException, InterruptedException {
    return proposeWithUsage(messages).content();
  }

  /**
   * Extra ensemble draws with the same prompt (after one synchronous cache-seeding call). Uses up
   * to {@code parallelism} concurrent HTTP requests.
   */
  public List<LlmProposalResult> proposeParallelExtrasWithUsage(
      PromptMessages messages, int extraDraws, int parallelism)
      throws IOException, InterruptedException {
    if (extraDraws <= 0) {
      return List.of();
    }
    int pool = Math.max(1, Math.min(extraDraws, parallelism));
    ExecutorService executor = Executors.newFixedThreadPool(pool);
    try {
      List<Future<LlmProposalResult>> futures = new ArrayList<>(extraDraws);
      for (int i = 0; i < extraDraws; i++) {
        futures.add(executor.submit(() -> proposeWithUsage(messages)));
      }
      List<LlmProposalResult> results = new ArrayList<>(extraDraws);
      for (Future<LlmProposalResult> future : futures) {
        try {
          results.add(future.get());
        } catch (ExecutionException e) {
          Throwable cause = e.getCause();
          if (cause instanceof IOException io) {
            throw io;
          }
          if (cause instanceof InterruptedException ie) {
            throw ie;
          }
          throw new IOException("Ensemble LLM draw failed", cause);
        }
      }
      return results;
    } finally {
      executor.shutdownNow();
    }
  }

  public List<LlmProposalResult> proposeParallelExtrasWithUsage(
      String userPrompt, int extraDraws, int parallelism)
      throws IOException, InterruptedException {
    return proposeParallelExtrasWithUsage(new PromptMessages("", userPrompt), extraDraws, parallelism);
  }

  public List<String> proposeParallelExtras(String userPrompt, int extraDraws, int parallelism)
      throws IOException, InterruptedException {
    List<LlmProposalResult> results = proposeParallelExtrasWithUsage(userPrompt, extraDraws, parallelism);
    List<String> texts = new ArrayList<>(results.size());
    for (LlmProposalResult r : results) {
      texts.add(r.content());
    }
    return texts;
  }

  /**
   * Sends the request with retries on transient failures (network errors and 5xx /
   * 429 responses): 2 retries with short backoff, per the DeepSeek best-practices
   * retry pattern. Non-transient client errors (4xx other than 429) are not retried.
   */
  private HttpResponse<String> sendWithRetries(HttpRequest req)
      throws IOException, InterruptedException {
    IOException lastIo = null;
    HttpResponse<String> resp = null;
    int attempts = retryAttempts + 1;
    for (int attempt = 1; attempt <= attempts; attempt++) {
      resp = null;
      try {
        resp = http.send(req, HttpResponse.BodyHandlers.ofString());
        if (resp.statusCode() == 429 || resp.statusCode() >= 500) {
          if (attempt < attempts) {
            Thread.sleep(retryBackoffMs * (long) attempt);
            continue;
          }
          break;
        }
        return resp;
      } catch (IOException e) {
        lastIo = e;
        if (attempt < attempts) {
          Thread.sleep(retryBackoffMs * (long) attempt);
        }
      }
    }
    if (resp != null && (resp.statusCode() == 429 || resp.statusCode() >= 500)) {
      throw new IOException("DeepSeek API " + resp.statusCode() + ": " + resp.body());
    }
    throw Objects.requireNonNull(lastIo);
  }

  private String buildRequestBody(PromptMessages prompt) throws IOException {
    var root = JSON.createObjectNode();
    root.put("model", model);
    root.put("temperature", 0);
    root.put("max_completion_tokens", maxCompletionTokens);
    root.putObject("response_format").put("type", "json_object");
    var messages = root.putArray("messages");
    if (!prompt.system().isEmpty()) {
      messages.addObject().put("role", "system").put("content", prompt.system());
    }
    messages.addObject().put("role", "user").put("content", prompt.user());
    var thinking = root.putObject("thinking");
    if (thinkingEnabled) {
      thinking.put("type", "enabled");
      if (reasoningEffort != null) {
        root.put("reasoning_effort", reasoningEffort);
      }
    } else {
      thinking.put("type", "disabled");
    }
    return JSON.writeValueAsString(root);
  }

  private static boolean thinkingEnabledFromEnv() {
    String mode = System.getenv("VGUIDE_LLM_THINKING");
    if (mode == null || mode.isBlank()) {
      return false;
    }
    return switch (mode.toLowerCase(Locale.ROOT)) {
      case "enabled", "true", "on", "1" -> true;
      case "disabled", "false", "off", "0" -> false;
      default -> false;
    };
  }

  /**
   * DeepSeek V4 official API accepts {@code low}/{@code medium}/{@code high}/{@code max}
   * natively (verified 2026-08-15: reasoning lengths 221/625/270/396 chars); pass all
   * through. Default stays {@code high}.
   */
  private static @Nullable String reasoningEffortFromEnv() {
    String effort = System.getenv("VGUIDE_LLM_REASONING_EFFORT");
    if (effort == null || effort.isBlank() || "default".equalsIgnoreCase(effort)) {
      return "high";
    }
    return switch (effort.toLowerCase(Locale.ROOT)) {
      case "low" -> "low";
      case "medium" -> "medium";
      case "high" -> "high";
      case "max", "xhigh" -> "max";
      default -> "high";
    };
  }

  private static int readPositiveIntEnv(String name, int defaultValue) {
    String v = System.getenv(name);
    if (v == null || v.isBlank()) {
      return defaultValue;
    }
    try {
      return Integer.parseInt(v);
    } catch (NumberFormatException e) {
      return defaultValue;
    }
  }

  private static @Nullable LlmResponseCache responseCacheFromEnvironment() {
    String recordDir = System.getenv("VGUIDE_LLM_RECORD_DIR");
    String replayDir = System.getenv("VGUIDE_LLM_REPLAY_DIR");
    boolean record = recordDir != null && !recordDir.isBlank();
    boolean replay = replayDir != null && !replayDir.isBlank();
    if (record && replay) {
      throw new IllegalStateException(
          "VGUIDE_LLM_RECORD_DIR and VGUIDE_LLM_REPLAY_DIR are mutually exclusive");
    }
    String namespace = System.getenv().getOrDefault("VGUIDE_LLM_CACHE_NAMESPACE", "default");
    if (record) {
      return LlmResponseCache.forRecording(Path.of(recordDir), namespace);
    }
    if (replay) {
      return LlmResponseCache.forReplay(
          Path.of(replayDir), namespace, readBooleanEnv("VGUIDE_LLM_REPLAY_PRESERVE_LATENCY", true));
    }
    return null;
  }

  private static boolean readBooleanEnv(String name, boolean defaultValue) {
    String value = System.getenv(name);
    if (value == null || value.isBlank()) {
      return defaultValue;
    }
    return switch (value.toLowerCase(Locale.ROOT)) {
      case "1", "true", "on", "yes" -> true;
      case "0", "false", "off", "no" -> false;
      default -> throw new IllegalStateException("Invalid boolean environment variable " + name);
    };
  }

  private static String requestHash(String requestBody) {
    return com.google.common.hash.Hashing.sha256()
        .hashString(requestBody, StandardCharsets.UTF_8)
        .toString();
  }

}
