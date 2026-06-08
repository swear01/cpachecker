// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.truth.Truth.assertThat;

import org.junit.Test;

public class PredicateBudgetTest {

  @Test
  public void capOrdered_preservesPriorityAndDedupes() {
    PredicateBudget budget = new PredicateBudget(2, 3);
    assertThat(budget.capOrdered(java.util.List.of("(= a 0)", "(= a 0)", "(= b 1)", "(= c 2)", "(= d 3)")))
        .containsExactly("(= a 0)", "(= b 1)", "(= c 2)")
        .inOrder();
  }
}
