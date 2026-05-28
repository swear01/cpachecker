// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-FileCopyrightText: 2007-2020 Dirk Beyer <https://www.sosy-lab.org>
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate;

import static com.google.common.collect.FluentIterable.from;
import static org.sosy_lab.cpachecker.util.AbstractStates.extractLocation;
import static org.sosy_lab.cpachecker.util.AbstractStates.extractOptionalCallstackWraper;
import static org.sosy_lab.cpachecker.util.statistics.StatisticsWriter.writingStatisticsTo;

import com.google.common.base.Preconditions;
import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableSet;
import com.google.common.base.Predicates;
import java.io.PrintStream;
import java.util.ArrayList;
import java.util.Collection;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.logging.Level;
import org.checkerframework.checker.nullness.qual.Nullable;
import org.sosy_lab.common.configuration.Configuration;
import org.sosy_lab.common.configuration.IntegerOption;
import org.sosy_lab.common.configuration.InvalidConfigurationException;
import org.sosy_lab.common.configuration.Option;
import org.sosy_lab.common.configuration.Options;
import org.sosy_lab.common.log.LogManager;
import org.sosy_lab.cpachecker.cfa.model.CFANode;
import org.sosy_lab.cpachecker.core.CPAcheckerResult.Result;
import org.sosy_lab.cpachecker.core.counterexample.CounterexampleInfo;
import org.sosy_lab.cpachecker.core.interfaces.AbstractState;
import org.sosy_lab.cpachecker.core.interfaces.Precision;
import org.sosy_lab.cpachecker.core.interfaces.Statistics;
import org.sosy_lab.cpachecker.core.interfaces.StatisticsProvider;
import org.sosy_lab.cpachecker.core.reachedset.UnmodifiableReachedSet;
import org.sosy_lab.cpachecker.cpa.arg.ARGBasedRefiner;
import org.sosy_lab.cpachecker.cpa.arg.ARGReachedSet;
import org.sosy_lab.cpachecker.cpa.arg.ARGState;
import org.sosy_lab.cpachecker.cpa.arg.path.ARGPath;
import org.sosy_lab.cpachecker.cpa.arg.path.PathIterator;
import org.sosy_lab.cpachecker.cpa.callstack.CallstackStateEqualsWrapper;
import org.sosy_lab.cpachecker.cpa.predicate.BlockFormulaStrategy.BlockFormulas;
import org.sosy_lab.cpachecker.exceptions.CPAException;
import org.sosy_lab.cpachecker.exceptions.CPATransferException;
import org.sosy_lab.cpachecker.exceptions.RefinementFailedException;
import org.sosy_lab.cpachecker.exceptions.RefinementFailedException.Reason;
import org.sosy_lab.cpachecker.util.AbstractStates;
import org.sosy_lab.cpachecker.util.LoopStructure;
import org.sosy_lab.cpachecker.util.Precisions;
import org.sosy_lab.cpachecker.util.predicates.AbstractionPredicate;
import org.sosy_lab.cpachecker.util.LoopStructure.Loop;
import org.sosy_lab.cpachecker.util.cwriter.LoopCollectingEdgeVisitor;
import org.sosy_lab.cpachecker.util.predicates.NewtonRefinementManager;
import org.sosy_lab.cpachecker.util.predicates.PathChecker;
import org.sosy_lab.cpachecker.util.predicates.UCBRefinementManager;
import org.sosy_lab.cpachecker.util.predicates.interpolation.CounterexampleTraceInfo;
import org.sosy_lab.cpachecker.util.predicates.interpolation.InterpolationManager;
import org.sosy_lab.cpachecker.util.predicates.pathformula.PathFormulaManager;
import org.sosy_lab.cpachecker.util.predicates.smt.FormulaManagerView;
import org.sosy_lab.cpachecker.util.predicates.smt.BooleanFormulaManagerView;
import org.sosy_lab.cpachecker.util.predicates.smt.Solver;
import org.sosy_lab.cpachecker.util.refinement.InfeasiblePrefix;
import org.sosy_lab.cpachecker.util.refinement.PrefixProvider;
import org.sosy_lab.cpachecker.util.refinement.PrefixSelector;
import org.sosy_lab.cpachecker.util.refinement.PrefixSelector.PrefixPreference;
import org.sosy_lab.cpachecker.util.statistics.StatInt;
import org.sosy_lab.cpachecker.util.statistics.StatKind;
import org.sosy_lab.cpachecker.util.statistics.StatTimer;
import org.sosy_lab.cpachecker.util.statistics.StatisticsWriter;
import org.sosy_lab.java_smt.api.BooleanFormula;
import org.sosy_lab.java_smt.api.ProverEnvironment;
import org.sosy_lab.java_smt.api.SolverContext.ProverOptions;
import org.sosy_lab.java_smt.api.SolverException;

/**
 * This class provides a basic refiner implementation for predicate analysis. When a counterexample
 * is found, it creates a path for it and checks it for feasibility, getting the interpolants if
 * possible.
 *
 * <p>It does not define any strategy for using the interpolants to update the abstraction, this is
 * left to an instance of {@link RefinementStrategy}.
 *
 * <p>It does, however, produce a nice error path in case of a feasible counterexample.
 */
@Options(prefix = "cpa.predicate.refinement")
final class PredicateCPARefiner implements ARGBasedRefiner, StatisticsProvider {

  @Option(secure = true, description = "which sliced prefix should be used for interpolation")
  private List<PrefixPreference> prefixPreference = PrefixSelector.NO_SELECTION;

  @Option(
      secure = true,
      description =
          "use only the atoms from the interpolants"
              + "as predicates, and not the whole interpolant")
  private boolean atomicInterpolants = true;

  @Option(
      secure = true,
      description =
          "Should the path invariants be created and used (potentially additionally to the other"
              + " invariants)")
  private boolean usePathInvariants = false;

  @Option(
      secure = true,
      description = "use Newton-based Algorithm for the CPA-Refinement, experimental feature!")
  private boolean useNewtonRefinement = false;

  @Option(
      secure = true,
      description = "use UCB predicates for the CPA-Refinement, experimental feature!")
  private boolean useUCBRefinement = false;

  @Option(
      secure = true,
      description =
          "Stop after refining the n-th spurious counterexample and export that. If 0, stop after"
              + " finding the first spurious counterexample but before refinement. If -1, never"
              + " stop. If this option is used with a value different from -1, option"
              + " counterexample.export.alwaysUseImpreciseCounterexamples=true should be set. Then,"
              + " an actually infeasible counterexample will be handed to export. So this option"
              + " will also not work with additional counterexample checks or similar, because"
              + " these may reject the (infeasible) counterexample.")
  @IntegerOption(min = -1)
  private int stopAfter = -1;

  // statistics
  private final StatInt totalPathLength =
      new StatInt(StatKind.AVG, "Avg. length of target path (in blocks)"); // measured in blocks
  private final StatTimer totalRefinement = new StatTimer("Time for refinement");
  private final StatTimer prefixExtractionTime =
      new StatTimer("Extracting infeasible sliced prefixes");

  private final StatTimer errorPathProcessing = new StatTimer("Error-path post-processing");
  private final StatTimer getFormulasForPathTime = new StatTimer("Path-formulas extraction");

  private final StatInt totalPrefixes =
      new StatInt(StatKind.SUM, "Number of infeasible sliced prefixes");
  private final StatTimer prefixSelectionTime =
      new StatTimer("Selecting infeasible sliced prefixes");

  /** Number of performed refinements */
  private int refinements = 0;

  // V-guided statistics
  private int vInjectionAttempts = 0;
  private int vInjectionSuccesses = 0;
  private int vSmtValidated = 0;
  private int vSmtFailed = 0;
  private int vFallbacks = 0;
  private int vAbstractionCandidates = 0;
  private Map<CFANode, Set<BooleanFormula>> pendingAbstractionCandidates = new LinkedHashMap<>();
  private Map<CFANode, BooleanFormula> v4BlockContext = new LinkedHashMap<>();
  private Set<String> lastEncodedVars = Set.of();
  private boolean vPrecisionInjected = false;
  private PredicateScorer v4Scorer;
  private B5ContextDumper b5Dumper;
  private Map<CFANode, Set<BooleanFormula>> b5Entailed = new LinkedHashMap<>();
  private Map<CFANode, Set<BooleanFormula>> b5Injected = new LinkedHashMap<>();

  // the previously analyzed counterexample to detect repeated counterexamples
  private final Set<ImmutableList<CFANode>> lastErrorPaths = new HashSet<>();

  private final PathChecker pathChecker;

  private final PredicateCPAInvariantsManager invariantsManager;
  private final LoopCollectingEdgeVisitor loopFinder;

  private boolean wereInvariantsUsedInLastRefinement = false;
  private boolean wereInvariantsusedInCurrentRefinement = false;
  private final Map<CFANode, BooleanFormula> lastInvariantForNode = new HashMap<>();

  private final PrefixProvider prefixProvider;
  private final PrefixSelector prefixSelector;
  private final LogManager logger;
  private final BlockFormulaStrategy blockFormulaStrategy;
  private final Solver solver;
  private final FormulaManagerView fmgr;
  private final PathFormulaManager pfmgr;
  private final InterpolationManager interpolationManager;
  private final @Nullable VocabularyGuide vocabularyGuide;
  private final @Nullable LLMConnector llmConnector;
  private boolean useVGuide;
  private final RefinementStrategy strategy;
  private final @Nullable PredicateAbstractionManager predAbsManager;
  private final Optional<NewtonRefinementManager> newtonManager;
  private final Optional<UCBRefinementManager> ucbManager;

  PredicateCPARefiner(
      final Configuration pConfig,
      final LogManager pLogger,
      final Optional<LoopStructure> pLoopStructure,
      final BlockFormulaStrategy pBlockFormulaStrategy,
      final Solver pSolver,
      final PathFormulaManager pPfgmr,
      final InterpolationManager pInterpolationManager,
      final PathChecker pPathChecker,
      final PrefixProvider pPrefixProvider,
      final PrefixSelector pPrefixSelector,
      final PredicateCPAInvariantsManager pInvariantsManager,
      final RefinementStrategy pStrategy,
      final @Nullable List<InterpolationManager> pAllInterpolationManagers,
      final @Nullable List<String> pInterpolationManagerLabels,
      final @Nullable VocabularyGuide pVocabularyGuide,
      final @Nullable LLMConnector pLlmConnector,
      final @Nullable PredicateAbstractionManager pPredAbsManager)
      throws InvalidConfigurationException {
    pConfig.inject(this, PredicateCPARefiner.class);
    logger = pLogger;
    blockFormulaStrategy = pBlockFormulaStrategy;
    solver = pSolver;
    fmgr = solver.getFormulaManager();
    pfmgr = pPfgmr;

    interpolationManager = pInterpolationManager;
    pathChecker = pPathChecker;
    strategy = pStrategy;
    prefixProvider = pPrefixProvider;
    prefixSelector = pPrefixSelector;
    invariantsManager = pInvariantsManager;

    if (pLoopStructure.isPresent()) {
      loopFinder = new LoopCollectingEdgeVisitor(pLoopStructure.orElseThrow(), pConfig);
    } else {
      loopFinder = null;
      if (invariantsManager.addToPrecision()) {
        logger.log(
            Level.WARNING,
            "Invariants should be used during refinement, but loop information is not present.");
      }
    }

    // Create the NewtonRefinementManager iff Newton-based refinement is selected
    if (useNewtonRefinement) {
      newtonManager = Optional.of(new NewtonRefinementManager(logger, solver, pfmgr, pConfig));
    } else {
      newtonManager = Optional.empty();
    }

    if (useUCBRefinement) {
      ucbManager = Optional.of(new UCBRefinementManager(logger, solver, pfmgr));
    } else {
      ucbManager = Optional.empty();
    }

    logger.log(
        Level.INFO,
        "Using refinement for predicate analysis with "
            + strategy.getClass().getSimpleName()
            + " strategy.");

    vocabularyGuide = pVocabularyGuide;
    llmConnector = pLlmConnector;
    useVGuide = (vocabularyGuide != null);
    predAbsManager = pPredAbsManager;
    v4Scorer = new PredicateScorer(solver, fmgr, logger);
    String b5Dir = System.getenv("VGUIDE_B5_DUMP_CONTEXT");
    int b5Limit = 3;
    try {
      String envLimit = System.getenv("VGUIDE_B5_DUMP_LIMIT");
      if (envLimit != null && !envLimit.isBlank()) {
        b5Limit = Integer.parseInt(envLimit);
      }
    } catch (NumberFormatException e) {
      // use default
    }
    b5Dumper = new B5ContextDumper(b5Dir, b5Limit, fmgr, logger);
  }

  /** Create list of formulas on path. */
  private BlockFormulas createFormulasOnPath(
      final ARGPath allStatesTrace, final List<ARGState> abstractionStatesTrace)
      throws CPAException, InterruptedException {
    BlockFormulas formulas =
        isRefinementSelectionEnabled()
            ? performRefinementSelection(allStatesTrace, abstractionStatesTrace)
            : getFormulasForPath(abstractionStatesTrace, allStatesTrace.getFirstState());

    // a user would expect "abstractionStatesTrace.size() == formulas.size()+1",
    // however we do not have the very first state in the trace,
    // because the rootState has always abstraction "True".
    assert abstractionStatesTrace.size() == formulas.getSize()
        : abstractionStatesTrace.size() + " != " + formulas.getSize();

    logger.log(Level.ALL, "Error path formulas: ", formulas);
    return formulas;
  }

  @Override
  public CounterexampleInfo performRefinementForPath(
      final ARGReachedSet pReached, final ARGPath allStatesTrace)
      throws CPAException, InterruptedException {
    totalRefinement.start();

    try {
      refinements++;
      BlockFormulas formulas;
      final boolean repeatedCounterexample;
      List<ARGState> abstractionStatesTrace;
      ImmutableList<CFANode> errorPath =
          allStatesTrace.asStatesList().stream()
              .map(AbstractStates::extractLocation)
              .filter(x -> x != null)
              .collect(ImmutableList.toImmutableList());
      repeatedCounterexample = lastErrorPaths.contains(errorPath);
      lastErrorPaths.add(errorPath);

      // create path with all abstraction location elements (excluding the initial element)
      // the last element is the element corresponding to the error location
      abstractionStatesTrace = filterAbstractionStates(allStatesTrace);
      totalPathLength.setNextValue(abstractionStatesTrace.size());

      logger.log(Level.ALL, "Abstraction trace is", abstractionStatesTrace);

      formulas = createFormulasOnPath(allStatesTrace, abstractionStatesTrace);

      // find new invariants (this is a noop if no invariants should be used/generated)
      invariantsManager.findInvariants(allStatesTrace, abstractionStatesTrace, pfmgr, solver);

      CounterexampleTraceInfo counterexample =
          checkCounterexample(
              allStatesTrace, abstractionStatesTrace, formulas, repeatedCounterexample);

      // if error is spurious refine
      if (counterexample.isSpurious() && (stopAfter < 0 || refinements <= stopAfter)) {
        logger.log(Level.FINEST, "Error trace is spurious, refining the abstraction");

        List<BooleanFormula> predicates = counterexample.getInterpolants();
        logger.log(Level.INFO, "refinement #", refinements, ": predicates=", predicates.size(),
            " traceStates=", abstractionStatesTrace.size());

        boolean trackFurtherCEX =
            strategy.performRefinement(
                pReached,
                abstractionStatesTrace,
                predicates,
                repeatedCounterexample && !wereInvariantsUsedInLastRefinement);

        b5Dumper.dumpRefinement(refinements, allStatesTrace, abstractionStatesTrace,
            formulas, counterexample, pReached,
            pendingAbstractionCandidates, b5Injected, b5Entailed);

        injectAbstractionCandidates(pReached);

        if (!trackFurtherCEX) {
          // when trackFurtherCEX is false, we only track 'one' CEX, otherwise we track all of them.
          lastErrorPaths.clear();
          lastErrorPaths.add(errorPath);
        }

        // set some invariants flags, they are necessary to make sure we
        // call performRefinement in a way that it doesn't think it is a repeated
        // counterexample due to weak invariants
        wereInvariantsUsedInLastRefinement = wereInvariantsusedInCurrentRefinement;
        wereInvariantsusedInCurrentRefinement = false;

        return CounterexampleInfo.spurious();

      } else {
        // we have a real error
        logger.log(Level.FINEST, "Error trace is not spurious");
        errorPathProcessing.start();
        try {
          return pathChecker.handleFeasibleCounterexample(counterexample, allStatesTrace);
        } finally {
          errorPathProcessing.stop();
        }
      }

    } finally {
      totalRefinement.stop();
    }
  }

  /**
   * Check the given trace (or traces in the DAG) for feasibility and collect information why it is
   * feasible or why not.
   *
   * @param allStatesTrace a concrete path in the ARG.
   * @param abstractionStatesTrace the list of abstraction states along the path.
   * @param formulas the list of block formulas for the abstraction states along the path.
   * @param repeatedCounterexample whether the current counterexample was seen before.
   * @return information about the counterexample, for example a model (feasible CEX) or
   *     interpolants (infeasible CEX).
   */
  private CounterexampleTraceInfo checkCounterexample(
      final ARGPath allStatesTrace,
      final List<ARGState> abstractionStatesTrace,
      final BlockFormulas formulas,
      final boolean repeatedCounterexample)
      throws CPAException, InterruptedException {

    Preconditions.checkArgument(
        abstractionStatesTrace.size() == formulas.getSize(),
        "each abstraction state should have a block formula");
    Preconditions.checkArgument(
        abstractionStatesTrace.size() <= allStatesTrace.size(),
        "each abstraction state should have a state in the counterexample trace");

    // Set the atomic Predicates configuration in the RefinementStrategy
    if (strategy
        instanceof PredicateAbstractionRefinementStrategy predicateAbstractionRefinementStrategy) {
      predicateAbstractionRefinementStrategy.setUseAtomicPredicates(atomicInterpolants);
    }

    if (!repeatedCounterexample && (invariantsManager.addToPrecision() || usePathInvariants)) {
      // Compute invariants if desired, and if the counterexample is not a repeated one
      // (otherwise invariants for the same location didn't help before, so they won't help now).
      return performInvariantsRefinement(allStatesTrace, abstractionStatesTrace, formulas);

    } else if (useNewtonRefinement) {
      assert newtonManager.isPresent();
      if (!repeatedCounterexample) {
        try {
          logger.log(Level.FINEST, "Starting Newton-based refinement");
          return performNewtonRefinement(allStatesTrace, formulas);
        } catch (RefinementFailedException e) {
          if (e.getReason() == Reason.SequenceOfAssertionsToWeak
              && newtonManager.orElseThrow().fallbackToInterpolation()) {
            logger.log(
                Level.FINEST,
                "Fallback from Newton-based refinement to interpolation-based refinement");
            return performInterpolatingRefinement(allStatesTrace, abstractionStatesTrace, formulas);
          } else {
            throw e;
          }
        }
      } else {
        logger.log(
            Level.FINEST,
            "Fallback from Newton-based refinement to interpolation-based refinement");
        return performInterpolatingRefinement(allStatesTrace, abstractionStatesTrace, formulas);
      }
    } else if (useUCBRefinement) {
      logger.log(Level.FINEST, "Starting unsat-core-based refinement");
      return performUCBRefinement(allStatesTrace, abstractionStatesTrace, formulas);

    } else {
      logger.log(Level.FINEST, "Starting interpolation-based refinement.");
      return performInterpolatingRefinement(allStatesTrace, abstractionStatesTrace, formulas);
    }
  }

  private CounterexampleTraceInfo performInterpolatingRefinement(
      final ARGPath allStatesTrace,
      final List<ARGState> abstractionStatesTrace,
      final BlockFormulas formulas)
      throws CPAException, InterruptedException {

    if (!useVGuide || vocabularyGuide == null || vocabularyGuide.isEmpty()) {
      return interpolationManager.buildCounterexampleTrace(
          formulas, ImmutableList.copyOf(abstractionStatesTrace), Optional.of(allStatesTrace));
    }

    b5Entailed.clear();
    // Stock CPAchecker refinement first
    CounterexampleTraceInfo result0 =
        interpolationManager.buildCounterexampleTrace(
            formulas, ImmutableList.copyOf(abstractionStatesTrace), Optional.of(allStatesTrace));
    if (!result0.isSpurious()) {
      return result0;
    }

    vInjectionAttempts++;

    // --- V-guided predicate injection (strengthen interpolants) ---
    List<AbstractState> absStates = ImmutableList.copyOf(abstractionStatesTrace);
    List<BooleanFormula> interpolants = new ArrayList<>(result0.getInterpolants());
    BooleanFormulaManagerView bfmgr = fmgr.getBooleanFormulaManager();
    Set<String> encodedVars = new HashSet<>(fmgr.extractVariableNames(formulas.getFormulas().get(0)));
    for (int i = 1; i < formulas.getFormulas().size(); i++) {
      encodedVars.addAll(fmgr.extractVariableNames(formulas.getFormulas().get(i)));
    }
    lastEncodedVars = encodedVars;

    int vAdded = 0;
    int n = Math.min(absStates.size(), interpolants.size());
    for (int i = 0; i < n; i++) {
      CFANode node = extractLocation(absStates.get(i));
      if (node == null) {
        continue;
      }
      String locKey = locationKeyForNode(node);
      if (locKey == null) {
        continue;
      }
      List<BooleanFormula> locPreds = vocabularyGuide.getFormulasForLocation(locKey, encodedVars);
      if (locPreds.isEmpty()) {
        continue;
      }
      BooleanFormula blockFormula = formulas.getFormulas().get(i);
      List<BooleanFormula> valid = new ArrayList<>();
      for (BooleanFormula p : locPreds) {
        if (bfmgr.isTrue(p) || bfmgr.isFalse(p)) {
          vSmtFailed++;
          continue;
        }
        try (ProverEnvironment pe =
            solver.newProverEnvironment(ProverOptions.GENERATE_MODELS)) {
          pe.push(blockFormula);
          pe.push(bfmgr.not(p));
          if (pe.isUnsat()) {
            valid.add(p);
            vSmtValidated++;
            b5Entailed.computeIfAbsent(node, k -> new LinkedHashSet<>()).add(p);
            logger.log(Level.INFO, "V-FATE [", locKey, "] ENTAILED: ",
                fmgr.dumpFormula(p).toString().replace("\n", " "));
          } else {
            vSmtFailed++;
            vAbstractionCandidates++;
            pendingAbstractionCandidates
                .computeIfAbsent(node, k -> new LinkedHashSet<>()).add(p);
            v4BlockContext.putIfAbsent(node, blockFormula);
            logger.log(Level.INFO, "V-FATE [", locKey, "] ABSTRACTION-CANDIDATE: ",
                fmgr.dumpFormula(p).toString().replace("\n", " "));
          }
        } catch (SolverException se) {
          vSmtFailed++;
          logger.log(Level.INFO, "V-FATE [", locKey, "] PARSE-ERROR: ",
              fmgr.dumpFormula(p).toString().replace("\n", " "));
        }
      }
      if (!valid.isEmpty()) {
        BooleanFormula conj = valid.get(0);
        for (int j = 1; j < valid.size(); j++) {
          conj = bfmgr.and(conj, valid.get(j));
        }
        interpolants.set(i, bfmgr.and(interpolants.get(i), conj));
        vAdded++;
      }
    }

    if (vAdded == 0) {
      vFallbacks++;
      triggerVocabularyUpdate(formulas.getFormulas());
      logger.log(Level.FINE, "No V predicates validated; using stock interpolants only.");
      return result0;
    }

    vInjectionSuccesses++;
    if (llmConnector != null) {
      llmConnector.onGoodScore();
    }

    logger.log(
        Level.INFO,
        "V-injected ",
        vAdded,
        " predicates into ",
        vAdded,
        " interpolants");
    return CounterexampleTraceInfo.infeasible(interpolants);
  }

  private void triggerVocabularyUpdate(List<BooleanFormula> traceFormulas) {
    if (llmConnector == null) {
      return;
    }
    for (BooleanFormula f : traceFormulas) {
      llmConnector.addTrace(fmgr.dumpFormula(f).toString());
    }
    llmConnector.onShortfall();
  }

  private void injectAbstractionCandidates(ARGReachedSet pReached) {
    if (vPrecisionInjected) return;
    if (predAbsManager == null) return;

    if ("1".equals(System.getenv("VGUIDE_INJECT_TOP1_PARITY_ONCE"))) {
      injectTop1ParityOnce(pReached);
      vPrecisionInjected = true;
      return;
    }

    if ("1".equals(System.getenv("VGUIDE_INJECT_ASSERTION_ORACLE_ONCE"))) {
      injectAssertionOracleOnce(pReached);
      vPrecisionInjected = true;
      return;
    }

    if ("1".equals(System.getenv("VGUIDE_INJECT_REPAIR_PREDICATES_ONCE"))) {
      injectRepairPredicatesOnce(pReached);
      vPrecisionInjected = true;
      return;
    }

    if (!"1".equals(System.getenv("VGUIDE_INJECT_PRECISION"))) {
      String topK = System.getenv("VGUIDE_PRECISION_TOP_K");
      if (topK != null && !topK.isBlank() && !pendingAbstractionCandidates.isEmpty()) {
        if ("1".equals(System.getenv("VGUIDE_PRECISION_V4"))) {
          injectRankedTopKV4(pReached, Integer.parseInt(topK));
        } else {
          injectRankedTopK(pReached, Integer.parseInt(topK));
        }
        vPrecisionInjected = true;
      } else {
        pendingAbstractionCandidates.clear();
      }
      return;
    }

    if (pendingAbstractionCandidates.isEmpty()) return;
    Map<CFANode, Set<BooleanFormula>> candidates = new LinkedHashMap<>(pendingAbstractionCandidates);
    pendingAbstractionCandidates.clear();

    AbstractState firstState = pReached.asReachedSet().getFirstState();
    if (firstState == null) return;
    Precision currentPrec = pReached.asReachedSet().getPrecision(firstState);
    PredicatePrecision currentPredPrec =
        Precisions.extractPrecisionByType(currentPrec, PredicatePrecision.class);
    if (currentPredPrec == null) return;

    int total = 0;
    List<Map.Entry<CFANode, AbstractionPredicate>> entries = new ArrayList<>();
    for (var entry : candidates.entrySet()) {
      CFANode node = entry.getKey();
      for (BooleanFormula bf : entry.getValue()) {
        try {
          entries.add(Map.entry(node, predAbsManager.getPredicateFor(bf)));
          total++;
        } catch (Exception e) {
          logger.logDebugException(e, "Failed to create AbstractionPredicate");
        }
      }
      logger.log(Level.INFO, "V precision-candidate at N", node.getNodeNumber(),
          ": ", entry.getValue().size(), " unique predicates");
    }

    if (entries.isEmpty()) return;

    PredicatePrecision newPredPrec = currentPredPrec.addLocalPredicates(entries);
    pReached.updatePrecisionGlobally(
        newPredPrec, Predicates.instanceOf(PredicatePrecision.class));

    logger.log(Level.INFO, "V precision-injected ", total,
        " abstraction-candidates as local predicates");
  }

  private void injectTop1ParityOnce(ARGReachedSet pReached) {
    if (pendingAbstractionCandidates.isEmpty()) {
      logger.log(Level.WARNING, "V top1 parity: no abstraction candidates available yet");
      return;
    }
    AbstractState firstState = pReached.asReachedSet().getFirstState();
    if (firstState == null) return;
    Precision currentPrec = pReached.asReachedSet().getPrecision(firstState);
    PredicatePrecision currentPredPrec =
        Precisions.extractPrecisionByType(currentPrec, PredicatePrecision.class);
    if (currentPredPrec == null) return;

    List<AbstractionPredicate> absPreds = new ArrayList<>();
    boolean onlyFirst = "1".equals(System.getenv("VGUIDE_TOP1_ONLY_EQ"));
    int count = 0;
    for (var entry : pendingAbstractionCandidates.entrySet()) {
      for (BooleanFormula bf : entry.getValue()) {
        if (onlyFirst && count > 0) continue;
        try {
          absPreds.add(predAbsManager.getPredicateFor(bf));
          count++;
        } catch (Exception e) {
          logger.logDebugException(e, "V top1 parity: AbstractionPredicate failed");
        }
      }
    }
    pendingAbstractionCandidates.clear();
    if (absPreds.isEmpty()) return;

    PredicatePrecision newPredPrec = currentPredPrec.addGlobalPredicates(absPreds);
    pReached.updatePrecisionGlobally(
        newPredPrec, p -> p instanceof PredicatePrecision);

    logger.log(Level.WARNING, "V one-shot precision injected ",
        absPreds.size(), " abstraction-candidates (first batch, once)");
  }

  private void injectAssertionOracleOnce(ARGReachedSet pReached) {
    String rawPred = System.getenv("VGUIDE_ASSERTION_PREDICATE");
    if (rawPred == null || rawPred.isBlank()) {
      // Fallback: use pending abstraction candidates (backward compat)
      if (pendingAbstractionCandidates.isEmpty()) {
        logger.log(Level.WARNING, "V assertion oracle: no predicate set, no candidates available");
        return;
      }
      injectTop1ParityOnce(pReached);
      return;
    }

    BooleanFormula assertionPred = VocabularyGuide.parsePredicate(
        rawPred, fmgr, lastEncodedVars);
    if (assertionPred == null) {
      logger.log(Level.WARNING, "V assertion oracle: parse failed for: ", rawPred,
          " encodedVars=", lastEncodedVars.size());
      return;
    }

    AbstractState firstState = pReached.asReachedSet().getFirstState();
    if (firstState == null) return;
    Precision currentPrec = pReached.asReachedSet().getPrecision(firstState);
    PredicatePrecision currentPredPrec =
        Precisions.extractPrecisionByType(currentPrec, PredicatePrecision.class);
    if (currentPredPrec == null) return;

    AbstractionPredicate absPred;
    try {
      absPred = predAbsManager.getPredicateFor(assertionPred);
    } catch (Exception e) {
      logger.log(Level.WARNING, "V assertion oracle: AbstractionPredicate creation failed");
      return;
    }

    PredicatePrecision newPredPrec = currentPredPrec.addGlobalPredicates(List.of(absPred));
    pReached.updatePrecisionGlobally(
        newPredPrec, p -> p instanceof PredicatePrecision);

    logger.log(Level.WARNING, "V assertion oracle precision injected (1 predicate)");
    logger.log(Level.WARNING, "  predicate: ", this.fmgr.dumpFormula(assertionPred));
  }

  private void injectRepairPredicatesOnce(ARGReachedSet pReached) {
    String repairFile = System.getenv("VGUIDE_REPAIR_CANDIDATES_FILE");
    if (repairFile == null || repairFile.isBlank()) {
      logger.log(Level.WARNING, "V B4 repair: VGUIDE_REPAIR_CANDIDATES_FILE not set");
      return;
    }
    java.nio.file.Path path = java.nio.file.Path.of(repairFile);
    if (!java.nio.file.Files.exists(path)) {
      logger.log(Level.WARNING, "V B4 repair: file not found: ", repairFile);
      return;
    }
    String jsonText;
    try {
      jsonText = java.nio.file.Files.readString(path);
    } catch (Exception e) {
      logger.log(Level.WARNING, "V B4 repair: read failed: ", e.getMessage());
      return;
    }

    // Parse JSON: {"location": ["pred1", "pred2", ...], ...}
    Map<String, List<String>> locPreds;
    try {
      locPreds = LLMConnector.parseLocationPredicates(jsonText);
    } catch (Exception e) {
      logger.log(Level.WARNING, "V B4 repair: JSON parse failed: ", e.getMessage());
      return;
    }
    if (locPreds.isEmpty()) {
      logger.log(Level.WARNING, "V B4 repair: no predicates in file");
      return;
    }

    // Parse predicates with encoded variable names
    int parsed = 0;
    int failed = 0;
    List<BooleanFormula> validPreds = new ArrayList<>();
    for (var entry : locPreds.entrySet()) {
      for (String text : entry.getValue()) {
        BooleanFormula f = VocabularyGuide.parsePredicate(text, fmgr, lastEncodedVars);
        if (f != null) {
          validPreds.add(f);
          parsed++;
        } else {
          failed++;
        }
      }
    }

    logger.log(Level.INFO, "V B4 repair: parsed ", parsed, " predicates, ", failed, " failed");

    if (validPreds.isEmpty()) return;

    AbstractState firstState = pReached.asReachedSet().getFirstState();
    if (firstState == null) return;
    Precision currentPrec = pReached.asReachedSet().getPrecision(firstState);
    PredicatePrecision currentPredPrec =
        Precisions.extractPrecisionByType(currentPrec, PredicatePrecision.class);
    if (currentPredPrec == null) return;

    List<AbstractionPredicate> absPreds = new ArrayList<>();
    for (BooleanFormula bf : validPreds) {
      try {
        absPreds.add(predAbsManager.getPredicateFor(bf));
      } catch (Exception e) {
        logger.logDebugException(e, "V B4 repair: AbstractionPredicate failed");
      }
    }

    int topK = 5;
    try { topK = Integer.parseInt(System.getenv().getOrDefault("VGUIDE_B4_REPAIR_TOP_K", "5")); }
    catch (NumberFormatException ex) { logger.logDebugException(ex, "VGUIDE_B4_REPAIR_TOP_K parse failed"); }
    if (absPreds.size() > topK) {
      absPreds = absPreds.subList(0, topK);
    }

    PredicatePrecision newPredPrec = currentPredPrec.addGlobalPredicates(absPreds);
    pReached.updatePrecisionGlobally(
        newPredPrec, p -> p instanceof PredicatePrecision);

    logger.log(Level.WARNING, "V B4 repair injected ", absPreds.size(),
        " predicates (from ", validPreds.size(), " candidates, top-", topK, ")");
  }

  private void injectRankedTopK(ARGReachedSet pReached, int k) {
    if (pendingAbstractionCandidates.isEmpty()) return;
    AbstractState firstState = pReached.asReachedSet().getFirstState();
    if (firstState == null) return;
    Precision currentPrec = pReached.asReachedSet().getPrecision(firstState);
    PredicatePrecision currentPredPrec =
        Precisions.extractPrecisionByType(currentPrec, PredicatePrecision.class);
    if (currentPredPrec == null) return;

    // Collect all candidates with their formula text for ranking
    record Scored(AbstractionPredicate pred, int score) {}
    List<Scored> scored = new ArrayList<>();
    for (var entry : pendingAbstractionCandidates.entrySet()) {
      for (BooleanFormula bf : entry.getValue()) {
        try {
          AbstractionPredicate ap = predAbsManager.getPredicateFor(bf);
          String text = fmgr.dumpFormula(bf).toString();
           int s = 0;
           // Relational predicate (>1 variable): +3
           Set<String> vars = fmgr.extractVariableNames(bf);
           if (vars.size() >= 2) s += 3;
           // Contains mod: +2
           if (text.contains("bvurem") || text.contains("mod")) s += 2;
           // Accumulator relation (contains *): +3
           if (text.contains("bvmul") || text.contains("*")) s += 3;
           // Shorter formula: +1
           if (text.length() < 400) s += 1;
           // Loop-head location: +1
           if (entry.getKey().getFunctionName() != null) s += 1;
          scored.add(new Scored(ap, s));
        } catch (Exception e) {
          logger.logDebugException(e, "V ranked top-k: AbstractionPredicate failed");
        }
      }
    }
    pendingAbstractionCandidates.clear();
    if (scored.isEmpty()) return;

    // Sort by score descending, take top K
    scored.sort((a, b) -> Integer.compare(b.score, a.score));
    List<AbstractionPredicate> selected = new ArrayList<>();
    for (int i = 0; i < Math.min(k, scored.size()); i++) {
      selected.add(scored.get(i).pred);
    }

    PredicatePrecision newPredPrec = currentPredPrec.addGlobalPredicates(selected);
    pReached.updatePrecisionGlobally(
        newPredPrec, p -> p instanceof PredicatePrecision);

    logger.log(Level.WARNING, "V ranked top-", k, " precision injected ",
        selected.size(), " predicates (from ", scored.size(), " candidates)");
  }

  private void injectRankedTopKV4(ARGReachedSet pReached, int k) {
    if (pendingAbstractionCandidates.isEmpty()) return;
    AbstractState firstState = pReached.asReachedSet().getFirstState();
    if (firstState == null) return;
    Precision currentPrec = pReached.asReachedSet().getPrecision(firstState);
    PredicatePrecision currentPredPrec =
        Precisions.extractPrecisionByType(currentPrec, PredicatePrecision.class);
    if (currentPredPrec == null) return;

    List<AbstractionPredicate> selected = new ArrayList<>();
    int totalCandidates = 0;
    int totalScored = 0;
    int totalRejected = 0;
    StringBuilder scoreLog = new StringBuilder();

    for (var entry : pendingAbstractionCandidates.entrySet()) {
      CFANode node = entry.getKey();
      BooleanFormula blockFormula = v4BlockContext.get(node);
      boolean isLoopHead = node.getFunctionName() != null;
      List<BooleanFormula> candList = new ArrayList<>(entry.getValue());
      totalCandidates += candList.size();

      if (blockFormula == null) {
        logger.log(Level.FINE, "V4: no block context for N", node.getNodeNumber(), ", fallback to ranker");
        for (BooleanFormula bf : candList) {
          try {
            int s = 1;
            String text = fmgr.dumpFormula(bf).toString();
            Set<String> vars = fmgr.extractVariableNames(bf);
            if (vars.size() >= 2) s += 3;
            if (text.contains("bvurem") || text.contains("mod")) s += 2;
            if (text.contains("bvmul") || text.contains("*")) s += 3;
            if (text.length() < 400) s += 1;
            if (isLoopHead) s += 1;
            AbstractionPredicate ap = predAbsManager.getPredicateFor(bf);
            selected.add(ap);
            totalScored++;
            scoreLog.append("N").append(node.getNodeNumber()).append(" fallback=").append(s).append(" ");
          } catch (Exception e) {
            totalRejected++;
            logger.logDebugException(e, "V4: AbstractionPredicate failed");
          }
        }
        continue;
      }

      PredicateScorer.RankedPredicates ranked =
          v4Scorer.scoreAndRank(blockFormula, candList, fmgr, isLoopHead, k);

      totalScored += ranked.allScores().size();
      totalRejected += ranked.rejected().size();

      for (var scoredEntry : ranked.allScores().entrySet()) {
        scoreLog.append("N").append(node.getNodeNumber())
            .append("=").append(scoredEntry.getValue()).append(" ");
      }
      for (BooleanFormula rejectedBf : ranked.rejected()) {
        String rText = fmgr.dumpFormula(rejectedBf).toString().replace("\n", " ");
        int maxLen = 80;
        scoreLog.append("N").append(node.getNodeNumber())
            .append(" REJECT(").append(rText.substring(0, Math.min(rText.length(), maxLen)))
            .append(") ");
      }

      for (BooleanFormula bf : ranked.predicates()) {
        try {
          AbstractionPredicate ap = predAbsManager.getPredicateFor(bf);
          selected.add(ap);
        } catch (Exception e) {
          logger.logDebugException(e, "V4: AbstractionPredicate failed");
        }
      }
    }

    pendingAbstractionCandidates.clear();
    v4BlockContext.clear();

    if (selected.isEmpty()) return;

    PredicatePrecision newPredPrec = currentPredPrec.addGlobalPredicates(selected);
    pReached.updatePrecisionGlobally(
        newPredPrec, p -> p instanceof PredicatePrecision);

    logger.log(Level.WARNING, "V4 scored top-", k, " precision injected ",
        selected.size(), " predicates (scored=", totalScored, " rejected=",
        totalRejected, " candidates=", totalCandidates, ")");
    logger.log(Level.INFO, "V4 scores: ", scoreLog.toString());
  }

  private @Nullable String locationKeyForNode(CFANode node) {
    String target = "N" + node.getNodeNumber();
    for (String loc : vocabularyGuide.getAllLocations()) {
      if (loc.startsWith(target)) {
        return loc;
      }
    }
    return null;
  }

  private CounterexampleTraceInfo performInvariantsRefinement(
      final ARGPath allStatesTrace,
      final List<ARGState> abstractionStatesTrace,
      final BlockFormulas formulas)
      throws CPAException, InterruptedException {

    CounterexampleTraceInfo counterexample =
        interpolationManager.buildCounterexampleTraceWithoutInterpolation(
            formulas, Optional.of(allStatesTrace));

    // if error is spurious refine
    if (counterexample.isSpurious()) {
      logger.log(Level.FINEST, "Error trace is spurious, refining the abstraction");

      // add invariant precision increment if necessary
      List<BooleanFormula> precisionIncrement = new ArrayList<>();
      if (invariantsManager.addToPrecision()) {
        precisionIncrement = addInvariants(abstractionStatesTrace);
      }

      if (usePathInvariants) {
        precisionIncrement =
            addPathInvariants(allStatesTrace, abstractionStatesTrace, precisionIncrement);
      }

      if (precisionIncrement.isEmpty()) {
        // fall-back to interpolation
        logger.log(
            Level.FINEST,
            "Starting interpolation-based refinement because invariant generation was not"
                + " successful.");
        return performInterpolatingRefinement(allStatesTrace, abstractionStatesTrace, formulas);

      } else {
        wereInvariantsusedInCurrentRefinement = true;
        return CounterexampleTraceInfo.infeasible(precisionIncrement);
      }

    } else {
      return counterexample;
    }
  }

  private CounterexampleTraceInfo performNewtonRefinement(
      final ARGPath pAllStatesTrace, final BlockFormulas pFormulas)
      throws CPAException, InterruptedException {
    // Delegate the refinement task to the NewtonManager
    return newtonManager.orElseThrow().buildCounterexampleTrace(pAllStatesTrace, pFormulas);
  }

  private CounterexampleTraceInfo performUCBRefinement(
      final ARGPath allStatesTrace,
      final List<ARGState> pAbstractionStatesTrace,
      final BlockFormulas pFormulas)
      throws CPAException, InterruptedException {

    assert ucbManager.isPresent();
    return ucbManager
        .orElseThrow()
        .buildCounterexampleTrace(allStatesTrace, pAbstractionStatesTrace, pFormulas);
  }

  private List<BooleanFormula> addInvariants(final List<ARGState> abstractionStatesTrace)
      throws InterruptedException {
    List<BooleanFormula> precisionIncrement = new ArrayList<>();
    boolean invIsTriviallyTrue = true;

    // we do not need the last state from the trace, so we exclude it here
    for (ARGState state : from(abstractionStatesTrace).limit(abstractionStatesTrace.size() - 1)) {
      CFANode location = extractLocation(state);
      Optional<CallstackStateEqualsWrapper> callstack = extractOptionalCallstackWraper(state);
      BooleanFormula inv =
          invariantsManager.getInvariantFor(location, callstack, fmgr, pfmgr, null);
      if (invIsTriviallyTrue
          && !fmgr.getBooleanFormulaManager().isTrue(inv)
          && (!lastInvariantForNode.containsKey(location)
              || !lastInvariantForNode.get(location).equals(inv))) {
        invIsTriviallyTrue = false;
        lastInvariantForNode.put(location, inv);
      }
      precisionIncrement.add(inv);
    }
    assert precisionIncrement.size() == abstractionStatesTrace.size() - 1;

    if (invIsTriviallyTrue) {
      precisionIncrement.clear();
    }
    return precisionIncrement;
  }

  private List<BooleanFormula> addPathInvariants(
      final ARGPath allStatesTrace,
      final List<ARGState> abstractionStatesTrace,
      List<BooleanFormula> precisionIncrement) {
    Set<Loop> loopsInPath = getRelevantLoops(allStatesTrace);
    if (!loopsInPath.isEmpty()) {
      List<BooleanFormula> pathInvariants =
          invariantsManager.findPathInvariants(
              allStatesTrace, abstractionStatesTrace, loopsInPath, pfmgr, solver);

      if (precisionIncrement.isEmpty()) {
        precisionIncrement = pathInvariants;

      } else {
        Preconditions.checkState(precisionIncrement.size() == pathInvariants.size());

        Iterator<BooleanFormula> invIt = precisionIncrement.iterator();
        Iterator<BooleanFormula> pathInvIt = pathInvariants.iterator();
        List<BooleanFormula> mergeFormulas = new ArrayList<>();
        while (invIt.hasNext()) {
          mergeFormulas.add(fmgr.getBooleanFormulaManager().and(invIt.next(), pathInvIt.next()));
        }
        precisionIncrement = mergeFormulas;
      }

    } else {
      logger.log(
          Level.WARNING, "Path invariants could not be computed, loop information is missing");
    }
    return precisionIncrement;
  }

  /** This method returns the set of loops which are relevant for the given ARGPath. */
  private Set<Loop> getRelevantLoops(final ARGPath allStatesTrace) {
    // in the case we have no loop informaion we cannot find loops
    if (loopFinder == null) {
      return ImmutableSet.of();
    }

    loopFinder.reset();

    PathIterator pathIt = allStatesTrace.fullPathIterator();
    while (pathIt.hasNext()) {
      if (pathIt.isPositionWithState()) {
        loopFinder.visit(pathIt.getAbstractState(), pathIt.getOutgoingEdge(), null);
      } else {
        loopFinder.visit(pathIt.getPreviousAbstractState(), pathIt.getOutgoingEdge(), null);
      }
      pathIt.advance();
    }

    return loopFinder.getRelevantLoops().keySet();
  }

  /**
   * This method determines whether to perform refinement selection.
   *
   * @return whether refinement selection has to be performed
   */
  private boolean isRefinementSelectionEnabled() {
    return !prefixPreference.equals(PrefixSelector.NO_SELECTION);
  }

  static List<ARGState> filterAbstractionStates(ARGPath pPath) {
    List<ARGState> result =
        from(pPath.asStatesList())
            .skip(1)
            .filter(PredicateAbstractState::containsAbstractionState)
            .toList();

    // This assertion does not hold anymore for slicing abstractions.
    // TODO: Find a way to still check this for when we do not use slicing!
    // assert from(result).allMatch(state -> state.getParents().size() <= 1)
    //    : "PredicateCPARefiner expects abstraction states to have only one parent, but at least
    // one state has more.";

    assert Objects.equals(pPath.getLastState(), result.getLast());
    return result;
  }

  /**
   * Get the block formulas from a path.
   *
   * @param path A list of all abstraction elements
   * @param initialState The initial element of the analysis (= the root element of the ARG)
   * @return A list of block formulas for this path.
   */
  private BlockFormulas getFormulasForPath(List<ARGState> path, ARGState initialState)
      throws CPATransferException, InterruptedException {
    getFormulasForPathTime.start();
    try {
      return blockFormulaStrategy.getFormulasForPath(initialState, path);
    } finally {
      getFormulasForPathTime.stop();
    }
  }

  private BlockFormulas performRefinementSelection(
      final ARGPath pAllStatesTrace, final List<ARGState> pAbstractionStatesTrace)
      throws InterruptedException, CPAException {

    prefixExtractionTime.start();
    List<InfeasiblePrefix> infeasiblePrefixes =
        prefixProvider.extractInfeasiblePrefixes(pAllStatesTrace);
    prefixExtractionTime.stop();

    totalPrefixes.setNextValue(infeasiblePrefixes.size());

    if (infeasiblePrefixes.isEmpty()) {
      return getFormulasForPath(pAbstractionStatesTrace, pAllStatesTrace.getFirstState());
    } else {
      prefixSelectionTime.start();
      InfeasiblePrefix selectedPrefix =
          prefixSelector.selectSlicedPrefix(prefixPreference, infeasiblePrefixes);
      prefixSelectionTime.stop();

      List<BooleanFormula> formulas = new ArrayList<>(selectedPrefix.getPathFormulae());
      while (formulas.size() < pAbstractionStatesTrace.size()) {
        formulas.add(fmgr.getBooleanFormulaManager().makeTrue());
      }

      return new BlockFormulas(formulas);
    }
  }

  @Override
  public void collectStatistics(Collection<Statistics> pStatsCollection) {
    pStatsCollection.add(new Stats());
    if (strategy instanceof StatisticsProvider statisticsProvider) {
      statisticsProvider.collectStatistics(pStatsCollection);
    }
    if (useNewtonRefinement) {
      newtonManager.orElseThrow().collectStatistics(pStatsCollection);
    }
  }

  private class Stats implements Statistics {

    @Override
    public void printStatistics(PrintStream out, Result result, UnmodifiableReachedSet reached) {
      StatisticsWriter w0 = writingStatisticsTo(out);

      int numberOfRefinements = totalRefinement.getUpdateCount();
      w0.put("Number of predicate refinements", totalRefinement.getUpdateCount());
      StatisticsWriter w1 = w0.beginLevel();
      if (numberOfRefinements > 0) {
        w0.put(totalPathLength).put(totalPrefixes).spacer().put(totalRefinement);

        w1.put(getFormulasForPathTime);
        if (isRefinementSelectionEnabled()) {
          w1.put(prefixExtractionTime);
          w1.put(prefixSelectionTime);
        }
      }

      if (vInjectionAttempts > 0) {
        w0.spacer();
        w0.put("V-injection attempts", vInjectionAttempts);
        StatisticsWriter wv = w0.beginLevel();
        wv.put("V-injection successes", vInjectionSuccesses);
        wv.put("V-injection fallbacks", vFallbacks);
        wv.put("V SMT-validated predicates", vSmtValidated);
        wv.put("V SMT-failed predicates", vSmtFailed);
        wv.put("V abstraction-candidate predicates", vAbstractionCandidates);
      }

      interpolationManager.printStatistics(w1);
      w1.putIfUpdatedAtLeastOnce(errorPathProcessing);

      dumpB4Context(result);
    }

    private void dumpB4Context(Result result) {
      String dumpDir = System.getenv("VGUIDE_B4_DUMP_CONTEXT");
      if (dumpDir == null || dumpDir.isBlank()) return;
      try {
        java.nio.file.Path dir = java.nio.file.Path.of(dumpDir);
        java.nio.file.Files.createDirectories(dir);
        StringBuilder json = new StringBuilder();
        json.append("{\n");
        json.append("  \"result\": \"").append(escapeJson(String.valueOf(result))).append("\",\n");
        json.append("  \"refinements\": ").append(totalRefinement.getUpdateCount()).append(",\n");
        json.append("  \"v_injection_attempts\": ").append(vInjectionAttempts).append(",\n");
        json.append("  \"v_injection_successes\": ").append(vInjectionSuccesses).append(",\n");
        json.append("  \"v_smt_validated\": ").append(vSmtValidated).append(",\n");
        json.append("  \"v_smt_failed\": ").append(vSmtFailed).append(",\n");
        json.append("  \"v_abstraction_candidates\": ").append(vAbstractionCandidates).append(",\n");
        json.append("  \"v_fallbacks\": ").append(vFallbacks).append(",\n");
        json.append("  \"vocabulary_size\": ").append(vocabularyGuide != null ? vocabularyGuide.size() : 0)
            .append(",\n");
        json.append("  \"vocabulary_entries\": [");
        if (vocabularyGuide != null) {
          boolean first = true;
          for (String loc : vocabularyGuide.getAllLocations()) {
            for (String pred : vocabularyGuide.getPredicateStringsForLocation(loc)) {
              if (!first) json.append(",");
              first = false;
              json.append("\n    {\"location\": \"").append(escapeJson(loc))
                  .append("\", \"predicate\": \"").append(escapeJson(pred)).append("\"}");
            }
          }
        }
        json.append("\n  ],\n");
        json.append("  \"abstraction_locations\": [");
        if (vocabularyGuide != null) {
          boolean first = true;
          for (String loc : vocabularyGuide.getAllLocations()) {
            if (!first) json.append(",");
            first = false;
            json.append("\n    \"").append(escapeJson(loc)).append("\"");
          }
        }
        json.append("\n  ]\n");
        json.append("}\n");
        java.nio.file.Files.writeString(dir.resolve("b4_context.json"), json.toString());
        logger.log(Level.INFO, "V B4 context dumped to ", dumpDir);
      } catch (Exception e) {
        logger.logDebugException(e, "V B4 context dump failed");
      }
    }

    private static String escapeJson(String s) {
      return s.replace("\\", "\\\\").replace("\"", "\\\"")
              .replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t");
    }

    @Override
    public String getName() {
      return "PredicateCPARefiner";
    }
  }
}
