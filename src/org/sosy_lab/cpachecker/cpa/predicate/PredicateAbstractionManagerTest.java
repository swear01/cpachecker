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
    AbstractionPredicate second = mock(AbstractionPredicate.class);
    String targetKey = bmgrv.makeVariable("PRED0").toString();
    String secondKey = bmgrv.makeVariable("PRED2").toString();
    when(target.getSymbolicVariable()).thenReturn(bmgrv.makeVariable("PRED0"));
    when(unrelated.getSymbolicVariable()).thenReturn(bmgrv.makeVariable("PRED1"));
    when(second.getSymbolicVariable()).thenReturn(bmgrv.makeVariable("PRED2"));
    PredicateAbstractionManager.VGuideDiagnosticState state =
        new PredicateAbstractionManager.VGuideDiagnosticState();

    state.arm(ImmutableList.of(target, target, second));
    assertThat(state.match(ImmutableList.of(unrelated))).isEmpty();
    assertThat(state.observing()).isFalse();
    assertThat(state.match(ImmutableList.of(target))).containsExactly(targetKey);
    assertThat(state.observing()).isTrue();
    assertThat(state.match(ImmutableList.of(target))).isEmpty();
    assertThat(state.match(ImmutableList.of(second))).containsExactly(secondKey);
    assertThat(state.consume(secondKey)).isTrue();
    assertThat(state.consume(secondKey)).isFalse();
    state.end();
    assertThat(state.active()).isEmpty();
    assertThat(state.observing()).isFalse();

    state.arm(ImmutableList.of(target));
    state.clear();
    assertThat(state.match(ImmutableList.of(target))).isEmpty();
  }
}
