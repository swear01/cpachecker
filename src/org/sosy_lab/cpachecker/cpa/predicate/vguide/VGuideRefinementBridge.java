// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static org.sosy_lab.cpachecker.util.AbstractStates.extractLocation;

import com.google.common.collect.ImmutableList;
import java.io.IOException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Level;
import org.checkerframework.checker.nullness.qual.Nullable;
import org.sosy_lab.common.configuration.Configuration;
import org.sosy_lab.common.configuration.InvalidConfigurationException;
import org.sosy_lab.common.log.LogManager;
import org.sosy_lab.cpachecker.cfa.CFA;
import org.sosy_lab.cpachecker.cfa.model.CFANode;
import org.sosy_lab.cpachecker.core.CPAcheckerResult.Result;
import org.sosy_lab.cpachecker.core.interfaces.AbstractState;
import org.sosy_lab.cpachecker.cpa.arg.ARGReachedSet;
import org.sosy_lab.cpachecker.cpa.arg.ARGState;
import org.sosy_lab.cpachecker.cpa.predicate.BlockFormulaStrategy.BlockFormulas;
import org.sosy_lab.cpachecker.cpa.predicate.PredicateAbstractionManager;
import org.sosy_lab.cpachecker.cpa.predicate.VocabularyGuide;
import org.sosy_lab.cpachecker.util.LoopStructure;
import org.sosy_lab.cpachecker.util.predicates.interpolation.CounterexampleTraceInfo;
import org.sosy_lab.cpachecker.util.predicates.smt.FormulaManagerView;
import org.sosy_lab.cpachecker.util.predicates.smt.Solver;
import org.sosy_lab.java_smt.api.BooleanFormula;
import org.sosy_lab.java_smt.api.BooleanFormulaManager;

/** Unified VGuide orchestration: first-spurious LLM, validation, injection, NO_SPURIOUS frozen. */
public final class VGuideRefinementBridge {

  private final LogManager logger;
  private final VGuideOptions options;
  private final PredicateProposalClient llmClient;
  private final ContextPackBuilder contextPackBuilder;
  private final ProposalPromptBuilder promptBuilder;
  private final PredicateBudgetResolver budgetResolver;
  private final PredicateValidationPipeline validationPipeline;
  private final LoopHeadPrecisionInjector precisionInjector;
  private final FrozenPredicateLoader frozenLoader;
  private final LoopHeadIndex loopHeadIndex;
  private final WallClockBudget wallBudget;
  private final LlmCallScheduler llmScheduler;
  private final CFA cfa;
  private final FormulaManagerView fmgr;
  private final @Nullable VGuideAnalysisDumper analysisDumper;
  private final long analysisStartMs;
  private final AtomicBoolean analysisEndFinished = new AtomicBoolean(false);
  private final @Nullable Thread shutdownHook;

  private volatile int trackedRefinementCount;
  private volatile @Nullable ARGReachedSet trackedReached;

  private @Nullable ValidationResult lastValidation;
  private @Nullable PendingRefinementDump pendingDump;
  private VGuideOutcome outcome = VGuideOutcome.NO_SPURIOUS_GIVE_UP;

  private static final AtomicInteger BRIDGE_SEQUENCE = new AtomicInteger();

  private static final class PendingRefinementDump {
  int refinementIndex;
  boolean llmCalled;
  @Nullable String llmSkipReason;
  @Nullable Integer llmRoundIndex;
  @Nullable String ceSummaryInPrompt;
  ContextPack pack;
  List<ARGState> trace;
  BlockFormulas formulas;
  CounterexampleTraceInfo counterexample;
  ARGReachedSet reachedBefore;
  List<VGuideAnalysisDumper.DumpValidatedPredicate> validated = List.of();
  }

  public static VGuideRefinementBridge create(
      Configuration config,
      LogManager logger,
      CFA cfa,
      Optional<LoopStructure> loopStructure,
      Solver solver,
      @Nullable PredicateAbstractionManager predAbsManager)
      throws InvalidConfigurationException {
    VGuideOptions opts = new VGuideOptions(config);
    if (!opts.isEnable()) {
      return null;
    }
    FormulaManagerView fmgr = solver.getFormulaManager();
    LoopHeadIndex loopHeads = new LoopHeadIndex(loopStructure);
    String taskNameBase = benchmarkBaseName(cfa);
    int bridgeIndex = BRIDGE_SEQUENCE.getAndIncrement();
    String taskName = bridgeIndex == 0 ? taskNameBase : taskNameBase + "__b" + bridgeIndex;
    return new VGuideRefinementBridge(
        logger,
        opts,
        new PredicateProposalClient(logger, opts.getLlmMaxCompletionTokens()),
        cfa,
        fmgr,
        loopHeads,
        new ContextPackBuilder(cfa, loopHeads, fmgr),
        new ProposalPromptBuilder(loopHeads),
        new PredicateBudgetResolver(),
        new PredicateValidationPipeline(logger, solver, fmgr, opts.isEnableL3Entailment()),
        new LoopHeadPrecisionInjector(logger, predAbsManager),
        new FrozenPredicateLoader(logger, opts.getFrozenDir()),
        new WallClockBudget(opts.getWallBudgetSec()),
        new LlmCallScheduler(opts, logger),
        VGuideAnalysisDumper.createOptional(
            logger, taskName, taskNameBase, bridgeIndex, fmgr, opts));
  }

  private VGuideRefinementBridge(
      LogManager logger,
      VGuideOptions options,
      @Nullable PredicateProposalClient llmClient,
      CFA cfa,
      FormulaManagerView fmgr,
      LoopHeadIndex loopHeadIndex,
      ContextPackBuilder contextPackBuilder,
      ProposalPromptBuilder promptBuilder,
      PredicateBudgetResolver budgetResolver,
      PredicateValidationPipeline validationPipeline,
      LoopHeadPrecisionInjector precisionInjector,
      FrozenPredicateLoader frozenLoader,
      WallClockBudget wallBudget,
      LlmCallScheduler llmScheduler,
      @Nullable VGuideAnalysisDumper analysisDumper) {
    this.logger = logger;
    this.options = options;
    this.llmClient = llmClient;
    this.cfa = cfa;
    this.fmgr = fmgr;
    this.loopHeadIndex = loopHeadIndex;
    this.contextPackBuilder = contextPackBuilder;
    this.promptBuilder = promptBuilder;
    this.budgetResolver = budgetResolver;
    this.validationPipeline = validationPipeline;
    this.precisionInjector = precisionInjector;
    this.frozenLoader = frozenLoader;
    this.wallBudget = wallBudget;
    this.llmScheduler = llmScheduler;
    this.analysisDumper = analysisDumper;
    this.analysisStartMs = System.currentTimeMillis();
    if (analysisDumper != null) {
      shutdownHook = new Thread(this::finishDumpOnShutdown, "vguide-analysis-dump-finish");
      Runtime.getRuntime().addShutdownHook(shutdownHook);
    } else {
      shutdownHook = null;
    }
  }

  /** Updated after each refinement attempt so a shutdown hook can write partial dumps. */
  public void trackAnalysisProgress(int refinementCount, @Nullable ARGReachedSet reached) {
    trackedRefinementCount = refinementCount;
    if (reached != null) {
      trackedReached = reached;
    }
  }

  private void finishDumpOnShutdown() {
    if (analysisDumper == null || analysisEndFinished.get()) {
      return;
    }
    logger.log(Level.INFO, "VGuide analysis dump: finishing task on JVM shutdown (hang/timeout?)");
    onAnalysisEnd(trackedRefinementCount, Result.UNKNOWN, trackedReached);
  }

  /**
   * Called after spurious CE check, before {@code strategy.performRefinement}. May strengthen
   * interpolants (ENTAILED) and schedule precision injection.
   */
  public CounterexampleTraceInfo onSpuriousBeforeRefinement(
      int refinementIndex,
      List<ARGState> abstractionStatesTrace,
      BlockFormulas formulas,
      CounterexampleTraceInfo counterexample,
      ARGReachedSet reachedBefore)
      throws InterruptedException {
    lastValidation = null;
    pendingDump = null;

    ContextPack pack =
        contextPackBuilder.build(refinementIndex, formulas, counterexample, abstractionStatesTrace);
    PendingRefinementDump dump = new PendingRefinementDump();
    dump.refinementIndex = refinementIndex;
    dump.pack = pack;
    dump.trace = abstractionStatesTrace;
    dump.formulas = formulas;
    dump.counterexample = counterexample;
    dump.reachedBefore = reachedBefore;
    dump.llmCalled = false;
    pendingDump = dump;

    if (!counterexample.isSpurious()
        || counterexample.getInterpolants() == null
        || counterexample.getInterpolants().isEmpty()) {
      dump.llmSkipReason = "no_interpolants";
      return counterexample;
    }

    if (!llmScheduler.shouldCall(refinementIndex)) {
      dump.llmSkipReason = llmScheduler.skipReason(refinementIndex);
      return counterexample;
    }
    if (!wallBudget.hasRemainingForLlm()) {
      dump.llmSkipReason = "wall_budget";
      logger.log(Level.INFO, "VGuide: wall budget exhausted; skipping LLM");
      return counterexample;
    }

    BudgetResolution budgetRes = resolveBudget(pack, refinementIndex);
    PredicateBudget budget = budgetRes.budget();
    logger.log(
        Level.INFO,
        "VGuide predicate budget tier=",
        budgetRes.tier(),
        " S=",
        budgetRes.complexityScore(),
        " min=",
        budget.minPerCall(),
        " max=",
        budget.maxPerCall());

    dump.ceSummaryInPrompt = pack.ceSummary();
    String promptKindBase = refinementIndex == 1 ? "first" : "later";
    long t0 = System.currentTimeMillis();
    try {
      int samplesPerProfile = options.getLlmSamplesForRefinement(refinementIndex);
      List<String> rejectedAll = new ArrayList<>();
      List<LlmProposalResult> apiResults = new ArrayList<>();
      ImmutableList<AttributedRawPredicate> attributedMerged = ImmutableList.of();
      boolean safeAccepted = false;
      boolean bugAccepted = false;

      if (options.isDualPromptMode()) {
        ProfileInvokeResult safe =
            invokeProfileLlm(
                refinementIndex,
                llmScheduler.getLlmCallsDone() + 1,
                promptKindBase,
                PromptProfile.SAFE,
                pack,
                budget,
                budgetRes,
                samplesPerProfile,
                rejectedAll);
        apiResults.addAll(safe.apiResults());
        safeAccepted = safe.hasAccepted();
        ProfileInvokeResult bug =
            invokeProfileLlm(
                refinementIndex,
                llmScheduler.getLlmCallsDone() + 1,
                promptKindBase,
                PromptProfile.BUG_HUNT,
                pack,
                budget,
                budgetRes,
                samplesPerProfile,
                rejectedAll);
        apiResults.addAll(bug.apiResults());
        bugAccepted = bug.hasAccepted();
        attributedMerged =
            LlmEnsembleMerger.mergeDualUnion(
                LlmEnsembleMerger.attributeAll(safe.mergedRaw(), PromptProfile.SAFE),
                LlmEnsembleMerger.attributeAll(bug.mergedRaw(), PromptProfile.BUG_HUNT));
      } else {
        ProfileInvokeResult safe =
            invokeProfileLlm(
                refinementIndex,
                llmScheduler.getLlmCallsDone() + 1,
                promptKindBase,
                PromptProfile.SAFE,
                pack,
                budget,
                budgetRes,
                samplesPerProfile,
                rejectedAll);
        apiResults.addAll(safe.apiResults());
        safeAccepted = safe.hasAccepted();
        attributedMerged = LlmEnsembleMerger.attributeAll(safe.mergedRaw(), PromptProfile.SAFE);
      }

      long latency = System.currentTimeMillis() - t0;
      wallBudget.recordLlmCall(latency);
      llmScheduler.recordCallCompleted();
      dump.llmCalled = true;
      dump.llmRoundIndex = llmScheduler.getLlmCallsDone();
      if (refinementIndex == 1) {
        outcome = VGuideOutcome.FIRST_SPURIOUS_LLM;
      }
      logger.log(
          Level.INFO,
          "VGuide LLM round #",
          llmScheduler.getLlmCallsDone(),
          " spurious #",
          refinementIndex,
          " dual=",
          options.isDualPromptMode(),
          " samples_per_profile=",
          samplesPerProfile,
          " api=",
          apiResults.size(),
          " schedule=",
          options.getLlmCallSchedule(),
          " prompt=",
          promptKindBase,
          " latencyMs=",
          latency);

      List<String> rawPreds = new ArrayList<>();
      for (AttributedRawPredicate a : attributedMerged) {
        rawPreds.add(a.raw());
      }
      Map<String, String> profileByRaw = profileMap(attributedMerged);

      if (rawPreds.isEmpty() && !safeAccepted && !bugAccepted) {
        List<String> rejectedForRepair = new ArrayList<>();
        for (LlmProposalResult r : apiResults) {
          rejectedForRepair.addAll(LlmResponseParser.parseWithRejects(r.content()).rejected());
        }
        rejectedForRepair = rejectedForRepair.stream().distinct().limit(5).toList();
        if (!rejectedForRepair.isEmpty()) {
          PromptProfile repairProfile =
              options.isDualPromptMode() ? PromptProfile.BUG_HUNT : PromptProfile.SAFE;
          PromptMessages repairMessages =
              promptBuilder.buildRepair(
                  pack, rejectedForRepair, budget, repairProfile, refinementIndex);
          logger.log(Level.INFO, "VGuide: both profiles empty; one repair LLM call");
          LlmProposalResult repair = llmClient.proposeWithUsage(repairMessages);
          if (analysisDumper != null) {
            analysisDumper.recordLlmApiCall(
                refinementIndex,
                dump.llmRoundIndex,
                repairProfile.callKindPrefix() + "_repair",
                promptKindBase + "_repair_" + repairProfile.promptKindSuffix(),
                repairMessages.fullText(),
                pack,
                repairProfile,
                repair,
                rejectedForRepair,
                budgetRes);
          }
          ImmutableList<String> repairPreds = LlmResponseParser.parsePredicates(repair.content());
          if (!repairPreds.isEmpty()) {
            attributedMerged = LlmEnsembleMerger.attributeAll(repairPreds, repairProfile);
            rawPreds = repairPreds;
            profileByRaw = profileMap(attributedMerged);
            apiResults.add(repair);
          }
        }
      }

      lastValidation =
          validationPipeline.validate(pack, rawPreds, abstractionStatesTrace);
      dump.validated =
          buildValidatedDump(pack, rawPreds, lastValidation, abstractionStatesTrace, profileByRaw);
      if (options.isAllowInterpolantStrengthen() && options.isEnableL3Entailment()) {
        return strengthenInterpolants(
            counterexample, abstractionStatesTrace, lastValidation.entailed());
      }
    } catch (InterruptedException e) {
      throw e;
    } catch (IOException e) {
      dump.llmSkipReason = "llm_failed";
      logger.logUserException(Level.WARNING, e, "VGuide LLM call failed");
    }
    return counterexample;
  }

  /** Called after {@code strategy.performRefinement} to inject PRECISION_ONLY predicates. */
  public void onSpuriousAfterRefinement(int refinementIndex, ARGReachedSet reached) {
    if (pendingDump != null && pendingDump.refinementIndex == refinementIndex) {
      List<VGuideAnalysisDumper.DumpValidatedPredicate> injected = List.of();
      if (lastValidation != null) {
        ImmutableList<ValidatedPredicate> toInject = lastValidation.precisionOnly();
        injected = markInjected(pendingDump.validated, toInject);
        precisionInjector.inject(reached, toInject);
      }
      if (analysisDumper != null) {
        analysisDumper.recordRefinement(
            refinementIndex,
            pendingDump.llmCalled,
            pendingDump.llmSkipReason,
            pendingDump.llmRoundIndex,
            pendingDump.ceSummaryInPrompt,
            pendingDump.pack,
            pendingDump.trace,
            pendingDump.formulas,
            pendingDump.counterexample,
            pendingDump.reachedBefore,
            reached,
            pendingDump.llmCalled ? injected : null,
            pendingDump.llmCalled ? injected : null);
      }
      pendingDump = null;
    } else if (lastValidation != null) {
      precisionInjector.inject(reached, lastValidation.precisionOnly());
    }
    lastValidation = null;
  }

  /** Called at analysis end to finalize dumps and handle NO_SPURIOUS frozen seed path. */
  public void onAnalysisEnd(int refinementCount, Result result, @Nullable ARGReachedSet reached) {
    if (refinementCount == 0 && reached != null) {
      String benchmark = benchmarkBaseName();
      Optional<ImmutableList<String>> frozen = frozenLoader.loadForBenchmark(benchmark);
      if (frozen.isPresent()) {
        precisionInjector.injectFrozen(
            reached, loopHeadIndex.getLoopHeads(), frozen.orElseThrow(), fmgr);
        outcome = VGuideOutcome.FROZEN_SEED_EXCEPTION;
        logger.log(Level.INFO, "VGuide outcome: FROZEN_SEED_EXCEPTION for ", benchmark);
      } else {
        outcome = VGuideOutcome.NO_SPURIOUS_GIVE_UP;
        logger.log(Level.INFO, "VGuide outcome: NO_SPURIOUS_GIVE_UP for ", benchmark);
      }
    }
    if (analysisDumper != null && analysisEndFinished.compareAndSet(false, true)) {
      double wallS = (System.currentTimeMillis() - analysisStartMs) / 1000.0;
      analysisDumper.finishTask(refinementCount, result, wallS, outcome, reached);
      removeShutdownHook();
    }
  }

  public VGuideOutcome getOutcome() {
    return outcome;
  }

  private void removeShutdownHook() {
    if (shutdownHook == null) {
      return;
    }
    try {
      Runtime.getRuntime().removeShutdownHook(shutdownHook);
    } catch (IllegalStateException e) {
      // JVM shutdown is already in progress; hooks cannot be removed at this point.
    }
  }

  private BudgetResolution resolveBudget(ContextPack pack, int refinementIndex) {
    if (options.isEnableAdaptivePredicateBudget()) {
      return budgetResolver.resolve(pack, refinementIndex);
    }
    return new BudgetResolution(options.getPredicateBudget(), "fixed", -1);
  }

  private record ProfileInvokeResult(
      List<LlmProposalResult> apiResults,
      ImmutableList<String> mergedRaw,
      boolean hasAccepted) {}

  private ProfileInvokeResult invokeProfileLlm(
      int refinementIndex,
      int llmRoundIndex,
      String promptKindBase,
      PromptProfile profile,
      ContextPack pack,
      PredicateBudget budget,
      BudgetResolution budgetRes,
      int samplesConfigured,
      List<String> rejectedOut)
      throws IOException, InterruptedException {
    PromptMessages messages =
        promptBuilder.buildPrompt(pack, budget, profile, refinementIndex);
    String promptKind = promptKindBase + "_" + profile.promptKindSuffix();
    List<LlmProposalResult> results = new ArrayList<>();
    LlmProposalResult primary = llmClient.proposeWithUsage(messages);
    results.add(primary);
    List<String> primaryRejected = LlmResponseParser.parseWithRejects(primary.content()).rejected();
    rejectedOut.addAll(primaryRejected);
    if (analysisDumper != null) {
      analysisDumper.recordLlmApiCall(
          refinementIndex,
          llmRoundIndex,
          profile.callKindPrefix() + "_primary",
          promptKind,
          messages.fullText(),
          pack,
          profile,
          primary,
          primaryRejected,
          budgetRes);
    }
    int extra = samplesConfigured - 1;
    if (extra > 0) {
      List<LlmProposalResult> extras =
          llmClient.proposeParallelExtrasWithUsage(
              messages, extra, options.getLlmSampleParallelism());
      for (LlmProposalResult extraResult : extras) {
        List<String> rejected = LlmResponseParser.parseWithRejects(extraResult.content()).rejected();
        rejectedOut.addAll(rejected);
        if (analysisDumper != null) {
          analysisDumper.recordLlmApiCall(
              refinementIndex,
              llmRoundIndex,
              profile.callKindPrefix() + "_ensemble_extra",
              promptKind,
              messages.fullText(),
              pack,
              profile,
              extraResult,
              rejected,
              budgetRes);
        }
        results.add(extraResult);
      }
    }
    List<String> rawResponses = new ArrayList<>();
    for (LlmProposalResult r : results) {
      rawResponses.add(r.content());
    }
    ImmutableList<String> merged = LlmEnsembleMerger.unionValidate(rawResponses, budget);
    boolean hasAccepted = false;
    for (LlmProposalResult r : results) {
      if (!LlmResponseParser.parsePredicates(r.content()).isEmpty()) {
        hasAccepted = true;
        break;
      }
    }
    return new ProfileInvokeResult(results, merged, hasAccepted);
  }

  private static Map<String, String> profileMap(ImmutableList<AttributedRawPredicate> attributed) {
    Map<String, String> map = new LinkedHashMap<>();
    for (AttributedRawPredicate a : attributed) {
      map.putIfAbsent(a.raw(), a.profile().name());
    }
    return map;
  }

  private List<VGuideAnalysisDumper.DumpValidatedPredicate> buildValidatedDump(
      ContextPack pack,
      List<String> rawPreds,
      ValidationResult validation,
      List<ARGState> trace,
      Map<String, String> profileByRaw) {
    if (analysisDumper == null) {
      return List.of();
    }
    Map<CFANode, BooleanFormula> blocks =
        LoopHeadBlockFormulaIndex.fromTrace(pack.blockFormulas(), trace);
    BooleanFormulaManager bfmgr = fmgr.getBooleanFormulaManager();
    Map<BooleanFormula, String> formulaToRaw = new LinkedHashMap<>();
    for (String raw : rawPreds) {
      if (!PredicateContractValidator.isValid(raw)) {
        continue;
      }
      BooleanFormula parsed = VocabularyGuide.parsePredicate(raw, fmgr, pack.encodedVars());
      if (parsed != null && !bfmgr.isTrue(parsed) && !bfmgr.isFalse(parsed)) {
        formulaToRaw.putIfAbsent(parsed, raw);
      }
    }
    List<VGuideAnalysisDumper.DumpValidatedPredicate> out = new ArrayList<>();
    for (ValidatedPredicate vp : validation.validated()) {
      String raw = formulaToRaw.getOrDefault(vp.formula(), "");
      BooleanFormula block =
          blocks.getOrDefault(vp.loopHeadNode(), bfmgr.makeTrue());
      out.add(
          new VGuideAnalysisDumper.DumpValidatedPredicate(
              analysisDumper.nextPredicateId(),
              raw,
              vp,
              block,
              !raw.isEmpty(),
              !raw.isEmpty(),
              false,
              profileByRaw.getOrDefault(raw, "")));
    }
    return out;
  }

  private static List<VGuideAnalysisDumper.DumpValidatedPredicate> markInjected(
      List<VGuideAnalysisDumper.DumpValidatedPredicate> validated,
      ImmutableList<ValidatedPredicate> toInject) {
    List<VGuideAnalysisDumper.DumpValidatedPredicate> out = new ArrayList<>();
    for (VGuideAnalysisDumper.DumpValidatedPredicate p : validated) {
      boolean injected =
          toInject.stream()
              .anyMatch(
                  v ->
                      v.formula().equals(p.validated().formula())
                          && v.loopHeadNode().equals(p.validated().loopHeadNode()));
      out.add(
          new VGuideAnalysisDumper.DumpValidatedPredicate(
              p.predicateId(),
              p.rawString(),
              p.validated(),
              p.blockFormula(),
              p.l1Ok(),
              p.l2Ok(),
              injected,
              p.sourceProfile()));
    }
    return out;
  }

  private CounterexampleTraceInfo strengthenInterpolants(
      CounterexampleTraceInfo counterexample,
      List<ARGState> abstractionStatesTrace,
      ImmutableList<ValidatedPredicate> entailed) {
    if (entailed.isEmpty()) {
      return counterexample;
    }
    BooleanFormulaManager bfmgr = fmgr.getBooleanFormulaManager();
    List<BooleanFormula> interpolants = new ArrayList<>(counterexample.getInterpolants());
    Map<Integer, List<BooleanFormula>> byIndex = new HashMap<>();
    int n = Math.min(abstractionStatesTrace.size(), interpolants.size());
    for (ValidatedPredicate vp : entailed) {
      for (int i = 0; i < n; i++) {
        CFANode node = extractLocation(abstractionStatesTrace.get(i));
        if (node != null && node.equals(vp.loopHeadNode())) {
          byIndex.computeIfAbsent(i, k -> new ArrayList<>()).add(vp.formula());
        }
      }
    }
    int strengthened = 0;
    for (var e : byIndex.entrySet()) {
      BooleanFormula conj = e.getValue().get(0);
      for (int j = 1; j < e.getValue().size(); j++) {
        conj = bfmgr.and(conj, e.getValue().get(j));
      }
      interpolants.set(e.getKey(), bfmgr.and(interpolants.get(e.getKey()), conj));
      strengthened++;
    }
    if (strengthened > 0) {
      logger.log(Level.INFO, "VGuide strengthened ", strengthened, " interpolants");
      return CounterexampleTraceInfo.infeasible(interpolants);
    }
    return counterexample;
  }

  private String benchmarkBaseName() {
    return benchmarkBaseName(cfa);
  }

  private static String benchmarkBaseName(CFA cfa) {
    if (cfa.getFileNames().isEmpty()) {
      return "unknown";
    }
    String name = cfa.getFileNames().get(0).getFileName().toString();
    int dot = name.lastIndexOf('.');
    return dot > 0 ? name.substring(0, dot) : name;
  }
}
