// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate;

import static com.google.common.truth.Truth.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.google.common.collect.ImmutableList;
import org.junit.Test;
import org.sosy_lab.cpachecker.util.predicates.AbstractionPredicate;
import org.sosy_lab.cpachecker.util.predicates.smt.SolverViewBasedTest0;

public class PredicateAbstractionManagerTest extends SolverViewBasedTest0 {

  @Test
  public void matchesOnlyTheFirstDownstreamUseAndResets() {
    AbstractionPredicate target = mock(AbstractionPredicate.class);
    AbstractionPredicate unrelated = mock(AbstractionPredicate.class);
    when(target.getSymbolicVariable()).thenReturn(bmgrv.makeVariable("PRED0"));
    when(unrelated.getSymbolicVariable()).thenReturn(bmgrv.makeVariable("PRED1"));
    PredicateAbstractionManager.VGuideDiagnosticState state =
        new PredicateAbstractionManager.VGuideDiagnosticState();

    state.arm(ImmutableList.of(target));
    assertThat(state.match(ImmutableList.of(unrelated))).isEmpty();
    assertThat(state.match(ImmutableList.of(target)))
        .containsExactly(target.getSymbolicVariable().toString());
    assertThat(state.match(ImmutableList.of(target))).isEmpty();

    state.arm(ImmutableList.of(target));
    state.clear();
    assertThat(state.match(ImmutableList.of(target))).isEmpty();
  }
}
