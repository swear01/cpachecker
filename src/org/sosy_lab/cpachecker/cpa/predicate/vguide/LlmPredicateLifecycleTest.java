// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.truth.Truth.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.sosy_lab.cpachecker.cfa.model.CFANode.newDummyCFANode;

import com.google.common.collect.ImmutableSet;
import com.google.common.collect.ImmutableSetMultimap;
import org.junit.Test;
import org.sosy_lab.cpachecker.cfa.model.CFANode;
import org.sosy_lab.cpachecker.cpa.predicate.PredicatePrecision;
import org.sosy_lab.cpachecker.cpa.predicate.PredicatePrecision.LocationInstance;
import org.sosy_lab.cpachecker.util.predicates.AbstractionPredicate;
import org.sosy_lab.cpachecker.util.predicates.smt.SolverViewBasedTest0;
import org.sosy_lab.java_smt.api.BooleanFormula;

/** LLM-predicate lifecycle ownership keys (Issue #8). */
public class LlmPredicateLifecycleTest extends SolverViewBasedTest0 {

  @Test
  public void ownershipKeyIsDeterministicAndScopedPerNode() {
    assertThat(VGuideRefinementBridge.llmOwnedKey(12, "(bvslt i n)"))
        .isEqualTo("local N12|(bvslt i n)");
    assertThat(VGuideRefinementBridge.llmOwnedKey(15, "(bvslt i n)"))
        .isEqualTo("local N15|(bvslt i n)");
    assertThat(VGuideRefinementBridge.llmOwnedKey(12, "(bvslt i n)"))
        .isNotEqualTo(VGuideRefinementBridge.llmOwnedKey(15, "(bvslt i n)"));
  }

  @Test
  public void ownershipKeySurvivesCanonicalRoundTripShape() {
    // Recording and removal both build keys via llmOwnedKey(nodeNumber, canonical(formula));
    // the canonical form is the fmgr dump string, which may contain spaces.
    assertThat(VGuideRefinementBridge.llmOwnedKey(3, "(= x (_ bv1 32))"))
        .isEqualTo("local N3|(= x (_ bv1 32))");
  }

  @Test
  public void filtersOwnedPredicatesByNodeAndKeepsNativeLocationInstances() {
    CFANode firstHead = newDummyCFANode("main");
    CFANode secondHead = newDummyCFANode("main");
    BooleanFormula ownedFormula = bmgrv.makeVariable("owned");
    AbstractionPredicate owned = predicate(ownedFormula);
    AbstractionPredicate nativePredicate = predicate(bmgrv.makeVariable("native"));

    ImmutableSetMultimap.Builder<LocationInstance, AbstractionPredicate> locationInstances =
        ImmutableSetMultimap.builder();
    locationInstances.put(new LocationInstance(firstHead, 0), owned);
    locationInstances.put(new LocationInstance(secondHead, 0), owned);
    ImmutableSetMultimap.Builder<CFANode, AbstractionPredicate> locals =
        ImmutableSetMultimap.builder();
    locals.put(firstHead, owned);
    locals.put(firstHead, nativePredicate);
    locals.put(secondHead, owned);
    PredicatePrecision current =
        new PredicatePrecision(
            locationInstances.build(),
            locals.build(),
            ImmutableSetMultimap.of(),
            ImmutableSet.of());

    var replacement =
        VGuideRefinementBridge.filterLlmOwnedPrecision(
            current,
            ImmutableSet.of(
                VGuideRefinementBridge.llmOwnedKey(
                    firstHead.getNodeNumber(), canonical(ownedFormula))),
            this::canonical);

    assertThat(replacement.removed()).isEqualTo(1);
    assertThat(replacement.filtered().getLocalPredicates().get(firstHead))
        .containsExactly(nativePredicate);
    assertThat(replacement.filtered().getLocalPredicates().get(secondHead)).containsExactly(owned);
    assertThat(
            replacement
                .filtered()
                .getLocationInstancePredicates()
                .get(new LocationInstance(firstHead, 0)))
        .containsExactly(nativePredicate);
    assertThat(
            replacement
                .filtered()
                .getLocationInstancePredicates()
                .get(new LocationInstance(secondHead, 0)))
        .containsExactly(owned);
  }

  @Test
  public void emptyOwnershipSetLeavesNativePrecisionUntouched() {
    CFANode head = newDummyCFANode("main");
    AbstractionPredicate nativePredicate = predicate(bmgrv.makeVariable("native"));
    PredicatePrecision current =
        new PredicatePrecision(
            ImmutableSetMultimap.of(),
            ImmutableSetMultimap.of(head, nativePredicate),
            ImmutableSetMultimap.of(),
            ImmutableSet.of());

    var replacement =
        VGuideRefinementBridge.filterLlmOwnedPrecision(current, ImmutableSet.of(), this::canonical);

    assertThat(replacement.removed()).isEqualTo(0);
    assertThat(replacement.filtered()).isEqualTo(current);
    assertThat(replacement.filtered().getLocalPredicates().get(head))
        .containsExactly(nativePredicate);
  }

  private AbstractionPredicate predicate(BooleanFormula formula) {
    AbstractionPredicate predicate = mock(AbstractionPredicate.class);
    when(predicate.getSymbolicAtom()).thenReturn(formula);
    return predicate;
  }

  private String canonical(BooleanFormula formula) {
    return mgrv.dumpFormula(formula).toString().replace('\n', ' ');
  }
}
