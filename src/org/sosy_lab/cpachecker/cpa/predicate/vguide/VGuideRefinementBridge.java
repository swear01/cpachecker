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
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.logging.Level;
import org.checkerframework.checker.nullness.qual.Nullable;
import org.sosy_lab.common.configuration.Configuration;
import org.sosy_lab.common.configuration.InvalidConfigurationException;
import org.sosy_lab.common.log.LogManager;
import org.sosy_lab.cpachecker.cfa.CFA;
import org.sosy_lab.cpachecker.cfa.model.CFANode;
import org.sosy_lab.cpachecker.core.interfaces.AbstractState;
import org.sosy_lab.cpachecker.cpa.arg.ARGReachedSet;
import org.sosy_lab.cpachecker.cpa.arg.ARGState;
import org.sosy_lab.cpachecker.cpa.arg.path.ARGPath;
import org.sosy_lab.cpachecker.cpa.predicate.BlockFormulaStrategy.BlockFormulas;
import org.sosy_lab.cpachecker.cpa.predicate.PredicateAbstractionManager;
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
  private final PredicateValidationPipeline validationPipeline;
  private final LoopHeadPrecisionInjector precisionInjector;
  private final FrozenPredicateLoader frozenLoader;
  private final LoopHeadIndex loopHeadIndex;
  private final WallClockBudget wallBudget;
  private final LlmCallScheduler llmScheduler;
  private final CFA cfa;
  private final FormulaManagerView fmgr;

  private @Nullable ValidationResult lastValidation;
  private VGuideOutcome outcome = VGuideOutcome.NO_SPURIOUS_GIVE_UP;

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
    return new VGuideRefinementBridge(
        logger,
        opts,
        new PredicateProposalClient(logger),
        cfa,
        fmgr,
        loopHeads,
        new ContextPackBuilder(cfa, loopHeads, fmgr),
        new ProposalPromptBuilder(loopHeads),
        new PredicateValidationPipeline(logger, solver, fmgr, opts.isEnableL3Entailment()),
        new LoopHeadPrecisionInjector(logger, predAbsManager),
        new FrozenPredicateLoader(logger, opts.getFrozenDir()),
        new WallClockBudget(opts.getWallBudgetSec()),
        new LlmCallScheduler(opts, logger));
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
      PredicateValidationPipeline validationPipeline,
      LoopHeadPrecisionInjector precisionInjector,
      FrozenPredicateLoader frozenLoader,
      WallClockBudget wallBudget,
      LlmCallScheduler llmScheduler) {
    this.logger = logger;
    this.options = options;
    this.llmClient = llmClient;
    this.cfa = cfa;
    this.fmgr = fmgr;
    this.loopHeadIndex = loopHeadIndex;
    this.contextPackBuilder = contextPackBuilder;
    this.promptBuilder = promptBuilder;
    this.validationPipeline = validationPipeline;
    this.precisionInjector = precisionInjector;
    this.frozenLoader = frozenLoader;
    this.wallBudget = wallBudget;
    this.llmScheduler = llmScheduler;
  }

  /**
   * Called after spurious CE check, before {@code strategy.performRefinement}. May strengthen
   * interpolants (ENTAILED) and schedule precision injection.
   */
  public CounterexampleTraceInfo onSpuriousBeforeRefinement(
      int refinementIndex,
      List<ARGState> abstractionStatesTrace,
      BlockFormulas formulas,
      CounterexampleTraceInfo counterexample)
      throws InterruptedException {
    lastValidation = null;
    if (!counterexample.isSpurious()
        || counterexample.getInterpolants() == null
        || counterexample.getInterpolants().isEmpty()) {
      return counterexample;
    }

    if (!llmScheduler.shouldCall(refinementIndex)) {
      return counterexample;
    }
    if (!wallBudget.hasRemainingForLlm()) {
      logger.log(Level.INFO, "VGuide: wall budget exhausted; skipping LLM");
      return counterexample;
    }

    ContextPack pack = contextPackBuilder.build(refinementIndex, formulas, counterexample);
    String prompt =
        refinementIndex == 1
            ? promptBuilder.buildFirstSpurious(pack)
            : promptBuilder.buildLaterSpurious(pack);
    long t0 = System.currentTimeMillis();
    try {
      int samplesConfigured = options.getLlmSamplesForRefinement(refinementIndex);
      List<String> rawResponses = invokeLlmEnsemble(prompt, samplesConfigured);
      long latency = System.currentTimeMillis() - t0;
      wallBudget.recordLlmCall(latency);
      llmScheduler.recordCallCompleted();
      if (refinementIndex == 1) {
        outcome = VGuideOutcome.FIRST_SPURIOUS_LLM;
      }
      logger.log(
          Level.INFO,
          "VGuide LLM round #",
          llmScheduler.getLlmCallsDone(),
          " spurious #",
          refinementIndex,
          " samples=",
          samplesConfigured,
          " api=",
          rawResponses.size(),
          " schedule=",
          options.getLlmCallSchedule(),
          " prompt=",
          refinementIndex == 1 ? "first" : "later",
          " latencyMs=",
          latency);
      ImmutableList<String> rawPreds = LlmEnsembleMerger.unionValidate(rawResponses);
      List<String> rejectedForRepair = new ArrayList<>();
      if (rawPreds.isEmpty()) {
        for (String raw : rawResponses) {
          rejectedForRepair.addAll(LlmResponseParser.parseWithRejects(raw).rejected());
        }
      }
      String combinedRaw = String.join("\n---\n", rawResponses);
      if (rawPreds.isEmpty() && !rejectedForRepair.isEmpty()) {
        String repairPrompt =
            promptBuilder.buildRepair(
                pack, rejectedForRepair.stream().distinct().limit(5).toList());
        logger.log(Level.INFO, "VGuide: ensemble L1 empty; one repair LLM call");
        String repairRaw = llmClient.propose(repairPrompt);
        combinedRaw = combinedRaw + "\n--- repair ---\n" + repairRaw;
        rawPreds = LlmResponseParser.parsePredicates(repairRaw);
      }
      lastValidation =
          validationPipeline.validate(pack, rawPreds, abstractionStatesTrace);
      if (options.isAllowInterpolantStrengthen() && options.isEnableL3Entailment()) {
        return strengthenInterpolants(
            counterexample, abstractionStatesTrace, lastValidation.entailed());
      }
    } catch (InterruptedException e) {
      throw e;
    } catch (IOException e) {
      logger.logUserException(Level.WARNING, e, "VGuide LLM call failed");
    }
    return counterexample;
  }

  /** Called after {@code strategy.performRefinement} to inject PRECISION_ONLY predicates. */
  public void onSpuriousAfterRefinement(int refinementIndex, ARGReachedSet reached) {
    if (lastValidation == null) {
      return;
    }
    precisionInjector.inject(reached, lastValidation.precisionOnly());
    lastValidation = null;
  }

  /** Called at analysis end when no refinement occurred (NO_SPURIOUS exception path). */
  public void onAnalysisEnd(int refinementCount, @Nullable ARGReachedSet reached) {
    if (refinementCount > 0 || reached == null) {
      return;
    }
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

  public VGuideOutcome getOutcome() {
    return outcome;
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

  /**
   * Refinement #1: one synchronous API (cache seed). Later rounds: 1 sync + (K-1) parallel extras.
   */
  private List<String> invokeLlmEnsemble(String prompt, int samplesConfigured)
      throws IOException, InterruptedException {
    List<String> rawResponses = new ArrayList<>();
    rawResponses.add(llmClient.propose(prompt));
    int extra = samplesConfigured - 1;
    if (extra > 0) {
      rawResponses.addAll(
          llmClient.proposeParallelExtras(
              prompt, extra, options.getLlmSampleParallelism()));
    }
    return rawResponses;
  }

  private String benchmarkBaseName() {
    if (cfa.getFileNames().isEmpty()) {
      return "unknown";
    }
    String name = cfa.getFileNames().get(0).getFileName().toString();
    int dot = name.lastIndexOf('.');
    return dot > 0 ? name.substring(0, dot) : name;
  }

}
