// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-FileCopyrightText: 2026 Dirk Beyer <https://www.sosy-lab.org>
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.core.algorithm;

import static com.google.common.truth.Truth.assertThat;

import java.util.concurrent.atomic.AtomicInteger;
import org.junit.Test;
import org.sosy_lab.common.ShutdownNotifier;
import org.sosy_lab.common.configuration.Configuration;
import org.sosy_lab.common.log.LogManager;
import org.sosy_lab.cpachecker.cfa.CFA;
import org.sosy_lab.cpachecker.core.algorithm.Algorithm.AlgorithmStatus;
import org.sosy_lab.cpachecker.core.defaults.DummyTargetState;
import org.sosy_lab.cpachecker.core.defaults.SingletonAbstractState;
import org.sosy_lab.cpachecker.core.defaults.SingletonPrecision;
import org.sosy_lab.cpachecker.core.interfaces.StateSpacePartition;
import org.sosy_lab.cpachecker.core.reachedset.ReachedSet;
import org.sosy_lab.cpachecker.core.reachedset.ReachedSetFactory;
import org.sosy_lab.cpachecker.core.specification.Specification;
import org.sosy_lab.cpachecker.cpa.location.LocationCPA;
import org.sosy_lab.cpachecker.util.test.TestDataTools;

public class ArrayAbstractionAlgorithmTest {

  private final LogManager logger = LogManager.createTestLogManager();

  private Configuration configuration() throws Exception {
    return TestDataTools.configurationForTest()
        .setOption("arrayAbstraction.delegateAnalysis", "config/predicateAnalysis.properties")
        .setOption("arrayAbstraction.allowImprecision", "false")
        .setOption("arrayAbstraction.checkCounterexamples", "true")
        .setOption("arrayAbstraction.cfa.dot.export", "false")
        .setOption("arrayAbstraction.cfa.dot.file", "unused-array.dot")
        .setOption("arrayAbstraction.cfa.c.export", "false")
        .setOption("arrayAbstraction.cfa.c.file", "unused-array.c")
        .setOption("analysis.reachedSet", "NORMAL")
        .build();
  }

  private ArrayAbstractionAlgorithm createAlgorithm(Configuration pConfig, CFA pCfa)
      throws Exception {
    ArrayAbstractionAlgorithm algorithm =
        new ArrayAbstractionAlgorithm(
            pConfig, logger, ShutdownNotifier.createDummy(), Specification.alwaysSatisfied(), pCfa);
    assertThat(pConfig.getUnusedProperties())
        .containsNoneOf(
            "arrayAbstraction.delegateAnalysis", "arrayAbstraction.allowImprecision",
            "arrayAbstraction.checkCounterexamples", "arrayAbstraction.cfa.dot.export",
            "arrayAbstraction.cfa.dot.file", "arrayAbstraction.cfa.c.export",
            "arrayAbstraction.cfa.c.file", "analysis.stopAfterError");
    return algorithm;
  }

  private ReachedSet createReachedSet(Configuration pConfig, CFA pCfa) throws Exception {
    ReachedSet reached =
        new ReachedSetFactory(pConfig, logger)
            .createAndInitialize(
                LocationCPA.create(pCfa, pConfig),
                pCfa.getMainFunction(),
                StateSpacePartition.getDefaultPartition());
    reached.add(SingletonAbstractState.INSTANCE, SingletonPrecision.getInstance());
    return reached;
  }

  @Test
  public void defaultStopsAfterCounterexampleWithPendingStates() throws Exception {
    Configuration config = configuration();
    CFA cfa = TestDataTools.makeCFA("int main() { return 0; }");
    ReachedSet reached = createReachedSet(config, cfa);
    AtomicInteger calls = new AtomicInteger();
    Algorithm delegate =
        r -> {
          calls.incrementAndGet();
          r.popFromWaitlist();
          r.addNoWaitlist(
              DummyTargetState.withoutTargetInformation(), SingletonPrecision.getInstance());
          return AlgorithmStatus.SOUND_AND_PRECISE;
        };

    AlgorithmStatus status = createAlgorithm(config, cfa).runDelegateAlgorithm(delegate, reached);

    assertThat(calls.get()).isEqualTo(1);
    assertThat(reached.wasTargetReached()).isTrue();
    assertThat(reached.hasWaitingState()).isTrue();
    assertThat(status).isEqualTo(AlgorithmStatus.SOUND_AND_PRECISE);
  }

  @Test
  public void defaultAlsoPreservesAnIncompleteDelegateResult() throws Exception {
    Configuration config = configuration();
    CFA cfa = TestDataTools.makeCFA("int main() { return 0; }");
    ReachedSet reached = createReachedSet(config, cfa);
    AtomicInteger calls = new AtomicInteger();
    Algorithm delegate =
        r -> {
          calls.incrementAndGet();
          r.popFromWaitlist();
          return AlgorithmStatus.UNSOUND_AND_PRECISE;
        };

    AlgorithmStatus status = createAlgorithm(config, cfa).runDelegateAlgorithm(delegate, reached);

    assertThat(calls.get()).isEqualTo(1);
    assertThat(reached.wasTargetReached()).isFalse();
    assertThat(reached.hasWaitingState()).isTrue();
    assertThat(status).isEqualTo(AlgorithmStatus.UNSOUND_AND_PRECISE);
  }

  @Test
  public void configuredStopControlsExplorationAndPreservesEarlierStatus() throws Exception {
    for (boolean stopAfterError : new boolean[] {false, true}) {
      Configuration config =
          Configuration.builder()
              .copyFrom(configuration())
              .setOption("analysis.stopAfterError", Boolean.toString(stopAfterError))
              .build();
      CFA cfa = TestDataTools.makeCFA("int main() { return 0; }");
      ReachedSet reached = createReachedSet(config, cfa);
      AtomicInteger calls = new AtomicInteger();
      Algorithm delegate =
          r -> {
            r.popFromWaitlist();
            r.addNoWaitlist(
                DummyTargetState.withoutTargetInformation(), SingletonPrecision.getInstance());
            return calls.incrementAndGet() == 1
                ? AlgorithmStatus.UNSOUND_AND_IMPRECISE
                : AlgorithmStatus.SOUND_AND_PRECISE;
          };

      AlgorithmStatus status = createAlgorithm(config, cfa).runDelegateAlgorithm(delegate, reached);

      assertThat(calls.get()).isEqualTo(stopAfterError ? 1 : 2);
      assertThat(reached.wasTargetReached()).isTrue();
      assertThat(reached.hasWaitingState()).isEqualTo(stopAfterError);
      assertThat(status).isEqualTo(AlgorithmStatus.UNSOUND_AND_IMPRECISE);
    }
  }
}
