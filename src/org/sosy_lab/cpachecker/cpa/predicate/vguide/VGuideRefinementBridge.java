// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static org.sosy_lab.cpachecker.util.AbstractStates.extractLocation;

import com.google.common.base.Predicates;
import com.google.common.collect.HashMultimap;
import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableSet;
import com.google.common.collect.ImmutableSetMultimap;
import java.io.IOException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
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
import org.sosy_lab.cpachecker.core.interfaces.Precision;
import org.sosy_lab.cpachecker.cpa.arg.ARGReachedSet;
import org.sosy_lab.cpachecker.cpa.arg.ARGState;
import org.sosy_lab.cpachecker.cpa.predicate.BlockFormulaStrategy.BlockFormulas;
import org.sosy_lab.cpachecker.cpa.predicate.PredicateAbstractionManager;
import org.sosy_lab.cpachecker.cpa.predicate.PredicatePrecision;
import org.sosy_lab.cpachecker.cpa.predicate.VocabularyGuide;
import org.sosy_lab.cpachecker.util.LoopStructure;
import org.sosy_lab.cpachecker.util.Precisions;
import org.sosy_lab.cpachecker.util.predicates.AbstractionPredicate;
import org.sosy_lab.cpachecker.cpa.predicate.PredicatePrecision.LocationInstance;
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
  private final CeHistoryStore ceHistoryStore;
  private final RefinementOutcomeStore refinementOutcomeStore = new RefinementOutcomeStore();
  private final Set<String> llmOwnedKeys = new HashSet<>();
  private final NativePredicateContextBuilder nativeContextBuilder =
      new NativePredicateContextBuilder(llmOwnedKeys);
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
  private @Nullable List<ValidatedPredicate> preCegarValidated = null;
  private boolean suppressCurrentPrecisionInjection = false;

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
  List<CandidateRejection> rejections = List.of();
  CeHistoryStore.@Nullable Snapshot ceHistorySnapshot;
  @Nullable String refinementOutcomeLine;
  NativePredicateContextBuilder.@Nullable Context nativeContext;
  Set<String> precisionBeforeSnapshot = Set.of();
  int llmPrecisionRemoved = -1;
  int llmPrecisionRetained = -1;
  PredicateUsefulnessGate.@Nullable Decision usefulnessGateDecision;
  }

  public static VGuideRefinementBridge create(
      Configuration config,
      LogManager logger,
      CFA cfa,
      Optional<LoopStructure> loopStructure,
      Solver solver,
      @Nullable PredicateAbstractionManager predAbsManager,
      PredicateProposalClient llmClient)
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
        llmClient,
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
    this.ceHistoryStore = new CeHistoryStore();
    this.analysisStartMs = System.currentTimeMillis();
    if (analysisDumper != null) {
      shutdownHook = new Thread(this::finishDumpOnShutdown, "vguide-analysis-dump-finish");
      Runtime.getRuntime().addShutdownHook(shutdownHook);
    } else {
      shutdownHook = null;
    }
  }

  /**
   * Called before analysis starts (source-prior mode). Fires LLM with source-only context pack,
   * validates predicates with L1/L2 only, and stores results for initial-precision injection.
   */
  public void firePreCegarLlm() {
    if (llmClient == null || !wallBudget.hasRemainingForLlm()) {
      logger.log(Level.INFO, "VGuide source-prior: skip pre-CEGAR LLM (no client or wall budget)");
      return;
    }
    ContextPack pack = contextPackBuilder.buildSourceOnly();
    PredicateBudget budget = options.getPredicateBudget();
    BudgetResolution budgetRes = new BudgetResolution(budget, "source_prior", -1);
    long t0 = System.currentTimeMillis();
    try {
      List<LoopHeadCandidate> rawCandidates = new ArrayList<>();
      PromptMessages safeMessages =
          promptBuilder.buildPrompt(pack, budget, PromptProfile.SAFE, 1);
      LlmProposalResult safeResult = llmClient.proposeWithUsage(safeMessages);
      rawCandidates.addAll(LoopHeadCandidateParser.parse(safeResult.content()));
      if (options.isDualPromptMode()) {
        PromptMessages bugMessages =
            promptBuilder.buildPrompt(pack, budget, PromptProfile.BUG_HUNT, 1);
        LlmProposalResult bugResult = llmClient.proposeWithUsage(bugMessages);
        rawCandidates.addAll(LoopHeadCandidateParser.parse(bugResult.content()));
      }
      long latency = System.currentTimeMillis() - t0;
      wallBudget.recordLlmCall(latency);
      llmScheduler.recordCallCompleted();
      preCegarValidated = validateSourceOnly(pack, rawCandidates);
      outcome = VGuideOutcome.SOURCE_PRIOR_LLM;
      logger.log(
          Level.INFO,
          "VGuide source-prior LLM: raw=",
          rawCandidates.size(),
          " validated=",
          preCegarValidated.size(),
          " latencyMs=",
          latency);
      if (analysisDumper != null) {
        analysisDumper.recordLlmApiCall(
            0, 0, "safe_primary", "source_prior_safe",
            safeMessages.fullText(), pack, PromptProfile.SAFE, safeResult,
            List.of(), budgetRes);
      }
    } catch (IOException e) {
      logger.logUserException(Level.WARNING, e, "VGuide source-prior LLM call failed");
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
    }
  }

  private List<ValidatedPredicate> validateSourceOnly(
      ContextPack pack, List<LoopHeadCandidate> candidates) {
    BooleanFormulaManager bfmgr = fmgr.getBooleanFormulaManager();
    List<ValidatedPredicate> out = new ArrayList<>();
    Set<String> seen = new HashSet<>();
    for (LoopHeadCandidate candidate : candidates) {
      List<LoopHeadInfo> heads = new ArrayList<>();
      for (String label : candidate.loopHeads()) {
        LoopHeadInfo head = PredicateValidationPipeline.findHead(pack, label);
        if (head != null && !heads.contains(head)) {
          heads.add(head);
        }
      }
      if (heads.isEmpty()) {
        logger.log(
            Level.FINE,
            "VGuide source-prior: drop candidate with unknown loop head(s): ",
            candidate.loopHeads());
        continue;
      }
      BooleanFormula parsed =
          VocabularyGuide.parsePredicate(candidate.predicate(), fmgr, ImmutableSet.of());
      if (parsed == null || bfmgr.isTrue(parsed) || bfmgr.isFalse(parsed)) {
        continue;
      }
      for (LoopHeadInfo head : heads) {
        String pairKey = head.node().getNodeNumber() + "#" + candidate.predicate();
        if (!seen.add(pairKey)) {
          continue;
        }
        out.add(
            new ValidatedPredicate(
                parsed,
                head.node(),
                ValidatedPredicate.Classification.PRECISION_ONLY,
                candidate.role(),
                candidate.variables(),
                false,
                false));
      }
      logger.log(Level.INFO, "VGuide source-prior L1/L2 validated: ", candidate.predicate());
    }
    return out;
  }

  /**
   * Merges pre-CEGAR validated predicates into the given base {@link PredicatePrecision}. Called
   * from {@code PredicateCPA.getInitialPrecision()} so predicates are active from round 0.
   */
  public PredicatePrecision mergePreCegarInto(PredicatePrecision base) {
    if (preCegarValidated == null || preCegarValidated.isEmpty()) {
      return base;
    }
    return precisionInjector.mergePreCegarInto(base, preCegarValidated);
  }

  /** Updated after each refinement attempt so a shutdown hook can write partial dumps. */
  public void trackAnalysisProgress(int refinementCount, @Nullable ARGReachedSet reached) {
    trackedRefinementCount = refinementCount;
    if (reached != null) {
      trackedReached = reached;
    }
  }

  /**
   * Number of abstraction states in the counterexample trace located at a loop head. A trace that
   * passes a loop head more times each refinement is "peeling" the loop (divergence signature).
   */
  private static int countLoopHeadVisits(
      @Nullable List<ARGState> trace, ImmutableList<LoopHeadInfo> loopHeads) {
    if (trace == null || loopHeads.isEmpty()) {
      return 0;
    }
    Set<CFANode> heads = new HashSet<>();
    for (LoopHeadInfo h : loopHeads) {
      heads.add(h.node());
    }
    int visits = 0;
    for (ARGState s : trace) {
      if (heads.contains(extractLocation(s))) {
        visits++;
      }
    }
    return visits;
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
    suppressCurrentPrecisionInjection = false;

    ContextPack pack =
        contextPackBuilder.build(refinementIndex, formulas, counterexample, abstractionStatesTrace);
    int loopHeadVisits = countLoopHeadVisits(abstractionStatesTrace, pack.loopHeads());
    refinementOutcomeStore.recordStarted(
        refinementIndex,
        loopHeadVisits,
        counterexample.getInterpolants() == null ? 0 : counterexample.getInterpolants().size(),
        formulas.getSize());
    logger.log(
        Level.INFO,
        "VGuide peel: refinement #"
            + refinementIndex
            + " loopHeadVisits="
            + loopHeadVisits
            + " traceLen="
            + (abstractionStatesTrace == null ? 0 : abstractionStatesTrace.size()));
    PendingRefinementDump dump = new PendingRefinementDump();
    dump.precisionBeforeSnapshot = canonicalPrecisionSet(reachedBefore);
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

    if (options.isSourcePriorMode()) {
      dump.llmSkipReason = "source_prior";
      return counterexample;
    }

    if (!llmScheduler.shouldCall(refinementIndex, loopHeadVisits)) {
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
      ImmutableList<LoopHeadCandidate> mergedCandidates = ImmutableList.of();
      Map<String, String> profileByRaw = new LinkedHashMap<>();
      boolean safeAccepted = false;
      boolean bugAccepted = false;
      String ceHistory = "";
      if (options.getCeHistoryMode() != VGuideOptions.CeHistoryMode.OFF) {
        ceHistory = ceHistoryStore.buildContext(options.getCeHistoryMode(), pack.ceSummary());
        ceHistoryStore.record(refinementIndex, pack.ceSummary());
        dump.ceHistorySnapshot = ceHistoryStore.snapshot();
      }
      String refinementOutcomeText =
          options.isRefinementOutcomeContextEnabled()
              ? refinementOutcomeStore.buildContext()
              : "";
      String nativeContextText = "";
      if (options.isNativePredicateContextEnabled()) {
        dump.nativeContext = buildNativeContext(reachedBefore, pack);
        if (dump.nativeContext != null) {
          nativeContextText = NativePredicateContextBuilder.format(dump.nativeContext);
        }
      }

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
                rejectedAll,
                ceHistory,
                refinementOutcomeText,
                nativeContextText);
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
                rejectedAll,
                ceHistory,
                refinementOutcomeText,
                nativeContextText);
        apiResults.addAll(bug.apiResults());
        bugAccepted = bug.hasAccepted();
        mergedCandidates =
            LlmEnsembleMerger.mergeDualUnionCandidates(safe.candidates(), bug.candidates());
        for (LoopHeadCandidate c : safe.candidates()) {
          profileByRaw.putIfAbsent(c.predicate(), PromptProfile.SAFE.name());
        }
        for (LoopHeadCandidate c : bug.candidates()) {
          profileByRaw.putIfAbsent(c.predicate(), PromptProfile.BUG_HUNT.name());
        }
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
                rejectedAll,
                ceHistory,
                refinementOutcomeText,
                nativeContextText);
        apiResults.addAll(safe.apiResults());
        safeAccepted = safe.hasAccepted();
        mergedCandidates = safe.candidates();
        for (LoopHeadCandidate c : safe.candidates()) {
          profileByRaw.putIfAbsent(c.predicate(), PromptProfile.SAFE.name());
        }
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
      Set<String> seenPreds = new LinkedHashSet<>();
      for (LoopHeadCandidate c : mergedCandidates) {
        if (seenPreds.add(c.predicate())) {
          rawPreds.add(c.predicate());
        }
      }

      if (rawPreds.isEmpty() && !safeAccepted && !bugAccepted) {
        List<String> rejectedForRepair = new ArrayList<>();
        for (LlmProposalResult r : apiResults) {
          rejectedForRepair.addAll(rejectedTexts(r.content()));
        }
        rejectedForRepair = rejectedForRepair.stream().distinct().limit(5).toList();
        if (!rejectedForRepair.isEmpty()) {
          PromptProfile repairProfile =
              options.isDualPromptMode() ? PromptProfile.BUG_HUNT : PromptProfile.SAFE;
          PromptMessages repairMessages =
              promptBuilder.buildRepair(
                  pack,
                  rejectedForRepair,
                  budget,
                  repairProfile,
                  refinementIndex,
                  ceHistory,
                  refinementOutcomeText,
                  nativeContextText);
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
          ImmutableList<LoopHeadCandidate> repairCandidates =
              LoopHeadCandidateParser.parse(repair.content());
          if (!repairCandidates.isEmpty()) {
            mergedCandidates = repairCandidates;
            rawPreds = repairCandidates.stream().map(LoopHeadCandidate::predicate).distinct().toList();
            profileByRaw.clear();
            for (LoopHeadCandidate c : repairCandidates) {
              profileByRaw.put(c.predicate(), repairProfile.name());
            }
            apiResults.add(repair);
          }
        }
      }

      PredicateValidationPipeline.CandidateValidationOutcome validationOutcome =
          validationPipeline.validateCandidates(pack, mergedCandidates, abstractionStatesTrace);
      lastValidation = validationOutcome.validation();
      for (CandidateRejection rejection : validationOutcome.rejections()) {
        logger.log(
            Level.FINE,
            "VGuide candidate rejected: ",
            rejection.reason(),
            " predicate=",
            rejection.predicate(),
            " loop_head=",
            rejection.loopHead());
      }
      dump.validated =
          buildValidatedDump(pack, rawPreds, lastValidation, abstractionStatesTrace, profileByRaw);
      dump.rejections = validationOutcome.rejections();
      if (lastValidation != null) {
        refinementOutcomeStore.recordLlmOutcome(
            refinementIndex,
            lastValidation.validated().size(),
            lastValidation.precisionOnly().size(),
            validationOutcome.rejections().size());
      }
      if (options.isPredicateUsefulnessGateEnabled()) {
        PredicateUsefulnessGate.Decision usefulnessDecision =
            PredicateUsefulnessGate.evaluate(loopHeadVisits, lastValidation, fmgr);
        dump.usefulnessGateDecision = usefulnessDecision;
        if (usefulnessDecision.rejects()) {
          suppressCurrentPrecisionInjection = true;
          llmScheduler.suppressForPredicateUsefulnessGate();
          logger.log(
              Level.INFO,
              "VGuide predicate usefulness gate rule="
                  + PredicateUsefulnessGate.RULE_VERSION
                  + " decision="
                  + usefulnessDecision.action()
                  + " loopHeadVisits="
                  + loopHeadVisits
                  + " uniqueValidatedPredicates="
                  + usefulnessDecision.uniqueValidatedPredicates()
                  + " uniqueMultiplicativePredicates="
                  + usefulnessDecision.uniqueMultiplicativePredicates());
        }
      }
      if (!suppressCurrentPrecisionInjection
          && options.isAllowInterpolantStrengthen()
          && options.isEnableL3Entailment()) {
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
      int nativeDelta = nativePrecisionDelta(pendingDump.precisionBeforeSnapshot, reached);
      refinementOutcomeStore.recordCompleted(refinementIndex, nativeDelta);
      pendingDump.refinementOutcomeLine = refinementOutcomeStore.completedLineFor(refinementIndex);
      List<VGuideAnalysisDumper.DumpValidatedPredicate> injected = List.of();
      if (lastValidation != null) {
        ImmutableList<ValidatedPredicate> toInject =
            suppressCurrentPrecisionInjection
                ? ImmutableList.of()
                : lastValidation.precisionOnly();
        injected = markInjected(pendingDump.validated, toInject);
        if (!suppressCurrentPrecisionInjection) {
          if (options.isReplaceLlmPredicates()) {
            var counts = removeLlmOwnedPrecision(reached);
            pendingDump.llmPrecisionRemoved = counts.removed();
            pendingDump.llmPrecisionRetained = counts.retained();
            llmOwnedKeys.clear();
          }
          precisionInjector.inject(reached, toInject);
          for (ValidatedPredicate vp : toInject) {
            if (vp != null && vp.loopHeadNode() != null && vp.formula() != null) {
              llmOwnedKeys.add(llmOwnedKey(vp.loopHeadNode().getNodeNumber(), canonical(vp.formula())));
            }
          }
        }
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
            pendingDump.llmCalled ? injected : null,
            pendingDump.llmCalled ? pendingDump.rejections : null,
            pendingDump.ceHistorySnapshot,
            pendingDump.refinementOutcomeLine,
            pendingDump.llmCalled ? pendingDump.nativeContext : null,
            pendingDump.llmPrecisionRemoved,
            pendingDump.llmPrecisionRetained,
            options.isPredicateUsefulnessGateEnabled(),
            pendingDump.usefulnessGateDecision);
      }
      pendingDump = null;
    } else if (lastValidation != null) {
      if (!suppressCurrentPrecisionInjection) {
        precisionInjector.inject(reached, lastValidation.precisionOnly());
      }
    }
    lastValidation = null;
    suppressCurrentPrecisionInjection = false;
  }

  /**
   * Called at analysis end to finalize dumps and handle NO_SPURIOUS frozen seed path.
   *
   * <p>This method is currently reached from predicate-refiner statistics printing, i.e., after the
   * analysis has already produced its verdict. Thus frozen predicate injection here affects only
   * dump/outcome accounting for this run, not the verdict itself. A verdict-effective frozen-seed
   * path needs injection into the initial predicate precision before analysis starts.
   */
  public void onAnalysisEnd(int refinementCount, Result result, @Nullable ARGReachedSet reached) {
    if (refinementCount == 0 && reached != null && outcome != VGuideOutcome.SOURCE_PRIOR_LLM) {
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
      ImmutableList<LoopHeadCandidate> candidates,
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
      List<String> rejectedOut,
      String ceHistory,
      String refinementOutcomes,
      String nativePredicateContext)
      throws IOException, InterruptedException {
    PromptMessages messages =
        promptBuilder.buildPrompt(
            pack,
            budget,
            profile,
            refinementIndex,
            ceHistory,
            refinementOutcomes,
            nativePredicateContext);
    String promptKind = promptKindBase + "_" + profile.promptKindSuffix();
    List<LlmProposalResult> results = new ArrayList<>();
    LlmProposalResult primary = llmClient.proposeWithUsage(messages);
    results.add(primary);
    List<String> primaryRejected = rejectedTexts(primary.content());
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
        List<String> rejected = rejectedTexts(extraResult.content());
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
    ImmutableList<LoopHeadCandidate> merged =
        LlmEnsembleMerger.mergeCandidates(rawResponses, budget);
    return new ProfileInvokeResult(results, merged, !merged.isEmpty());
  }

  /**
   * Removes all LLM-owned local predicates from the active precision (Issue #8). The precision
   * is immutable, so this rebuilds a filtered PredicatePrecision and applies it in one atomic
   * update; existing ARG states keep their abstractions, later refinements use the filtered
   * precision. Returns the number of removed predicates.
   */
  private record PrecisionReplacementCounts(int removed, int retained) {}

  private PrecisionReplacementCounts removeLlmOwnedPrecision(ARGReachedSet reached) {
    AbstractState firstState = reached.asReachedSet().getFirstState();
    if (firstState == null) {
      return new PrecisionReplacementCounts(0, 0);
    }
    PredicatePrecision current =
        Precisions.extractPrecisionByType(
            reached.asReachedSet().getPrecision(firstState), PredicatePrecision.class);
    if (current == null) {
      return new PrecisionReplacementCounts(0, 0);
    }
    ImmutableSetMultimap.Builder<CFANode, AbstractionPredicate> locals = ImmutableSetMultimap.builder();
    // The local and location-instance maps both contain eagerly merged predicates,
    // so track removed keys uniquely to avoid double-counting.
    Set<String> removedKeys = new HashSet<>();
    Set<String> retainedKeys = new HashSet<>();
    for (var e : current.getLocalPredicates().entries()) {
      if (e.getValue() == null || e.getValue().getSymbolicAtom() == null) {
        // defensive: never insert nulls into the ImmutableSetMultimap builder
        continue;
      }
      String key = llmOwnedKey(e.getKey().getNodeNumber(), canonical(e.getValue().getSymbolicAtom()));
      if (llmOwnedKeys.contains(key)) {
        removedKeys.add(key);
      } else {
        if (isGenuinelyLocal(current, e.getKey(), e.getValue())) {
          retainedKeys.add(key);
        }
        locals.put(e.getKey(), e.getValue());
      }
    }
    // The PredicatePrecision constructor eagerly merges local predicates into the
    // location-instance map, so LLM-owned predicates must be filtered there too,
    // otherwise they persist in the rebuilt precision.
    ImmutableSetMultimap.Builder<LocationInstance, AbstractionPredicate> locInstances =
        ImmutableSetMultimap.builder();
    for (var e : current.getLocationInstancePredicates().entries()) {
      if (e.getValue() == null || e.getValue().getSymbolicAtom() == null) {
        continue;
      }
      String key =
          llmOwnedKey(e.getKey().getLocation().getNodeNumber(), canonical(e.getValue().getSymbolicAtom()));
      if (llmOwnedKeys.contains(key)) {
        removedKeys.add(key);
      } else {
        if (isGenuinelyLocal(current, e.getKey().getLocation(), e.getValue())) {
          retainedKeys.add(key);
        }
        locInstances.put(e.getKey(), e.getValue());
      }
    }
    int removed = removedKeys.size();
    if (removed == 0) {
      return new PrecisionReplacementCounts(0, retainedKeys.size());
    }
    PredicatePrecision filtered =
        new PredicatePrecision(
            locInstances.build(),
            locals.build(),
            current.getFunctionPredicates(),
            current.getGlobalPredicates());
    reached.updatePrecisionGlobally(filtered, Predicates.instanceOf(PredicatePrecision.class));
    logger.log(
        Level.INFO,
        "VGuide replaced LLM precision: removed ",
        removed,
        " stale, retained ",
        retainedKeys.size(),
        " local predicates before injecting the new round");
    return new PrecisionReplacementCounts(removed, retainedKeys.size());
  }

  /** Canonical ownership key for one (loop head, formula) LLM predicate. */
  static String llmOwnedKey(int nodeNumber, String canonicalSmt) {
    return "local N" + nodeNumber + "|" + canonicalSmt;
  }

  private int nativePrecisionDelta(Set<String> beforeSnapshot, ARGReachedSet after) {
    Set<String> afterSet = canonicalPrecisionSet(after);
    afterSet.removeAll(beforeSnapshot);
    return afterSet.size();
  }

  private Set<String> canonicalPrecisionSet(ARGReachedSet reached) {
    Set<String> out = new HashSet<>();
    if (reached == null) {
      return out;
    }
    AbstractState firstState = reached.asReachedSet().getFirstState();
    if (firstState == null) {
      return out;
    }
    PredicatePrecision predPrec =
        Precisions.extractPrecisionByType(
            reached.asReachedSet().getPrecision(firstState), PredicatePrecision.class);
    if (predPrec == null) {
      return out;
    }
    for (AbstractionPredicate ap : predPrec.getGlobalPredicates()) {
      if (ap != null && ap.getSymbolicAtom() != null) {
        out.add("g|" + canonical(ap.getSymbolicAtom()));
      }
    }
    for (var e : predPrec.getFunctionPredicates().entries()) {
      if (e.getValue() != null && e.getValue().getSymbolicAtom() != null) {
        out.add("f|" + e.getKey() + "|" + canonical(e.getValue().getSymbolicAtom()));
      }
    }
    for (var e : predPrec.getLocalPredicates().entries()) {
      if (e.getKey() != null && e.getValue() != null && e.getValue().getSymbolicAtom() != null) {
        out.add("l|N" + e.getKey().getNodeNumber() + "|" + canonical(e.getValue().getSymbolicAtom()));
      }
    }
    return out;
  }

  private NativePredicateContextBuilder.@Nullable Context buildNativeContext(
      ARGReachedSet reached, ContextPack pack) {
    if (reached == null) {
      return null;
    }
    AbstractState firstState = reached.asReachedSet().getFirstState();
    if (firstState == null) {
      return null;
    }
    Precision currentPrec = reached.asReachedSet().getPrecision(firstState);
    PredicatePrecision predPrec =
        Precisions.extractPrecisionByType(currentPrec, PredicatePrecision.class);
    if (predPrec == null) {
      return null;
    }
    List<String> globals =
        predPrec.getGlobalPredicates().stream()
            .filter(ap -> ap != null && ap.getSymbolicAtom() != null)
            .map(ap -> canonical(ap.getSymbolicAtom()))
            .toList();
    HashMultimap<String, String> functions = HashMultimap.create();
    for (var e : predPrec.getFunctionPredicates().entries()) {
      if (e.getValue() != null && e.getValue().getSymbolicAtom() != null) {
        functions.put(e.getKey(), canonical(e.getValue().getSymbolicAtom()));
      }
    }
    HashMultimap<String, String> locals = HashMultimap.create();
    for (var e : predPrec.getLocalPredicates().entries()) {
      if (e.getKey() != null && e.getValue() != null && e.getValue().getSymbolicAtom() != null) {
        locals.put("N" + e.getKey().getNodeNumber(), canonical(e.getValue().getSymbolicAtom()));
      }
    }
    return nativeContextBuilder.build(globals, functions, locals, pack.loopHeads());
  }

  /**
   * PredicatePrecision eagerly merges global and function predicates into the local and
   * location-instance maps; only predicates that are genuinely local (not also global or
   * function-scoped at this node's function) count as retained local predicates.
   */
  private static boolean isGenuinelyLocal(
      PredicatePrecision precision, CFANode node, AbstractionPredicate predicate) {
    if (precision.getGlobalPredicates().contains(predicate)) {
      return false;
    }
    if (precision.getFunctionPredicates().get(node.getFunctionName()).contains(predicate)) {
      return false;
    }
    return true;
  }

  private String canonical(BooleanFormula f) {
    return fmgr.dumpFormula(f).toString().replace('\n', ' ');
  }

  private static List<String> rejectedTexts(String content) {
    return LoopHeadCandidateParser.parseWithRejects(content).rejected().stream()
        .map(CandidateRejection::predicate)
        .filter(p -> !p.isEmpty())
        .toList();
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
