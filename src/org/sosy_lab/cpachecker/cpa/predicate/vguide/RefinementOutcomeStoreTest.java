// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.truth.Truth.assertThat;

import org.junit.Test;

/** Bounded refinement-outcome store: two-phase recording, eviction, deterministic context. */
public class RefinementOutcomeStoreTest {

  @Test
  public void completedRoundRendersCompactLineWithNativeDelta() {
    RefinementOutcomeStore store = new RefinementOutcomeStore();
    store.recordStarted(1, 8, 12, 9);
    store.recordLlmOutcome(1, 3, 2, 1);
    store.recordCompleted(1, 5);

    String ctx = store.buildContext();
    assertThat(ctx).contains("round 1: visits=8 [heuristic] itp=12 blocks=9");
    assertThat(ctx).contains("llm=fired validated=3 injected=2 rejected=1");
    assertThat(ctx).contains("native_delta=+5");
  }

  @Test
  public void skippedLlmRoundHasNoLlmOutcome() {
    RefinementOutcomeStore store = new RefinementOutcomeStore();
    store.recordStarted(1, 2, 5, 4);
    store.recordCompleted(1, 3);

    String ctx = store.buildContext();
    assertThat(ctx).doesNotContain("llm=fired");
    assertThat(ctx).contains("native_delta=+3");
  }

  @Test
  public void boundedStoreEvictsOldestAndCountsOmitted() {
    RefinementOutcomeStore store = new RefinementOutcomeStore();
    for (int i = 1; i <= 6; i++) {
      store.recordStarted(i, i, 1, 1);
      store.recordCompleted(i, 1);
    }

    assertThat(store.snapshot().entries()).hasSize(RefinementOutcomeStore.MAX_ENTRIES);
    assertThat(store.snapshot().omitted()).isEqualTo(2);
    String ctx = store.buildContext();
    assertThat(ctx).contains("round 3:");
    assertThat(ctx).doesNotContain("round 2:");
    assertThat(ctx).contains("(older rounds omitted: 2)");
  }

  @Test
  public void unavailableFieldsAreMarkedNotInferred() {
    RefinementOutcomeStore store = new RefinementOutcomeStore();
    store.recordStarted(1, 1, 1, 1);
    store.recordCompleted(1, 0);

    String ctx = store.buildContext();
    assertThat(ctx).contains("unavailable: " + RefinementOutcomeStore.UNAVAILABLE);
    assertThat(RefinementOutcomeStore.UNAVAILABLE).contains("refiner_status");
    assertThat(RefinementOutcomeStore.UNAVAILABLE).contains("infeasible_prefix");
    assertThat(RefinementOutcomeStore.UNAVAILABLE).contains("arg_prune");
  }

  @Test
  public void completedLineForReturnsOnlyMatchingRound() {
    RefinementOutcomeStore store = new RefinementOutcomeStore();
    store.recordStarted(1, 1, 1, 1);
    store.recordCompleted(1, 2);
    store.recordStarted(2, 3, 1, 1);
    store.recordCompleted(2, 4);

    assertThat(store.completedLineFor(2)).contains("round 2:");
    assertThat(store.completedLineFor(2)).contains("native_delta=+4");
    assertThat(store.completedLineFor(9)).isNull();
  }

  @Test
  public void emptyStoreProducesNoContext() {
    assertThat(new RefinementOutcomeStore().buildContext()).isEmpty();
  }
}
