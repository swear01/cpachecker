// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-FileCopyrightText: 2007-2020 Dirk Beyer <https://www.sosy-lab.org>
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate;

import static com.google.common.base.Preconditions.checkNotNull;
import static com.google.common.base.Preconditions.checkState;

import com.google.errorprone.annotations.CanIgnoreReturnValue;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.logging.Level;
import org.checkerframework.checker.nullness.qual.Nullable;
import org.sosy_lab.common.ShutdownNotifier;
import org.sosy_lab.common.configuration.Configuration;
import org.sosy_lab.common.configuration.InvalidConfigurationException;
import org.sosy_lab.common.configuration.Option;
import org.sosy_lab.common.configuration.Options;
import org.sosy_lab.common.log.LogManager;
import org.sosy_lab.cpachecker.cfa.CFA;
import org.sosy_lab.cpachecker.cfa.types.MachineModel;
import org.sosy_lab.cpachecker.core.interfaces.ConfigurableProgramAnalysis;
import org.sosy_lab.cpachecker.cpa.arg.ARGBasedRefiner;
import org.sosy_lab.cpachecker.util.CPAs;
import org.sosy_lab.cpachecker.util.LoopStructure;
import org.sosy_lab.cpachecker.util.predicates.PathChecker;
import org.sosy_lab.cpachecker.util.predicates.interpolation.InterpolationManager;
import org.sosy_lab.cpachecker.util.predicates.pathformula.PathFormulaManager;
import org.sosy_lab.cpachecker.util.predicates.smt.Solver;
import org.sosy_lab.cpachecker.util.refinement.PrefixProvider;
import org.sosy_lab.cpachecker.util.refinement.PrefixSelector;
import org.sosy_lab.cpachecker.util.variableclassification.VariableClassification;

/**
 * Factory for {@link PredicateCPARefiner}, the base class for most refiners for the PredicateCPA.
 */
@Options(prefix = "cpa.predicate.refinement")
public final class PredicateCPARefinerFactory {

  @Option(secure = true, description = "slice block formulas, experimental feature!")
  private boolean sliceBlockFormulas = false;

  @Option(
      secure = true,
      name = "graphblockformulastrategy",
      description = "BlockFormulaStrategy for graph-like ARGs (e.g. Slicing Abstractions)")
  private boolean graphBlockFormulaStrategy = false;

  @Option(
      secure = true,
      description =
          "use heuristic to extract predicates from the CFA statically on first refinement")
  private boolean performInitialStaticRefinement = false;

  @Option(
      secure = true,
      description =
          "Use LLM vocabulary to guide interpolation strategy selection. When enabled, computes"
              + " 6 interpolation strategies and selects the one best matching an LLM-maintained"
              + " predicate vocabulary V.")
  private boolean useVocabularyGuide = false;

  @Option(
      secure = true,
      description =
          "Subsumption weight for V-guided scoring (0..1). Remainder is variable overlap.")
  private double vocabularyGuideAlpha = 0.6;

  @Option(
      secure = true,
      description =
          "Threshold for CE-guided LLM update. When best strategy score < tau for"
              + " 3 consecutive refinements, LLM is asked to generate additional predicates.")
  private double vocabularyGuideTau = 0.2;

  private final PredicateCPA predicateCpa;

  private @Nullable BlockFormulaStrategy blockFormulaStrategy = null;

  /**
   * Create a factory instance.
   *
   * @param pCpa The CPA used for this whole analysis.
   * @throws InvalidConfigurationException If there is no PredicateCPA configured or if
   *     configuration is invalid.
   */
  @SuppressWarnings("options")
  public PredicateCPARefinerFactory(ConfigurableProgramAnalysis pCpa)
      throws InvalidConfigurationException {
    predicateCpa =
        CPAs.retrieveCPAOrFail(checkNotNull(pCpa), PredicateCPA.class, PredicateCPARefiner.class);
    predicateCpa.getConfiguration().inject(this);
  }

  /**
   * Ensure that {@link PredicateStaticRefiner} is not used. This is mostly useful for
   * configurations where static refinements do not make sense, or a the predicate refiner is used
   * as a helper for other refinements and should always generate interpolants.
   *
   * @return this
   * @throws InvalidConfigurationException If static refinements are enabled by the configuration.
   */
  @CanIgnoreReturnValue
  public PredicateCPARefinerFactory forbidStaticRefinements() throws InvalidConfigurationException {
    if (performInitialStaticRefinement) {
      throw new InvalidConfigurationException(
          "Static refinement is not supported with the configured refiner, "
              + "please turn cpa.predicate.refinement.useStaticRefinement off.");
    }
    return this;
  }

  /**
   * Let the refiners created by this factory instance use the given {@link BlockFormulaStrategy}.
   * May be called only once, but does not need to be called (in this case the configuration will
   * determine the used BlockFormulaStrategy).
   *
   * @return this
   */
  @CanIgnoreReturnValue
  public PredicateCPARefinerFactory setBlockFormulaStrategy(
      BlockFormulaStrategy pBlockFormulaStrategy) {
    checkState(blockFormulaStrategy == null);
    blockFormulaStrategy = checkNotNull(pBlockFormulaStrategy);
    return this;
  }

  /**
   * Create a {@link PredicateCPARefiner}. This factory can be reused afterward.
   *
   * @param pRefinementStrategy The refinement strategy to use.
   * @return A fresh instance.
   */
  public ARGBasedRefiner create(RefinementStrategy pRefinementStrategy)
      throws InvalidConfigurationException {
    checkNotNull(pRefinementStrategy);

    Configuration config = predicateCpa.getConfiguration();
    LogManager logger = predicateCpa.getLogger();
    ShutdownNotifier shutdownNotifier = predicateCpa.getShutdownNotifier();
    Solver solver = predicateCpa.getSolver();
    PathFormulaManager pfmgr = predicateCpa.getPathFormulaManager();

    CFA cfa = predicateCpa.getCfa();
    MachineModel machineModel = cfa.getMachineModel();
    Optional<VariableClassification> variableClassification = cfa.getVarClassification();
    Optional<LoopStructure> loopStructure = cfa.getLoopStructure();

    PredicateAbstractionManager predAbsManager = predicateCpa.getPredicateManager();
    PredicateCPAInvariantsManager invariantsManager = predicateCpa.getInvariantsManager();

    PrefixProvider prefixProvider =
        new PredicateBasedPrefixProvider(config, logger, solver, shutdownNotifier);
    PrefixSelector prefixSelector =
        new PrefixSelector(variableClassification, loopStructure, logger);

    PathChecker pathChecker =
        new PathChecker(config, logger, shutdownNotifier, machineModel, pfmgr, solver);

    BlockFormulaStrategy bfs;
    if (blockFormulaStrategy != null) {
      if (sliceBlockFormulas) {
        throw new InvalidConfigurationException(
            "Block-formula slicing is not supported with this refiner, "
                + "please turn cpa.predicate.refinement.sliceBlockFormula off.");
      }
      bfs = blockFormulaStrategy;
    } else {
      if (sliceBlockFormulas) {
        bfs = new BlockFormulaSlicer(pfmgr);
      } else if (graphBlockFormulaStrategy) {
        bfs = new SlicingAbstractionsBlockFormulaStrategy(solver, config, pfmgr);
      } else {
        bfs = new BlockFormulaStrategy();
      }
    }

    ARGBasedRefiner refiner;
    InterpolationManager primaryInterpolationManager;

    if (useVocabularyGuide) {
      String apiKey = System.getenv("OPENROUTER_API_KEY");
      if (apiKey == null || apiKey.isBlank()) {
        throw new InvalidConfigurationException(
            "useVocabularyGuide=true but OPENROUTER_API_KEY environment variable is not set");
      }

      logger.log(
          Level.INFO,
          "Vocabulary-guided CEGAR enabled (alpha=",
          vocabularyGuideAlpha,
          ", tau=",
          vocabularyGuideTau,
          ")");

      List<InterpolationManager> ims = new ArrayList<>(6);

      String[][] configs = {
        {"SEQ_CPACHECKER", "FORWARDS"},
        {"SEQ_CPACHECKER", "BACKWARDS"},
        {"SEQ_CPACHECKER", "ZIGZAG"},
        {"TREE_WELLSCOPED", "ZIGZAG"},
        {"TREE_NESTED", "ZIGZAG"},
        {"TREE_WELLSCOPED", "LOOP_FREE_FIRST"},
      };

      for (String[] cfg : configs) {
        Configuration c =
            Configuration.builder()
                .copyFrom(config)
                .setOption("cpa.predicate.refinement.strategy", cfg[0])
                .setOption("cpa.predicate.refinement.cexTraceCheckDirection", cfg[1])
                .build();
        ims.add(
            new InterpolationManager(
                pfmgr,
                solver,
                loopStructure,
                variableClassification,
                c,
                shutdownNotifier,
                logger));
      }

      primaryInterpolationManager = ims.getFirst();

      VocabularyGuide vg =
          new VocabularyGuide(solver, logger, vocabularyGuideAlpha, vocabularyGuideTau);
      LLMConnector llm =
          new LLMConnector(vg, solver, logger, shutdownNotifier, cfa, apiKey);

      llm.initializeVocab();
      llm.start();

      refiner =
          new PredicateCPARefiner(
              config,
              logger,
              loopStructure,
              bfs,
              solver,
              pfmgr,
              primaryInterpolationManager,
              pathChecker,
              prefixProvider,
              prefixSelector,
              invariantsManager,
              pRefinementStrategy,
              ims.subList(1, ims.size()),
              vg,
              llm);
    } else {
      primaryInterpolationManager =
          new InterpolationManager(
              pfmgr,
              solver,
              loopStructure,
              variableClassification,
              config,
              shutdownNotifier,
              logger);

      refiner =
          new PredicateCPARefiner(
              config,
              logger,
              loopStructure,
              bfs,
              solver,
              pfmgr,
              primaryInterpolationManager,
              pathChecker,
              prefixProvider,
              prefixSelector,
              invariantsManager,
              pRefinementStrategy,
              null,
              null,
              null);
    }

    if (performInitialStaticRefinement) {
      refiner =
          new PredicateStaticRefiner(
              config,
              logger,
              shutdownNotifier,
              solver,
              pfmgr,
              predAbsManager,
              bfs,
              primaryInterpolationManager,
              pathChecker,
              cfa,
              refiner);
    }

    return refiner;
  }
}
