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
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.logging.Level;
import org.checkerframework.checker.nullness.qual.Nullable;
import org.sosy_lab.common.log.LogManager;

/**
 * DeepSeek chat API client for predicate proposals. Replaces Python bootstrap/b5 scripts and legacy
 * {@link org.sosy_lab.cpachecker.cpa.predicate.LLMConnector} HTTP calls.
 *
 * <p>Configuration via environment: {@code DEEPSEEK_API_KEY}, {@code DEEPSEEK_MODEL},
 * {@code VGUIDE_LLM_REASONING_EFFORT} (low|medium|high|default).
 */
public final class PredicateProposalClient {

  private static final String API_URL = "https://api.deepseek.com/chat/completions";
  private static final String DEFAULT_MODEL = "deepseek-v4-pro";
  private static final ObjectMapper JSON = new ObjectMapper();

  private final LogManager logger;
  private final String apiKey;
  private final String model;
  private final int reasoningTokens;
  private final int timeoutSeconds;
  private final HttpClient http;

  /** Returns a client when {@code DEEPSEEK_API_KEY} is set; otherwise {@code null}. */
  public static @Nullable PredicateProposalClient createOptional(LogManager pLogger) {
    String key = System.getenv("DEEPSEEK_API_KEY");
    if (key == null || key.isBlank()) {
      return null;
    }
    return new PredicateProposalClient(pLogger);
  }

  public PredicateProposalClient(LogManager pLogger) {
    logger = pLogger;
    apiKey = System.getenv("DEEPSEEK_API_KEY");
    if (apiKey == null || apiKey.isBlank()) {
      throw new IllegalStateException("DEEPSEEK_API_KEY is required for VGuide LLM client");
    }
    String configuredModel = System.getenv("DEEPSEEK_MODEL");
    model = configuredModel == null || configuredModel.isBlank() ? DEFAULT_MODEL : configuredModel;
    logger.log(Level.INFO, "VGuide LLM model: ", model);
    reasoningTokens = reasoningTokensFromEnv();
    timeoutSeconds = readPositiveIntEnv("VGUIDE_LLM_TIMEOUT_SEC", 120);
    http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(30)).build();
  }

  /**
   * Call LLM with the given user prompt; returns raw message content (expected JSON predicate map).
   */
  public String propose(String userPrompt) throws IOException, InterruptedException {
    String body = buildRequestBody(userPrompt);
    HttpRequest req =
        HttpRequest.newBuilder()
            .uri(URI.create(API_URL))
            .header("Authorization", "Bearer " + apiKey)
            .header("Content-Type", "application/json")
            .timeout(Duration.ofSeconds(timeoutSeconds))
            .POST(HttpRequest.BodyPublishers.ofString(body, StandardCharsets.UTF_8))
            .build();
    HttpResponse<String> resp = http.send(req, HttpResponse.BodyHandlers.ofString());
    if (resp.statusCode() != 200) {
      throw new IOException("DeepSeek API " + resp.statusCode() + ": " + resp.body());
    }
    JsonNode root = JSON.readTree(resp.body());
    JsonNode content = root.at("/choices/0/message/content");
    if (!content.isTextual()) {
      throw new IOException("No text content in LLM response");
    }
    logger.log(Level.FINE, "VGuide LLM response length: ", content.asText().length());
    return content.asText();
  }

  /**
   * Extra ensemble draws with the same prompt (after one synchronous cache-seeding call). Uses up
   * to {@code parallelism} concurrent HTTP requests.
   */
  public List<String> proposeParallelExtras(String userPrompt, int extraDraws, int parallelism)
      throws IOException, InterruptedException {
    if (extraDraws <= 0) {
      return List.of();
    }
    int pool = Math.max(1, Math.min(extraDraws, parallelism));
    ExecutorService executor = Executors.newFixedThreadPool(pool);
    try {
      List<Future<String>> futures = new ArrayList<>(extraDraws);
      for (int i = 0; i < extraDraws; i++) {
        futures.add(executor.submit(() -> propose(userPrompt)));
      }
      List<String> results = new ArrayList<>(extraDraws);
      for (Future<String> future : futures) {
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

  private String buildRequestBody(String userPrompt) throws IOException {
    var root = JSON.createObjectNode();
    root.put("model", model);
    root.put("temperature", 0);
    root.put("max_completion_tokens", 1024);
    var messages = root.putArray("messages");
    messages.addObject().put("role", "user").put("content", userPrompt);
    if (reasoningTokens > 0) {
      var reasoning = root.putObject("reasoning");
      reasoning.put("max_tokens", reasoningTokens);
      reasoning.put("exclude", true);
    }
    return JSON.writeValueAsString(root);
  }

  private static int reasoningTokensFromEnv() {
    String effort = System.getenv("VGUIDE_LLM_REASONING_EFFORT");
    if (effort == null || effort.isBlank() || "default".equalsIgnoreCase(effort)) {
      return 0;
    }
    return switch (effort.toLowerCase(Locale.ROOT)) {
      case "low" -> 0;
      case "medium" -> 1024;
      case "high" -> 4096;
      default -> 0;
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
}
