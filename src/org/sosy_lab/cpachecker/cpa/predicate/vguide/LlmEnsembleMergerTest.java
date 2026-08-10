// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.truth.Truth.assertThat;

import com.google.common.collect.ImmutableList;
import java.util.List;
import org.junit.Test;

public class LlmEnsembleMergerTest {

  private static LoopHeadCandidate candidate(String head, String predicate) {
    return new LoopHeadCandidate(ImmutableList.of(head), predicate, "", ImmutableList.of());
  }

  @Test
  public void mergeCandidates_dedupesAcrossDraws() {
    String a =
        """
        {"schema_version":"loop-head-candidate-v1","candidates":[{"loop_head":"N12","predicate":"(bvslt i n)"}]}
        """;
    String b =
        """
        {"schema_version":"loop-head-candidate-v1","candidates":[{"loop_head":"N12","predicate":"(bvslt i n)"},{"loop_head":"N12","predicate":"(bvsge i (_ bv0 32))"}]}
        """;

    assertThat(LlmEnsembleMerger.mergeCandidates(ImmutableList.of(a, b), new PredicateBudget(1, 16)))
        .containsExactly(candidate("N12", "(bvslt i n)"), candidate("N12", "(bvsge i (_ bv0 32))"));
  }

  @Test
  public void mergeCandidates_keepsSamePredicateAtDifferentHeads() {
    String a =
        """
        {"schema_version":"loop-head-candidate-v1","candidates":[
          {"loop_head":"N12","predicate":"(bvslt i n)"},
          {"loop_head":"N15","predicate":"(bvslt i n)"}
        ]}
        """;

    assertThat(LlmEnsembleMerger.mergeCandidates(ImmutableList.of(a), new PredicateBudget(1, 16)))
        .containsExactly(candidate("N12", "(bvslt i n)"), candidate("N15", "(bvslt i n)"));
  }

  @Test
  public void mergeCandidates_capsToPredicateBudget() {
    String a =
        """
        {"schema_version":"loop-head-candidate-v1","candidates":[
          {"loop_head":"N12","predicate":"(= x (_ bv0 32))"},
          {"loop_head":"N12","predicate":"(= x (_ bv1 32))"},
          {"loop_head":"N12","predicate":"(= x (_ bv2 32))"}
        ]}
        """;

    assertThat(LlmEnsembleMerger.mergeCandidates(ImmutableList.of(a), new PredicateBudget(1, 2)))
        .hasSize(2);
  }

  @Test
  public void mergeDualUnionCandidates_safeWinsOnEqualKeys() {
    var safe =
        ImmutableList.of(
            candidate("N12", "(bvslt i n)"), candidate("N12", "(bvsge i (_ bv0 32))"));
    var bug =
        ImmutableList.of(
            candidate("N12", "(bvslt i n)"), candidate("N12", "(bvslt i (_ bv0 32))"));

    assertThat(LlmEnsembleMerger.mergeDualUnionCandidates(safe, bug))
        .containsExactly(
            candidate("N12", "(bvslt i n)"),
            candidate("N12", "(bvsge i (_ bv0 32))"),
            candidate("N12", "(bvslt i (_ bv0 32))"))
        .inOrder();
  }
}
