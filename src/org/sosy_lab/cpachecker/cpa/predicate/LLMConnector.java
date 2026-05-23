// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-FileCopyrightText: 2007-2020 Dirk Beyer <https://www.sosy-lab.org>
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Level;
import org.checkerframework.checker.nullness.qual.Nullable;
import org.sosy_lab.common.ShutdownNotifier;
import org.sosy_lab.common.log.LogManager;
import org.sosy_lab.cpachecker.cfa.CFA;
import org.sosy_lab.cpachecker.cfa.model.CFANode;
import org.sosy_lab.cpachecker.cfa.model.FunctionEntryNode;
import org.sosy_lab.cpachecker.util.LoopStructure;
import org.sosy_lab.cpachecker.util.predicates.smt.Solver;

/**
 * Async LLM connector for maintaining the dynamic predicate vocabulary V via OpenRouter API.
 *
 * <p>Runs a daemon thread that periodically sends accumulated spurious traces to the LLM for
 * vocabulary updates. Initial V_0 is generated from static analysis of the source code. CE-guided
 * updates are triggered when CEGAR's scoring is consistently poor.
 */
public class LLMConnector {

  private static final String API_URL = "https://openrouter.ai/api/v1/chat/completions";
  private static final String DEFAULT_MODEL = "deepseek/deepseek-v4-pro";
  private static final int DEFAULT_REQUEST_TIMEOUT_SECONDS = 600;
  private static final ObjectMapper JSON_MAPPER = new ObjectMapper();
  private static final long MAX_INTERVAL_MS = 300_000L;
  private static final int TRACE_BATCH_SIZE = 10;
  private static final int SHORTFALL_THRESHOLD = 3;

  private enum RequestKind {
    INITIAL,
    CE_GUIDED
  }

  private final VocabularyGuide vg;
  private final LogManager logger;
  private final ShutdownNotifier sd;
  private final CFA cfa;
  private final String apiKey;
  private final String model;
  private final int completionTokens;
  private final int reasoningTokens;
  private final int requestTimeoutSeconds;
  private final HttpClient http;

  private final AtomicBoolean initialized = new AtomicBoolean(false);
  private final AtomicBoolean running = new AtomicBoolean(false);
  private final List<String> pendingTraces = Collections.synchronizedList(new ArrayList<>());
  private final BlockingQueue<RequestKind> requestQueue = new LinkedBlockingQueue<>();
  private final AtomicInteger shortfallCount = new AtomicInteger(0);
  private final CountDownLatch initialVocabDone = new CountDownLatch(1);

  private long currentIntervalMs = 10_000L;
  private long lastCallTime = 0L;

  public LLMConnector(
      VocabularyGuide pVg,
      Solver pSolver,
      LogManager pLogger,
      ShutdownNotifier pSd,
      CFA pCfa,
      String pApiKey) {
    vg = pVg;
    logger = pLogger;
    sd = pSd;
    cfa = pCfa;
    apiKey = pApiKey;
    String configuredModel = System.getenv("OPENROUTER_MODEL");
    model = configuredModel == null || configuredModel.isBlank() ? DEFAULT_MODEL : configuredModel;
    completionTokens = readOptionalPositiveIntEnv("OPENROUTER_MAX_COMPLETION_TOKENS");
    reasoningTokens = readOptionalPositiveIntEnv("OPENROUTER_REASONING_TOKENS");
    requestTimeoutSeconds =
        readPositiveIntEnv("OPENROUTER_TIMEOUT_SECONDS", DEFAULT_REQUEST_TIMEOUT_SECONDS);
    http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(30)).build();
  }

  public void requestInitialVocab() {
    if (initialized.compareAndSet(false, true)) {
      requestQueue.offer(RequestKind.INITIAL);
    }
  }

  public boolean requestInitialVocabAndWait(long timeout, TimeUnit unit) throws InterruptedException {
    requestInitialVocab();
    boolean finished = initialVocabDone.await(timeout, unit);
    if (!finished) {
      logger.log(
          Level.WARNING, "LLM V_0 initialization did not finish within ", timeout, " ", unit);
      return false;
    }
    return !vg.isEmpty();
  }

  public void initializeVocabBlocking() {
    logger.log(Level.INFO, "LLM: initializing V_0 from source code");
    try {
      StringBuilder code = new StringBuilder();
      for (Path f : cfa.getFileNames()) {
        code.append(Files.readString(f)).append("\n");
      }
      String prompt = buildInitPrompt(code.toString());
      String response = callLLM(prompt);
      Map<String, List<String>> locPreds = parseLocationPredicates(response);
      int total = 0;
      for (var entry : locPreds.entrySet()) {
        vg.addPredicates(entry.getKey(), entry.getValue());
        total += entry.getValue().size();
      }
      if (total > 0) {
        logger.log(Level.INFO, "LLM: V_0 initialized with", total, "predicates across",
            locPreds.size(), "locations");
        for (var entry : locPreds.entrySet()) {
          logger.log(Level.INFO, "  [", entry.getKey(), "] -> ", entry.getValue());
        }
      } else {
        logger.log(Level.WARNING, "LLM V_0 initialization produced no predicates");
      }
    } catch (Exception e) {
      logger.logUserException(Level.WARNING, e, "LLM V_0 initialization failed");
    } finally {
      initialVocabDone.countDown();
    }
  }

  public void start() {
    if (!running.compareAndSet(false, true)) {
      return;
    }
    Thread.ofPlatform()
        .daemon()
        .name("LLMConnector")
        .start(
            () -> {
              lastCallTime = System.currentTimeMillis();
              while (!sd.shouldShutdown() && running.get()) {
                try {
                  RequestKind request = requestQueue.poll(currentIntervalMs, TimeUnit.MILLISECONDS);
                  if (sd.shouldShutdown()) {
                    break;
                  }
                  if (request == RequestKind.INITIAL) {
                    initializeVocabBlocking();
                  } else if (request == RequestKind.CE_GUIDED) {
                    triggerCEUpdate();
                  } else {
                    backgroundUpdate();
                  }
                } catch (InterruptedException e) {
                  break;
                } catch (Exception e) {
                  logger.logDebugException(e, "LLM background error");
                }
              }
            });
  }

  public void stop() {
    running.set(false);
  }

  public void addTrace(String smtFormula) {
    pendingTraces.add(smtFormula);
  }

  public void onShortfall() {
    int c = shortfallCount.incrementAndGet();
    if (c >= SHORTFALL_THRESHOLD) {
      shortfallCount.set(0);
      requestQueue.offer(RequestKind.CE_GUIDED);
    }
  }

  public void onGoodScore() {
    shortfallCount.set(0);
  }

  // ---- LLM API ----

  private String callLLM(String prompt) throws IOException, InterruptedException {
    StringBuilder body =
        new StringBuilder()
            .append("{\"model\":\"")
            .append(model)
            .append("\",\"messages\":[{\"role\":\"user\",\"content\":")
            .append(jsonEscape(prompt))
            .append("}],\"temperature\":0");
    if (completionTokens > 0) {
      body.append(",\"max_completion_tokens\":").append(completionTokens);
    }
    if (reasoningTokens > 0) {
      body.append(",\"reasoning\":{\"max_tokens\":")
          .append(reasoningTokens)
          .append(",\"exclude\":true}");
    }
    body.append("}");

    HttpRequest req =
        HttpRequest.newBuilder()
            .uri(URI.create(API_URL))
            .header("Authorization", "Bearer " + apiKey)
            .header("Content-Type", "application/json")
            .timeout(Duration.ofSeconds(requestTimeoutSeconds))
            .POST(HttpRequest.BodyPublishers.ofString(body.toString()))
            .build();

    HttpResponse<String> resp = http.send(req, HttpResponse.BodyHandlers.ofString());
    if (resp.statusCode() != 200) {
      throw new IOException("LLM API error: " + resp.statusCode() + " " + resp.body());
    }
    JsonNode root = JSON_MAPPER.readTree(resp.body());
    JsonNode content = root.at("/choices/0/message/content");
    if (content.isMissingNode() || !content.isTextual()) {
      throw new IOException("No textual content in LLM response: " + resp.body());
    }
    return content.asText();
  }

  private static String jsonEscape(String s) {
    StringBuilder sb = new StringBuilder("\"");
    for (int i = 0; i < s.length(); i++) {
      char c = s.charAt(i);
      switch (c) {
        case '"' -> sb.append("\\\"");
        case '\\' -> sb.append("\\\\");
        case '\n' -> sb.append("\\n");
        case '\r' -> sb.append("\\r");
        case '\t' -> sb.append("\\t");
        default -> sb.append(c);
      }
    }
    return sb.append('"').toString();
  }

  private static int readPositiveIntEnv(String name, int fallback) {
    String value = System.getenv(name);
    if (value == null || value.isBlank()) {
      return fallback;
    }
    try {
      int parsed = Integer.parseInt(value);
      return parsed > 0 ? parsed : fallback;
    } catch (NumberFormatException e) {
      return fallback;
    }
  }

  private static int readOptionalPositiveIntEnv(String name) {
    String value = System.getenv(name);
    if (value == null || value.isBlank()) {
      return 0;
    }
    try {
      int parsed = Integer.parseInt(value);
      return parsed > 0 ? parsed : 0;
    } catch (NumberFormatException e) {
      return 0;
    }
  }

  // ---- Prompts ----

  private String buildAbaNodeList() {
    StringBuilder sb = new StringBuilder("Program verification points (use EXACTLY these labels):\n");

    for (FunctionEntryNode fn : cfa.getAllFunctions().values()) {
      sb.append("  N").append(fn.getNodeNumber())
        .append(" (function ").append(fn.getFunctionName()).append(" entry)\n");
    }

    Optional<LoopStructure> ls = cfa.getLoopStructure();
    if (ls.isPresent()) {
      for (LoopStructure.Loop loop : ls.orElseThrow().getAllLoops()) {
        for (CFANode head : loop.getLoopHeads()) {
          sb.append("  N").append(head.getNodeNumber())
            .append(" (function ").append(head.getFunctionName())
            .append(" loop head)\n");
        }
      }
    }
    return sb.toString();
  }

  private String buildInitPrompt(String sourceCode) {
    return "You are a software verification expert analyzing a C program.\n"
        + "Below are the program's verification points (use EXACTLY these labels\n"
        + "like \"N18\" as JSON keys). Generate meaningful SMT-LIB2 predicates for each\n"
        + "point you are confident about. Skip points you are unsure about.\n"
        + "Output ONLY a JSON object. Use SMT-LIB2 prefix notation.\n"
        + "Format:\n"
        + "{\"N18\": [\"(>= x 0)\", \"(< i n)\"], \"N12\": [\"(= x 0)\"]}\n"
        + "\n"
        + buildAbaNodeList()
        + "\n"
        + "Source code:\n"
        + sourceCode;
  }

  private String buildUpdatePrompt(
      String sourceCode, String traces, String vocabJson) {
    return "You are a software verification expert. CEGAR is using an LLM vocabulary V\n"
        + "for predicate injection during refinement.\n"
        + "Current V (location → predicates): " + vocabJson + "\n"
        + "New spurious traces that V predicates were too weak to handle: " + traces + "\n"
        + "Generate additional per-location predicates to strengthen V.\n"
        + "Output ONLY a JSON object: {\"location\": [\"pred1\", ...], ...}\n"
        + "Add predicates that capture semantics visible in the traces.\n"
        + "Source code:\n"
        + sourceCode;
  }

  private String buildCEPrompt(String sourceCode, String traces, String vocabJson) {
    return "You are a software verification expert. CEGAR is stuck on a counterexample\n"
        + "that the current vocabulary V cannot handle.\n"
        + "Current V (location → predicates): " + vocabJson + "\n"
        + "Problematic trace (SMT formulas): " + traces + "\n"
        + "Generate targeted per-location predicates to rule out this trace.\n"
        + "Output ONLY: {\"location\": [\"p1\", \"p2\", ...], ...}\n"
        + "Source code:\n"
        + sourceCode;
  }

  // ---- Predicate parsing ----

  static Map<String, List<String>> parseLocationPredicates(String llmOutput) {
    if (llmOutput == null || llmOutput.isBlank()) {
      return Map.of();
    }
    try {
      String cleaned = llmOutput.trim();
      if (cleaned.contains("```")) {
        cleaned = cleaned.replaceAll("```(?:json)?\\s*", " ").replace("```", " ").trim();
      }
      JsonNode root = JSON_MAPPER.readTree(cleaned);
      if (!root.isObject()) {
        return Map.of();
      }
      Map<String, List<String>> result = new LinkedHashMap<>();
      var fields = root.fields();
      while (fields.hasNext()) {
        var field = fields.next();
        String locationKey = field.getKey().strip();
        JsonNode predicatesNode = field.getValue();
        if (!predicatesNode.isArray()) {
          continue;
        }
        List<String> preds = new ArrayList<>();
        for (JsonNode p : predicatesNode) {
          if (p.isTextual()) {
            String text = p.asText().strip();
            if (!text.isEmpty()) {
              preds.add(text);
            }
          }
        }
        if (!preds.isEmpty()) {
          result.put(locationKey, preds);
        }
      }
      return result;
    } catch (Exception e) {
      return Map.of();
    }
  }

  private String buildVocabJson() {
    Map<String, List<String>> map = new LinkedHashMap<>();
    for (String loc : vg.getAllLocations()) {
      map.put(loc, vg.getPredicateStringsForLocation(loc));
    }
    try {
      return JSON_MAPPER.writeValueAsString(map);
    } catch (Exception e) {
      return "{}";
    }
  }

  // ---- Background & CE-guided updates ----

  private void backgroundUpdate() {
    if (pendingTraces.size() < TRACE_BATCH_SIZE) {
      return;
    }
    List<String> traces;
    synchronized (pendingTraces) {
      traces = new ArrayList<>(pendingTraces);
      pendingTraces.clear();
    }
    String source = readSource();
    String vocabJson = buildVocabJson();
    String tracesStr = String.join("\n", traces);

    String prompt = buildUpdatePrompt(source, tracesStr, vocabJson);
    try {
      String response = callLLM(prompt);
      Map<String, List<String>> locPreds = parseLocationPredicates(response);
      int total = 0;
      for (var entry : locPreds.entrySet()) {
        vg.addPredicates(entry.getKey(), entry.getValue());
        total += entry.getValue().size();
      }
      if (total > 0) {
        currentIntervalMs = Math.min(MAX_INTERVAL_MS, (long) (currentIntervalMs * 1.5));
        logger.log(
            Level.FINE,
            "LLM: bg update, added", total, "predicates to", locPreds.size(),
            "locations, V size=", vg.size());
      }
    } catch (Exception e) {
      logger.logDebugException(e, "LLM background update failed");
    }
    lastCallTime = System.currentTimeMillis();
  }

  private void triggerCEUpdate() {
    try {
      List<String> traces;
      synchronized (pendingTraces) {
        traces = new ArrayList<>(pendingTraces);
      }
      String source = readSource();
      String vocabJson = buildVocabJson();
      String tracesStr = String.join("\n", traces.isEmpty() ? List.of("(no traces)") : traces);

      String prompt = buildCEPrompt(source, tracesStr, vocabJson);
      String response = callLLM(prompt);
      Map<String, List<String>> locPreds = parseLocationPredicates(response);
      int total = 0;
      for (var entry : locPreds.entrySet()) {
        vg.addPredicates(entry.getKey(), entry.getValue());
        total += entry.getValue().size();
      }
      if (total > 0) {
        logger.log(Level.INFO, "LLM: CE-guided update added", total, "predicates across",
            locPreds.size(), "locations");
      }
    } catch (Exception e) {
      logger.logDebugException(e, "LLM CE-guided update error");
    }
    lastCallTime = System.currentTimeMillis();
  }

  private String readSource() {
    try {
      StringBuilder sb = new StringBuilder();
      for (Path f : cfa.getFileNames()) {
        sb.append("// File: ").append(f.getFileName()).append("\n");
        sb.append(Files.readString(f)).append("\n");
      }
      return sb.toString();
    } catch (IOException e) {
      return "// source unavailable";
    }
  }
}
