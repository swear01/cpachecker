// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.truth.Truth.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.sosy_lab.cpachecker.cfa.model.CFANode.newDummyCFANode;

import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableSet;
import com.google.common.collect.ImmutableSetMultimap;
import org.junit.Test;
import org.mockito.ArgumentCaptor;
import org.sosy_lab.common.log.LogManager;
import org.sosy_lab.cpachecker.cfa.model.CFANode;
import org.sosy_lab.cpachecker.core.interfaces.Precision;
import org.sosy_lab.cpachecker.core.reachedset.UnmodifiableReachedSet;
import org.sosy_lab.cpachecker.cpa.arg.ARGReachedSet;
import org.sosy_lab.cpachecker.cpa.predicate.PredicateAbstractionManager;
import org.sosy_lab.cpachecker.cpa.predicate.PredicatePrecision;
import org.sosy_lab.cpachecker.util.predicates.AbstractionPredicate;
import org.sosy_lab.cpachecker.util.predicates.smt.SolverViewBasedTest0;
import org.sosy_lab.java_smt.api.BooleanFormula;

public class LoopHeadPrecisionInjectorTest extends SolverViewBasedTest0 {

  @Test
  public void preservesAllCurrentPrecisionComponentsWhenInjecting() throws Exception {
    CFANode oldHead = newDummyCFANode("old");
    CFANode refinedHead = newDummyCFANode("refined");
    CFANode compilerHead = newDummyCFANode("compiler");
    AbstractionPredicate oldPredicate = mock(AbstractionPredicate.class);
    AbstractionPredicate refinedPredicate = mock(AbstractionPredicate.class);
    AbstractionPredicate compilerPredicate = mock(AbstractionPredicate.class);
    PredicatePrecision rootPrecision = precision(oldHead, oldPredicate);
    PredicatePrecision refinedPrecision = precision(refinedHead, refinedPredicate);
    UnmodifiableReachedSet view = mock(UnmodifiableReachedSet.class);
    when(view.getPrecisions()).thenReturn(ImmutableList.of(rootPrecision, refinedPrecision));
    ARGReachedSet reached = mock(ARGReachedSet.class);
    when(reached.asReachedSet()).thenReturn(view);
    BooleanFormula formula = bmgrv.makeVariable("main::x");
    PredicateAbstractionManager abstractionManager = mock(PredicateAbstractionManager.class);
    when(abstractionManager.getPredicateFor(formula)).thenReturn(compilerPredicate);
    ValidatedPredicate candidate =
        new ValidatedPredicate(
            formula,
            compilerHead,
            ValidatedPredicate.Classification.PRECISION_ONLY,
            "compiler",
            ImmutableList.of("main::x"),
            false,
            false);

    assertThat(
            new LoopHeadPrecisionInjector(LogManager.createTestLogManager(), abstractionManager)
                .inject(reached, ImmutableList.of(candidate)))
        .isTrue();

    ArgumentCaptor<Precision> precision = ArgumentCaptor.forClass(Precision.class);
    verify(reached).updatePrecisionGlobally(precision.capture(), any());
    PredicatePrecision updated = (PredicatePrecision) precision.getValue();
    assertThat(updated.getLocalPredicates().get(oldHead)).contains(oldPredicate);
    assertThat(updated.getLocalPredicates().get(refinedHead)).contains(refinedPredicate);
    assertThat(updated.getLocalPredicates().get(compilerHead)).contains(compilerPredicate);
  }

  private static PredicatePrecision precision(CFANode head, AbstractionPredicate predicate) {
    return new PredicatePrecision(
        ImmutableSetMultimap.of(),
        ImmutableSetMultimap.of(head, predicate),
        ImmutableSetMultimap.of(),
        ImmutableSet.of());
  }
}
