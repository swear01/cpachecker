// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-FileCopyrightText: 2026 SSU-WEI HUANG <https://github.com/swear01>
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.truth.Truth.assertThat;
import static org.mockito.Mockito.mock;

import com.google.common.collect.ImmutableMap;
import org.junit.Test;
import org.sosy_lab.cpachecker.cfa.model.CFANode;
import org.sosy_lab.cpachecker.cpa.predicate.PredicatePrecision;
import org.sosy_lab.cpachecker.util.predicates.AbstractionPredicate;

public class PredicateLifecycleTest {

  @Test
  public void replacementRemovesOnlyPreviousOwnedPredicates() {
    CFANode head = CFANode.newDummyCFANode("main");
    AbstractionPredicate nativePredicate = mock(AbstractionPredicate.class);
    AbstractionPredicate firstLlmPredicate = mock(AbstractionPredicate.class);
    AbstractionPredicate secondLlmPredicate = mock(AbstractionPredicate.class);
    PredicatePrecision nativePrecision =
        PredicatePrecision.empty()
            .addLocalPredicates(ImmutableMap.of(head, nativePredicate).entrySet());
    PredicateLifecycle lifecycle = new PredicateLifecycle();

    PredicatePrecision first =
        lifecycle
            .beginReplacement(ImmutableMap.of(head, firstLlmPredicate).entrySet())
            .apply(nativePrecision);
    PredicatePrecision second =
        lifecycle
            .beginReplacement(ImmutableMap.of(head, secondLlmPredicate).entrySet())
            .apply(first);

    assertThat(second.getLocalPredicates().get(head))
        .containsExactly(nativePredicate, secondLlmPredicate);
    assertThat(lifecycle.nativeOnly(second).getLocalPredicates().get(head))
        .containsExactly(nativePredicate);
  }
}
