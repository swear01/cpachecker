// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.truth.Truth.assertThat;

import org.junit.Test;

public class LlmEnsembleMergerTest {

  @Test
  public void unionValidate_dedupesAcrossDraws() {
    String a = "{\"predicates\":[\"(= x 0)\",\"(>= y 1)\"]}";
    String b = "{\"predicates\":[\"(= x 0)\",\"(<= z 3)\"]}";
    assertThat(LlmEnsembleMerger.unionValidate(java.util.List.of(a, b)))
        .containsExactly("(= x 0)", "(>= y 1)", "(<= z 3)")
        .inOrder();
  }

  @Test
  public void unionValidate_capsToPredicateBudget() {
    String json =
        "{\"predicates\":[\"(= a 0)\",\"(= b 1)\",\"(= c 2)\",\"(= d 3)\",\"(= e 4)\"]}";
    assertThat(
            LlmEnsembleMerger.unionValidate(
                java.util.List.of(json), new PredicateBudget(2, 3)))
        .containsExactly("(= a 0)", "(= b 1)", "(= c 2)")
        .inOrder();
  }
}
