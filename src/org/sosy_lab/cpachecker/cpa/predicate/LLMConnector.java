// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-FileCopyrightText: 2007-2020 Dirk Beyer <https://www.sosy-lab.org>
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate;

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
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Level;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.checkerframework.checker.nullness.qual.Nullable;
import org.sosy_lab.common.ShutdownNotifier;
import org.sosy_lab.common.log.LogManager;
import org.sosy_lab.cpachecker.cfa.CFA;
import org.sosy_lab.cpachecker.util.predicates.smt.BooleanFormulaManagerView;
import org.sosy_lab.cpachecker.util.predicates.smt.FormulaManagerView;
import org.sosy_lab.cpachecker.util.predicates.smt.IntegerFormulaManagerView;
import org.sosy_lab.cpachecker.util.predicates.smt.Solver;
import org.sosy_lab.java_smt.api.BooleanFormula;
import org.sosy_lab.java_smt.api.NumeralFormula.IntegerFormula;

/**
 * Async LLM connector for maintaining the dynamic predicate vocabulary V via OpenRouter API.
 *
 * <p>Runs a daemon thread that periodically sends accumulated spurious traces to the LLM for
 * vocabulary updates. Initial V_0 is generated from static analysis of the source code. CE-guided
 * updates are triggered when CEGAR's scoring is consistently poor.
 */
public class LLMConnector {

  private static final String API_URL = "https://openrouter.ai/api/v1/chat/completions";
  private static final String MODEL = "deepseek/deepseek-v4-pro";
  private static final Pattern PREDICATE_PATTERN = Pattern.compile("\"([^\"]+)\"");
  private static final long MAX_INTERVAL_MS = 300_000L;
  private static final int TRACE_BATCH_SIZE = 10;
  private static final int SHORTFALL_THRESHOLD = 3;

  private final VocabularyGuide vg;
  private final FormulaManagerView fmgr;
  private final BooleanFormulaManagerView bfmgr;
  private final IntegerFormulaManagerView ifmgr;
  private final LogManager logger;
  private final ShutdownNotifier sd;
  private final CFA cfa;
  private final String apiKey;
  private final HttpClient http;

  private final AtomicBoolean initialized = new AtomicBoolean(false);
  private final AtomicBoolean running = new AtomicBoolean(false);
  private final List<String> pendingTraces = Collections.synchronizedList(new ArrayList<>());
  private final AtomicInteger shortfallCount = new AtomicInteger(0);

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
    fmgr = pSolver.getFormulaManager();
    bfmgr = fmgr.getBooleanFormulaManager();
    ifmgr = fmgr.getIntegerFormulaManager();
    logger = pLogger;
    sd = pSd;
    cfa = pCfa;
    apiKey = pApiKey;
    http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(30)).build();
  }

  public void initializeVocab() {
    if (!initialized.compareAndSet(false, true)) {
      return;
    }
    logger.log(Level.INFO, "LLM: initializing V_0 from source code");
    try {
      StringBuilder code = new StringBuilder();
      for (Path f : cfa.getFileNames()) {
        code.append(Files.readString(f)).append("\n");
      }
      String prompt = buildInitPrompt(code.toString());
      String response = callLLM(prompt);
      List<BooleanFormula> preds = parsePredicates(response);
      if (!preds.isEmpty()) {
        vg.addPredicates(preds);
        logger.log(Level.INFO, "LLM: V_0 initialized with", preds.size(), "predicates");
      }
    } catch (Exception e) {
      logger.logUserException(Level.WARNING, e, "LLM V_0 initialization failed");
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
                  long elapsed = System.currentTimeMillis() - lastCallTime;
                  long waitMs = Math.max(0, currentIntervalMs - elapsed);
                  if (waitMs > 0) {
                    Thread.sleep(Math.min(waitMs, 5000));
                  }
                  if (sd.shouldShutdown()) {
                    break;
                  }
                  backgroundUpdate();
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
      triggerCEUpdate();
    }
  }

  public void onGoodScore() {
    shortfallCount.set(0);
  }

  // ---- LLM API ----

  private String callLLM(String prompt) throws IOException, InterruptedException {
    String body =
        "{\"model\":\""
            + MODEL
            + "\",\"messages\":[{\"role\":\"user\",\"content\":"
            + jsonEscape(prompt)
            + "}],\"max_tokens\":1024}";

    HttpRequest req =
        HttpRequest.newBuilder()
            .uri(URI.create(API_URL))
            .header("Authorization", "Bearer " + apiKey)
            .header("Content-Type", "application/json")
            .timeout(Duration.ofSeconds(60))
            .POST(HttpRequest.BodyPublishers.ofString(body))
            .build();

    HttpResponse<String> resp = http.send(req, HttpResponse.BodyHandlers.ofString());
    if (resp.statusCode() != 200) {
      throw new IOException("LLM API error: " + resp.statusCode());
    }
    String r = resp.body();
    int ci = r.indexOf("\"content\":\"");
    if (ci < 0) {
      throw new IOException("No content in LLM response");
    }
    int start = r.indexOf('"', ci + 11) + 1;
    StringBuilder content = new StringBuilder();
    for (int i = start; i < r.length(); i++) {
      char c = r.charAt(i);
      if (c == '\\' && i + 1 < r.length()) {
        content.append(r.charAt(++i));
      } else if (c == '"') {
        break;
      } else {
        content.append(c);
      }
    }
    return content.toString().replace("\\n", "\n").replace("\\t", "\t");
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

  // ---- Prompts ----

  private String buildInitPrompt(String sourceCode) {
    return "You are a software verification expert analyzing a C program.\n"
        + "Given the source code below, generate a set of meaningful predicates\n"
        + "that would be useful for verifying this program.\n"
        + "Focus on loop invariants, bounds checks, null checks, and\n"
        + "arithmetic relationships between variables.\n"
        + "Output ONLY a JSON array of predicate strings, like:\n"
        + "[\"i >= 0\", \"i < n\", \"ptr != NULL\", \"sum == i * (i + 1) / 2\"]\n"
        + "Source code:\n"
        + sourceCode;
  }

  private String buildUpdatePrompt(
      String sourceCode, String traces, String vocabJson, String statsJson) {
    return "You are a software verification expert. The system is using an LLM-maintained\n"
        + "predicate vocabulary V to guide interpolation strategy selection in CEGAR.\n"
        + "Current V: "
        + vocabJson
        + "\n"
        + "Usage stats: "
        + statsJson
        + "\n"
        + "New spurious traces (SMT formulas): "
        + traces
        + "\n"
        + "Analyze the traces and the current V. Output ONLY a JSON object:\n"
        + "{\"add\": [\"new predicate1\", \"new predicate2\"], \"remove\": [\"obsolete predicate\"]}\n"
        + "Add predicates that capture higher-level semantics (loop invariants, variable bounds,\n"
        + "pointer safety, arithmetic relationships) visible in the traces.\n"
        + "Remove predicates that are clearly obsolete or subsumed.\n"
        + "Source code for context:\n"
        + sourceCode;
  }

  private String buildCEPrompt(String sourceCode, String traces, String vocabJson) {
    return "You are a software verification expert. CEGAR is stuck - the current predicate\n"
        + "vocabulary V is scoring poorly on a new spurious trace.\n"
        + "Current V: "
        + vocabJson
        + "\n"
        + "Current problematic trace (SMT formulas): "
        + traces
        + "\n"
        + "Generate additional predicates specifically targeting the semantics of this trace.\n"
        + "Output ONLY: {\"add\": [\"p1\", \"p2\", ...]}\n"
        + "Source code:\n"
        + sourceCode;
  }

  // ---- Predicate parsing ----

  private List<BooleanFormula> parsePredicates(String llmOutput) {
    List<BooleanFormula> result = new ArrayList<>();
    try {
      String cleaned = llmOutput.trim();
      if (cleaned.contains("```")) {
        cleaned = cleaned.replaceAll("```(?:json)?\\s*", " ").replace("```", " ").trim();
      }
      Matcher m = PREDICATE_PATTERN.matcher(cleaned);
      while (m.find()) {
        String pred = m.group(1);
        if ("add".equals(pred) || "remove".equals(pred)) {
          continue;
        }
        BooleanFormula f = parseExpression(pred);
        if (f != null) {
          result.add(f);
        }
      }
    } catch (Exception e) {
      logger.logDebugException(e, "Failed to parse LLM predicate output");
    }
    return result;
  }

  private @Nullable BooleanFormula parseExpression(String expr) {
    expr = expr.strip();
    try {
      String[] parts;
      String op;
      if (expr.contains(" >= ")) {
        parts = expr.split(" >= ");
        op = ">=";
      } else if (expr.contains(" <= ")) {
        parts = expr.split(" <= ");
        op = "<=";
      } else if (expr.contains(" != ")) {
        parts = expr.split(" != ");
        op = "!=";
      } else if (expr.contains(" == ")) {
        parts = expr.split(" == ");
        op = "==";
      } else if (expr.contains(" < ")) {
        parts = expr.split(" < ");
        op = "<";
      } else if (expr.contains(" > ")) {
        parts = expr.split(" > ");
        op = ">";
      } else {
        return null;
      }
      if (parts.length != 2) {
        return null;
      }
      String left = parts[0].strip();
      String right = parts[1].strip();
      if ("NULL".equals(right)) {
        return bfmgr.not(ifmgr.equal(ifmgr.makeVariable(left), ifmgr.makeNumber(0)));
      }
      IntegerFormula lv = ifmgr.makeVariable(left);
      try {
        long rv = Long.parseLong(right);
        IntegerFormula rvf = ifmgr.makeNumber(rv);
        return switch (op) {
          case ">=" -> bfmgr.not(ifmgr.lessThan(lv, rvf));
          case "<=" -> bfmgr.not(ifmgr.greaterThan(lv, rvf));
          case "!=" -> bfmgr.not(ifmgr.equal(lv, rvf));
          case "==" -> ifmgr.equal(lv, rvf);
          case "<" -> ifmgr.lessThan(lv, rvf);
          case ">" -> ifmgr.greaterThan(lv, rvf);
          default -> null;
        };
      } catch (NumberFormatException e2) {
        IntegerFormula rv2 = ifmgr.makeVariable(right);
        return switch (op) {
          case ">=" -> bfmgr.not(ifmgr.lessThan(lv, rv2));
          case "<=" -> bfmgr.not(ifmgr.greaterThan(lv, rv2));
          case "!=" -> bfmgr.not(ifmgr.equal(lv, rv2));
          case "==" -> ifmgr.equal(lv, rv2);
          case "<" -> ifmgr.lessThan(lv, rv2);
          case ">" -> ifmgr.greaterThan(lv, rv2);
          default -> null;
        };
      }
    } catch (Exception e) {
      logger.logDebugException(e, "Failed to parse expression: " + expr);
      return null;
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
    String vocabJson = vg.getAllPredicates().stream().map(Object::toString).toList().toString();
    String tracesStr = String.join("\n", traces);
    String statsStr = vg.getUsageStats().toString();

    String prompt = buildUpdatePrompt(source, tracesStr, vocabJson, statsStr);
    try {
      String response = callLLM(prompt);
      List<BooleanFormula> newPreds = parsePredicates(response);
      if (!newPreds.isEmpty()) {
        vg.addPredicates(newPreds);
        currentIntervalMs = Math.min(MAX_INTERVAL_MS, (long) (currentIntervalMs * 1.5));
        logger.log(
            Level.FINE,
            "LLM: bg update, V size=",
            vg.size(),
            ", interval=",
            currentIntervalMs / 1000,
            "s");
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
      String vocabJson = vg.getAllPredicates().stream().map(Object::toString).toList().toString();
      String tracesStr = String.join("\n", traces.isEmpty() ? List.of("(no traces)") : traces);

      String prompt = buildCEPrompt(source, tracesStr, vocabJson);
      String response = callLLM(prompt);
      List<BooleanFormula> newPreds = parsePredicates(response);
      if (!newPreds.isEmpty()) {
        vg.addPredicates(newPreds);
        logger.log(Level.INFO, "LLM: CE-guided update added", newPreds.size(), "predicates");
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
