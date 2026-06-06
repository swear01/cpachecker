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
}
