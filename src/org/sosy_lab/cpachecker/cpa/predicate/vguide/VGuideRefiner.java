// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-FileCopyrightText: 2026 SSU-WEI HUANG <https://github.com/swear01>
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import java.io.IOException;
import java.util.Collection;
import java.util.Optional;
import org.sosy_lab.common.configuration.Configuration;
import org.sosy_lab.common.configuration.InvalidConfigurationException;
import org.sosy_lab.common.log.LogManager;
import org.sosy_lab.cpachecker.cfa.CFA;
import org.sosy_lab.cpachecker.core.counterexample.CounterexampleInfo;
import org.sosy_lab.cpachecker.core.interfaces.Statistics;
import org.sosy_lab.cpachecker.core.interfaces.StatisticsProvider;
import org.sosy_lab.cpachecker.cpa.arg.ARGBasedRefiner;
import org.sosy_lab.cpachecker.cpa.arg.ARGReachedSet;
import org.sosy_lab.cpachecker.cpa.arg.path.ARGPath;
import org.sosy_lab.cpachecker.cpa.predicate.PredicatePrecision;
import org.sosy_lab.cpachecker.exceptions.CPAException;
import org.sosy_lab.cpachecker.util.LoopStructure;
import org.sosy_lab.cpachecker.util.predicates.AbstractionManager;
import org.sosy_lab.cpachecker.util.predicates.smt.FormulaManagerView;

/** Minimal post-native-refinement decorator for VGuide. */
public final class VGuideRefiner implements ARGBasedRefiner, StatisticsProvider {

  private static final String EMPTY_CANDIDATES =
      "{\"schema_version\":\"vguide-candidates-v1\",\"candidates\":[]}";
  private static final String EMPTY_CANDIDATES_SHA256 =
      "950ec9013b84aed3afe9761427511822630e80cd5f009e837389312830deba94";

  private final ARGBasedRefiner delegate;
  private final VGuideAugmentor augmentor;
  private final VGuideStatistics statistics;
  private int refinement;

  public static ARGBasedRefiner wrapIfEnabled(
      ARGBasedRefiner delegate,
      Configuration config,
      LogManager logger,
      CFA cfa,
      Optional<LoopStructure> loopStructure,
      AbstractionManager abstractionManager,
      FormulaManagerView formulaManager)
      throws InvalidConfigurationException {
    VGuideOptions options = new VGuideOptions(config);
    if (!options.enabled()) {
      return delegate;
    }
    if (loopStructure.isEmpty()) {
      throw new InvalidConfigurationException(
          "VGuide requires CPAchecker loop-structure information");
    }
    CandidateProvider provider =
        options.provider() == VGuideOptions.Provider.EMPTY
            ? (agentRole, systemPrompt, contextJson) ->
                new CandidateProvider.ProviderResponse(
                    EMPTY_CANDIDATES, "deterministic-empty-provider", EMPTY_CANDIDATES_SHA256)
            : new OpenAiCompatibleCandidateProvider(
                options.endpoint(), options.model(), options.apiKey(), options.timeout());
    VGuideStatistics statistics = new VGuideStatistics(logger, options.telemetryFile());
    VGuideAugmentor augmentor =
        new VGuideAugmentor(
            new AgentPortfolio(provider, options.maxCandidatesPerAgent()),
            cfa,
            loopStructure.orElseThrow(),
            abstractionManager,
            formulaManager,
            options.counterexampleHistory(),
            statistics);
    return new VGuideRefiner(delegate, augmentor, statistics);
  }

  private VGuideRefiner(
      ARGBasedRefiner pDelegate, VGuideAugmentor pAugmentor, VGuideStatistics pStatistics) {
    delegate = pDelegate;
    augmentor = pAugmentor;
    statistics = pStatistics;
  }

  @Override
  public CounterexampleInfo performRefinementForPath(ARGReachedSet reached, ARGPath path)
      throws CPAException, InterruptedException {
    PredicatePrecision before = PredicatePrecision.unionOf(reached.asReachedSet().getPrecisions());
    CounterexampleInfo result = delegate.performRefinementForPath(reached, path);
    refinement++;
    if (result.isSpurious()) {
      PredicatePrecision after = PredicatePrecision.unionOf(reached.asReachedSet().getPrecisions());
      try {
        augmentor.augment(refinement, reached, path, before, after);
      } catch (InterruptedException e) {
        throw e;
      } catch (IOException e) {
        throw new CPAException("VGuide provider or response-schema failure", e);
      }
    }
    return result;
  }

  @Override
  public void collectStatistics(Collection<Statistics> statsCollection) {
    if (delegate instanceof StatisticsProvider provider) {
      provider.collectStatistics(statsCollection);
    }
    statsCollection.add(statistics);
  }
}
