// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.truth.Truth.assertThat;

import org.junit.Test;

/** Bounded CE history: dedup, eviction, deterministic context and deltas. */
public class CeHistoryStoreTest {

  private static String ce(String head, int repeatCount, String relations) {
    return "{\"schema_version\":\"structured-ce-v1\",\"assertion\":\"x\",\"trace\":[{\"node\":1,"
        + "\"function\":\"f\",\"loop_head\":\""
        + head
        + "\",\"repeat_count\":"
        + repeatCount
        + "}],\"relations\":\""
        + relations
        + "\"}";
  }

  private static final String CE_A = ce("N12", 3, "i < n");
  private static final String CE_B = ce("N12", 8, "i < n");
  private static final String CE_C = ce("N15", 2, "k == i");

  @Test
  public void consecutiveIdenticalCesAreDeduplicatedIntoRepeatCount() {
    CeHistoryStore store = new CeHistoryStore();
    store.record(1, CE_A);
    store.record(2, CE_A);

    assertThat(store.snapshot().entries()).hasSize(1);
    assertThat(store.snapshot().entries().get(0).repeatCount()).isEqualTo(2);
    assertThat(store.snapshot().omitted()).isEqualTo(0);
  }

  @Test
  public void boundedStoreEvictsOldestDeterministically() {
    CeHistoryStore store = new CeHistoryStore();
    for (int i = 1; i <= 6; i++) {
      store.record(i, ce("N1" + i, 1, "r" + i));
    }

    CeHistoryStore.Snapshot snapshot = store.snapshot();
    assertThat(snapshot.entries()).hasSize(CeHistoryStore.MAX_ENTRIES);
    assertThat(snapshot.omitted()).isEqualTo(2);
    assertThat(snapshot.entries().get(0).refinementIndex()).isEqualTo(3);
    assertThat(snapshot.entries().get(snapshot.entries().size() - 1).refinementIndex()).isEqualTo(6);
  }

  @Test
  public void offModeProducesNoHistory() {
    CeHistoryStore store = new CeHistoryStore();
    store.record(1, CE_A);
    assertThat(store.buildContext(VGuideOptions.CeHistoryMode.OFF, CE_B)).isEmpty();
  }

  @Test
  public void latestModeShowsOnlyPreviousRound() {
    CeHistoryStore store = new CeHistoryStore();
    store.record(1, CE_A);
    store.record(2, CE_B);

    String context = store.buildContext(VGuideOptions.CeHistoryMode.LATEST, CE_C);
    assertThat(context).contains("refinement 2");
    assertThat(context).doesNotContain("refinement 1");
  }

  @Test
  public void boundedModeShowsEntriesWithoutDelta() {
    CeHistoryStore store = new CeHistoryStore();
    store.record(1, CE_A);
    store.record(2, CE_B);

    String context = store.buildContext(VGuideOptions.CeHistoryMode.BOUNDED, CE_C);
    assertThat(context).contains("refinement 1");
    assertThat(context).contains("refinement 2");
    assertThat(context).doesNotContain("Delta vs previous round");
  }

  @Test
  public void boundedWithDeltaShowsExplicitVisitChanges() {
    CeHistoryStore store = new CeHistoryStore();
    store.record(1, CE_A);

    String context = store.buildContext(VGuideOptions.CeHistoryMode.BOUNDED_WITH_DELTA, CE_B);
    assertThat(context).contains("Delta vs previous round");
    assertThat(context).contains("N12 visits 3 -> 8");
  }

  @Test
  public void deltaReportsNewLoopHead() {
    CeHistoryStore store = new CeHistoryStore();
    store.record(1, CE_A);

    String context = store.buildContext(VGuideOptions.CeHistoryMode.BOUNDED_WITH_DELTA, CE_C);
    assertThat(context).contains("new loop head N15 x2");
    assertThat(context).contains("head gone N12");
  }

  @Test
  public void deltaIsEmptyWhenUnchanged() {
    CeHistoryStore store = new CeHistoryStore();
    store.record(1, CE_A);

    String context = store.buildContext(VGuideOptions.CeHistoryMode.BOUNDED_WITH_DELTA, CE_A);
    assertThat(context).contains("(no change vs previous round)");
  }

  @Test
  public void contextIsBoundedInCharacters() {
    CeHistoryStore store = new CeHistoryStore();
    String longRelations = "r".repeat(3000);
    for (int i = 1; i <= 4; i++) {
      store.record(i, ce("N12", i, longRelations));
    }

    String context = store.buildContext(VGuideOptions.CeHistoryMode.BOUNDED_WITH_DELTA, CE_A);
    assertThat(context.length()).isAtMost(CeHistoryStore.MAX_CONTEXT_CHARS);
  }

  @Test
  public void sameSequenceProducesDeterministicContext() {
    CeHistoryStore a = new CeHistoryStore();
    CeHistoryStore b = new CeHistoryStore();
    for (int i = 1; i <= 5; i++) {
      String ce = i % 2 == 0 ? CE_B : CE_A;
      a.record(i, ce);
      b.record(i, ce);
    }

    assertThat(a.buildContext(VGuideOptions.CeHistoryMode.BOUNDED_WITH_DELTA, CE_C))
        .isEqualTo(b.buildContext(VGuideOptions.CeHistoryMode.BOUNDED_WITH_DELTA, CE_C));
  }
}
