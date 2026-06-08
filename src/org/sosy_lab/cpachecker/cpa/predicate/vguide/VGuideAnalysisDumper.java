// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static org.sosy_lab.cpachecker.util.AbstractStates.extractLocation;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableMap;
import com.google.common.collect.ImmutableSet;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.logging.Level;
import org.checkerframework.checker.nullness.qual.Nullable;
import org.sosy_lab.common.log.LogManager;
import org.sosy_lab.cpachecker.core.CPAcheckerResult.Result;
import org.sosy_lab.cpachecker.core.interfaces.AbstractState;
import org.sosy_lab.cpachecker.core.interfaces.Precision;
import org.sosy_lab.cpachecker.cpa.arg.ARGReachedSet;
import org.sosy_lab.cpachecker.cpa.arg.ARGState;
import org.sosy_lab.cpachecker.cpa.predicate.BlockFormulaStrategy.BlockFormulas;
import org.sosy_lab.cpachecker.cpa.predicate.PredicatePrecision;
import org.sosy_lab.cpachecker.cfa.model.CFANode;
import org.sosy_lab.cpachecker.util.Precisions;
import org.sosy_lab.cpachecker.util.predicates.AbstractionPredicate;
import org.sosy_lab.cpachecker.util.predicates.interpolation.CounterexampleTraceInfo;
import org.sosy_lab.cpachecker.util.predicates.smt.FormulaManagerView;
import org.sosy_lab.java_smt.api.BooleanFormula;

/**
 * Writes per-task analysis dumps for predicate overlap / PCS studies. Enabled when {@code
 * VGUIDE_ANALYSIS_DUMP_DIR} is set. See docs/vguided-cegar/analysis/PREDICATE_ANALYSIS_PLAN.md.
 */
public final class VGuideAnalysisDumper {

  public static final String SCHEMA_VERSION = "1";
  private static final ObjectMapper JSON = new ObjectMapper();
  private static final AtomicBoolean MANIFEST_WRITTEN = new AtomicBoolean(false);

  private final LogManager logger;
  private final Path runRoot;
  private final Path taskRoot;
  private final String taskName;
  private final boolean dumpPrompts;
  private final FormulaManagerView fmgr;
  private final VGuideOptions options;

  private final Path refinementsFile;
  private final Path llmRoundsFile;
  private int apiCallIndex;
  private int predicateIdSeq;
  private int totalPromptTokens;
  private int totalCompletionTokens;
  private int llmRoundCount;
  private int llmApiCallCount;

  private VGuideAnalysisDumper(
      LogManager logger,
      Path runRoot,
      String taskName,
      boolean dumpPrompts,
      FormulaManagerView fmgr,
      VGuideOptions options) {
    this.logger = logger;
    this.runRoot = runRoot;
    this.taskName = taskName;
    this.dumpPrompts = dumpPrompts;
    this.fmgr = fmgr;
    this.options = options;
    this.taskRoot = runRoot.resolve("tasks").resolve(taskName);
    this.refinementsFile = taskRoot.resolve("refinements.jsonl");
    this.llmRoundsFile = taskRoot.resolve("llm_rounds.jsonl");
    try {
      Files.createDirectories(taskRoot.resolve("prompts"));
    } catch (IOException e) {
      throw new UncheckedIOException(e);
    }
    writeManifestOnce();
  }

  public static @Nullable VGuideAnalysisDumper createOptional(
      LogManager logger, String taskName, FormulaManagerView fmgr, VGuideOptions options) {
    String dir = System.getenv("VGUIDE_ANALYSIS_DUMP_DIR");
    if (dir == null || dir.isBlank()) {
      return null;
    }
    boolean dumpPrompts =
        !"0".equals(System.getenv("VGUIDE_ANALYSIS_DUMP_PROMPTS"))
            && !"false".equalsIgnoreCase(System.getenv("VGUIDE_ANALYSIS_DUMP_PROMPTS"));
    return new VGuideAnalysisDumper(
        logger, Path.of(dir), taskName, dumpPrompts, fmgr, options);
  }

  public void recordRefinement(
      int refinementIndex,
      boolean llmCalled,
      @Nullable String llmSkipReason,
      @Nullable Integer llmRoundIndex,
      @Nullable String traceSummaryInPrompt,
      ContextPack pack,
      List<ARGState> abstractionStatesTrace,
      BlockFormulas formulas,
      CounterexampleTraceInfo counterexample,
      @Nullable ARGReachedSet reachedBefore,
      @Nullable ARGReachedSet reachedAfter,
      @Nullable List<DumpValidatedPredicate> validatedPredicates,
      @Nullable List<DumpValidatedPredicate> injectedPredicates) {
    if (llmCalled && llmRoundIndex != null) {
      llmRoundCount = Math.max(llmRoundCount, llmRoundIndex);
    }
    ObjectNode row = JSON.createObjectNode();
    row.put("task", taskName);
    row.put("refinement_index", refinementIndex);
    row.put("llm_called", llmCalled);
    if (!llmCalled && llmSkipReason != null) {
      row.put("llm_skip_reason", llmSkipReason);
    }
    row.set("interpolants_pre", interpolantsJson(counterexample, abstractionStatesTrace));
    row.set("block_formulas", blockFormulasJson(formulas));
    row.set("var_contract", varContractJson(pack.varContract()));
    row.set("loop_heads", loopHeadsJson(pack.loopHeads()));
    row.set("abstraction_states", abstractionStatesJson(abstractionStatesTrace));
    row.set("precision_local_before", precisionLocalJson(reachedBefore));
    row.set("precision_global_before", precisionGlobalJson(reachedBefore));
    if (llmCalled) {
      if (llmRoundIndex != null) {
        row.put("llm_round_index", llmRoundIndex);
      }
      if (traceSummaryInPrompt != null) {
        row.put("trace_summary_in_prompt", traceSummaryInPrompt);
      }
      row.set(
          "validated_predicates",
          validatedPredicates == null ? JSON.createArrayNode() : validatedPredicatesJson(validatedPredicates));
      row.set(
          "precision_injected",
          injectedPredicates == null ? JSON.createArrayNode() : injectedPredicatesJson(injectedPredicates));
    }
    row.set("precision_local_after", precisionLocalJson(reachedAfter));
    appendJsonLine(refinementsFile, row);
  }

  public void recordLlmApiCall(
      int refinementIndex,
      int llmRoundIndex,
      String callKind,
      String promptKind,
      String prompt,
      ContextPack pack,
      LlmProposalResult api,
      List<String> rejectedPredicates) {
    apiCallIndex++;
    llmApiCallCount++;
    JsonNode usage = api.usage();
    if (usage != null && usage.isObject()) {
      totalPromptTokens += usage.path("prompt_tokens").asInt(0);
      totalCompletionTokens += usage.path("completion_tokens").asInt(0);
    }

    ObjectNode row = JSON.createObjectNode();
    row.put("task", taskName);
    row.put("refinement_index", refinementIndex);
    row.put("llm_round_index", llmRoundIndex);
    row.put("api_call_index", apiCallIndex);
    row.put("call_kind", callKind);
    row.put("prompt_kind", promptKind);
    row.put("latency_ms", api.latencyMs());
    row.put("prompt_chars", prompt.length());
    row.set("prompt_components", promptComponents(pack, promptKind));
    if (usage != null) {
      row.set("usage", usage);
    } else {
      row.putNull("usage");
    }
    row.put("response_raw", api.content());
    var parse = LlmResponseParser.parseWithRejects(api.content());
    row.put("response_parse_ok", !parse.accepted().isEmpty());
    row.set("predicates_raw", stringArray(parse.accepted()));
    row.set("predicates_rejected", stringArray(rejectedPredicates));
    row.put("schedule", options.getLlmCallSchedule().name());
    row.put("every_n", options.getLlmEveryNSpuriousRefinements());
    row.put("min_interval_sec", options.getLlmMinIntervalSec());

    if (dumpPrompts) {
      String promptFileName =
          String.format("r%03d_%s_%s.prompt.txt", refinementIndex, promptKind, callKind);
      Path promptPath = taskRoot.resolve("prompts").resolve(promptFileName);
      try {
        Files.writeString(promptPath, prompt, StandardCharsets.UTF_8);
      } catch (IOException e) {
        logger.logDebugException(e, "Failed to write prompt file");
      }
      row.put("prompt_path", "prompts/" + promptFileName);
    }
    appendJsonLine(llmRoundsFile, row);
  }

  private final AtomicBoolean taskFinished = new AtomicBoolean(false);

  public void finishTask(
      int refinementCount,
      Result result,
      double wallSeconds,
      VGuideOutcome outcome,
      @Nullable ARGReachedSet reached) {
    if (!taskFinished.compareAndSet(false, true)) {
      return;
    }
    ObjectNode summary = JSON.createObjectNode();
    summary.put("task", taskName);
    summary.put("verdict", resultToVerdict(result));
    summary.put("wall_s", wallSeconds);
    summary.put("refinements", refinementCount);
    summary.put("llm_rounds", llmRoundCount);
    summary.put("llm_api_calls", llmApiCallCount);
    summary.put("vguide_outcome", outcome.name());
    ObjectNode totalUsage = JSON.createObjectNode();
    totalUsage.put("prompt_tokens", totalPromptTokens);
    totalUsage.put("completion_tokens", totalCompletionTokens);
    totalUsage.put("total_tokens", totalPromptTokens + totalCompletionTokens);
    summary.set("total_usage", totalUsage);
    summary.set("precision_final", precisionSnapshot(reached));
    writeJson(taskRoot.resolve("task_summary.json"), summary);
    logger.log(Level.INFO, "VGuide analysis dump written to ", taskRoot);
  }

  /** One validated predicate row for refinements.jsonl. */
  public record DumpValidatedPredicate(
      int predicateId,
      String rawString,
      ValidatedPredicate validated,
      BooleanFormula blockFormula,
      boolean l1Ok,
      boolean l2Ok,
      boolean injected) {}

  private void writeManifestOnce() {
    if (!MANIFEST_WRITTEN.compareAndSet(false, true)) {
      return;
    }
    try {
      Files.createDirectories(runRoot);
      ObjectNode manifest = JSON.createObjectNode();
      manifest.put("schema_version", SCHEMA_VERSION);
      manifest.put("started_at", Instant.now().toString());
      manifest.put("run_id", runRoot.getFileName().toString());
      manifest.put("benchmark_set", System.getenv().getOrDefault("VGUIDE_ANALYSIS_BENCHMARK_SET", ""));
      manifest.put("model", System.getenv().getOrDefault("DEEPSEEK_MODEL", "deepseek-v4-pro"));
      manifest.put("timelimit_sec", System.getenv().getOrDefault("VGUIDE_ANALYSIS_TIMELIMIT_SEC", ""));
      manifest.put("git_commit", readGitCommit());
      manifest.put("dump_prompts", dumpPrompts);
      writeJson(runRoot.resolve("run_manifest.json"), manifest);
    } catch (IOException e) {
      logger.logDebugException(e, "Failed to write run_manifest.json");
    }
  }

  private static String readGitCommit() {
    try {
      Process p =
          new ProcessBuilder("git", "rev-parse", "HEAD")
              .directory(Path.of(".").toFile())
              .redirectErrorStream(true)
              .start();
      String out = new String(p.getInputStream().readAllBytes(), StandardCharsets.UTF_8).trim();
      return out.isEmpty() ? "unknown" : out;
    } catch (IOException e) {
      return "unknown";
    }
  }

  private ArrayNode interpolantsJson(
      CounterexampleTraceInfo counterexample, List<ARGState> abstractionStatesTrace) {
    ArrayNode arr = JSON.createArrayNode();
    if (!counterexample.isSpurious() || counterexample.getInterpolants() == null) {
      return arr;
    }
    List<BooleanFormula> itps = counterexample.getInterpolants();
    int n = Math.min(itps.size(), abstractionStatesTrace.size());
    for (int i = 0; i < n; i++) {
      ObjectNode o = JSON.createObjectNode();
      o.put("index", i);
      CFANode node = extractLocation(abstractionStatesTrace.get(i));
      if (node != null) {
        o.put("node", "N" + node.getNodeNumber());
      }
      o.put("smt", dumpFormula(itps.get(i)));
      arr.add(o);
    }
    return arr;
  }

  private ArrayNode blockFormulasJson(BlockFormulas formulas) {
    ArrayNode arr = JSON.createArrayNode();
    for (int i = 0; i < formulas.getSize(); i++) {
      ObjectNode o = JSON.createObjectNode();
      o.put("index", i);
      o.put("smt", dumpFormula(formulas.getFormulas().get(i)));
      arr.add(o);
    }
    return arr;
  }

  private ArrayNode abstractionStatesJson(List<ARGState> trace) {
    ArrayNode arr = JSON.createArrayNode();
    for (int i = 0; i < trace.size(); i++) {
      ObjectNode o = JSON.createObjectNode();
      o.put("index", i);
      CFANode node = extractLocation(trace.get(i));
      if (node != null) {
        o.put("node", "N" + node.getNodeNumber());
      }
      arr.add(o);
    }
    return arr;
  }

  private ObjectNode varContractJson(ImmutableMap<String, ImmutableSet<String>> contract) {
    ObjectNode o = JSON.createObjectNode();
    for (var e : contract.entrySet()) {
      o.set(e.getKey(), stringArray(new ArrayList<>(e.getValue())));
    }
    return o;
  }

  private ArrayNode loopHeadsJson(ImmutableList<LoopHeadInfo> heads) {
    ArrayNode arr = JSON.createArrayNode();
    for (LoopHeadInfo h : heads) {
      ObjectNode o = JSON.createObjectNode();
      o.put("label", h.label());
      o.put("node", h.label());
      o.put("function", h.functionName());
      arr.add(o);
    }
    return arr;
  }

  private ObjectNode precisionLocalJson(@Nullable ARGReachedSet reached) {
    ObjectNode local = JSON.createObjectNode();
    PredicatePrecision predPrec = extractPredicatePrecision(reached);
    if (predPrec == null) {
      return local;
    }
    for (var e : predPrec.getLocalPredicates().asMap().entrySet()) {
      String label = "N" + e.getKey().getNodeNumber();
      ArrayNode preds = JSON.createArrayNode();
      for (AbstractionPredicate ap : e.getValue()) {
        preds.add(dumpFormula(ap.getSymbolicAtom()));
      }
      local.set(label, preds);
    }
    return local;
  }

  private ArrayNode precisionGlobalJson(@Nullable ARGReachedSet reached) {
    ArrayNode arr = JSON.createArrayNode();
    PredicatePrecision predPrec = extractPredicatePrecision(reached);
    if (predPrec == null) {
      return arr;
    }
    for (AbstractionPredicate ap : predPrec.getGlobalPredicates()) {
      arr.add(dumpFormula(ap.getSymbolicAtom()));
    }
    return arr;
  }

  private ObjectNode precisionSnapshot(@Nullable ARGReachedSet reached) {
    ObjectNode snap = JSON.createObjectNode();
    snap.set("local", precisionLocalJson(reached));
    snap.set("global", precisionGlobalJson(reached));
    return snap;
  }

  private @Nullable PredicatePrecision extractPredicatePrecision(@Nullable ARGReachedSet reached) {
    if (reached == null) {
      return null;
    }
    AbstractState first = reached.asReachedSet().getFirstState();
    if (first == null) {
      return null;
    }
    Precision prec = reached.asReachedSet().getPrecision(first);
    return Precisions.extractPrecisionByType(prec, PredicatePrecision.class);
  }

  private ArrayNode validatedPredicatesJson(List<DumpValidatedPredicate> preds) {
    ArrayNode arr = JSON.createArrayNode();
    for (DumpValidatedPredicate p : preds) {
      arr.add(validatedPredicateJson(p));
    }
    return arr;
  }

  private ObjectNode validatedPredicateJson(DumpValidatedPredicate p) {
    ObjectNode o = JSON.createObjectNode();
    o.put("predicate_id", p.predicateId());
    o.put("raw_string", p.rawString());
    o.put("smt_dump", dumpFormula(p.validated().formula()));
    o.put("loop_head", "N" + p.validated().loopHeadNode().getNodeNumber());
    o.put("classification", p.validated().classification().name());
    o.put("l1_ok", p.l1Ok());
    o.put("l2_ok", p.l2Ok());
    o.put("injected", p.injected());
    o.put("block_formula_smt", dumpFormula(p.blockFormula()));
    return o;
  }

  private ArrayNode injectedPredicatesJson(List<DumpValidatedPredicate> preds) {
    ArrayNode arr = JSON.createArrayNode();
    for (DumpValidatedPredicate p : preds) {
      if (!p.injected()) {
        continue;
      }
      ObjectNode o = JSON.createObjectNode();
      o.put("predicate_id", p.predicateId());
      o.put("loop_head", "N" + p.validated().loopHeadNode().getNodeNumber());
      o.put("smt_dump", dumpFormula(p.validated().formula()));
      arr.add(o);
    }
    return arr;
  }

  private ObjectNode promptComponents(ContextPack pack, String promptKind) {
    ObjectNode o = JSON.createObjectNode();
    o.put("source", pack.sourceCode().length());
    o.put("contract", VarContractBuilder.formatForPrompt(pack.varContract()).length());
    o.put("loop_heads", formatLoopHeadsChars(pack.loopHeads()));
    o.put("rules", ProposalPromptBuilder.rulesCharCount(options.getPredicateBudget()));
    int traceChars = "later".equals(promptKind) || "repair".equals(promptKind) ? pack.traceSummary().length() : 0;
    o.put("trace", traceChars);
    return o;
  }

  private static int formatLoopHeadsChars(ImmutableList<LoopHeadInfo> heads) {
    if (heads.isEmpty()) {
      return "(no loop heads detected)\n".length();
    }
    int n = "LOOP HEADS (inject predicates here — use source variable names only):\n".length();
    for (LoopHeadInfo h : heads) {
      n += ("  " + h.label() + " (function " + h.functionName() + " loop head)\n").length();
    }
    return n;
  }

  public int nextPredicateId() {
    return ++predicateIdSeq;
  }

  private String dumpFormula(BooleanFormula f) {
    return fmgr.dumpFormula(f).toString().replace('\n', ' ');
  }

  private static ArrayNode stringArray(List<String> strings) {
    ArrayNode arr = JSON.createArrayNode();
    for (String s : strings) {
      arr.add(s);
    }
    return arr;
  }

  private static String resultToVerdict(Result result) {
    return switch (result) {
      case TRUE -> "TRUE";
      case FALSE -> "FALSE";
      default -> "UNKNOWN";
    };
  }

  private void appendJsonLine(Path file, ObjectNode row) {
    try {
      Files.writeString(file, JSON.writeValueAsString(row) + "\n", StandardCharsets.UTF_8,
          java.nio.file.StandardOpenOption.CREATE,
          java.nio.file.StandardOpenOption.APPEND);
    } catch (IOException e) {
      logger.logDebugException(e, "Failed to append analysis dump line to " + file);
    }
  }

  private void writeJson(Path file, ObjectNode node) {
    try {
      Files.createDirectories(file.getParent());
      Files.writeString(file, JSON.writerWithDefaultPrettyPrinter().writeValueAsString(node),
          StandardCharsets.UTF_8);
    } catch (IOException e) {
      logger.logDebugException(e, "Failed to write analysis dump " + file);
    }
  }
}
