// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.truth.Truth.assertThat;
import static org.mockito.Mockito.mock;

import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableMap;
import com.google.common.collect.ImmutableSet;
import java.util.List;
import org.junit.Test;
import org.sosy_lab.common.collect.PathCopyingPersistentTreeMap;
import org.sosy_lab.common.log.LogManager;
import org.sosy_lab.cpachecker.cfa.model.CFANode;
import org.sosy_lab.cpachecker.cfa.types.c.CNumericTypes;
import org.sosy_lab.cpachecker.core.interfaces.AbstractState;
import org.sosy_lab.cpachecker.core.interfaces.AbstractStateWithLocation;
import org.sosy_lab.cpachecker.cpa.composite.CompositeState;
import org.sosy_lab.cpachecker.cpa.predicate.BlockFormulaStrategy.BlockFormulas;
import org.sosy_lab.cpachecker.cpa.predicate.PredicateAbstractState;
import org.sosy_lab.cpachecker.cpa.predicate.VocabularyGuide;
import org.sosy_lab.cpachecker.util.predicates.AbstractionFormula;
import org.sosy_lab.cpachecker.util.predicates.pathformula.PathFormula;
import org.sosy_lab.cpachecker.util.predicates.pathformula.SSAMap;
import org.sosy_lab.cpachecker.util.predicates.pathformula.pointeraliasing.PointerTargetSet;
import org.sosy_lab.cpachecker.util.predicates.smt.SolverViewBasedTest0;
import org.sosy_lab.java_smt.SolverContextFactory.Solvers;
import org.sosy_lab.java_smt.api.BooleanFormula;

public class LegacyPredicateContextTest extends SolverViewBasedTest0 {
  private final CFANode head = CFANode.newDummyCFANode("main");

  private record Location(CFANode getLocationNode) implements AbstractStateWithLocation {}

  @Override
  protected Solvers solverToUse() {
    return Solvers.MATHSAT5;
  }

  private BooleanFormula arrayBlock(String function, int version) {
    return mgrv.parse(
        String.format(
            "(declare-fun |%1$s::a| () (_ BitVec 32))(declare-fun |%1$s::i@%2$d| () (_ BitVec"
                + " 32))(declare-fun |*int@%2$d| () (Array (_ BitVec 32) (_ BitVec 32)))(assert (="
                + " (select |*int@%2$d| (bvadd |%1$s::a| (bvshl |%1$s::i@%2$d| (_ bv2 32)))) (_ bv0"
                + " 32)))",
            function, version));
  }

  @SuppressWarnings("deprecation")
  private AbstractState state(int version) {
    var ssa =
        SSAMap.emptySSAMap()
            .builder()
            .setIndex("main::i", CNumericTypes.INT, version)
            .setIndex("main::x", CNumericTypes.INT, version)
            .setIndex("main::a", CNumericTypes.INT, 1)
            .setIndex("*int", CNumericTypes.INT, version)
            .build();
    var path =
        PathFormula.createManually(
            bmgrv.makeTrue(), ssa, PointerTargetSet.emptyPointerTargetSet(), 0);
    return new CompositeState(
        ImmutableList.of(
            new Location(head),
            PredicateAbstractState.mkAbstractionState(
                path, mock(AbstractionFormula.class), PathCopyingPersistentTreeMap.of())));
  }

  private PredicateValidationPipeline.CandidateValidationOutcome validate(
      List<BooleanFormula> blocks,
      List<AbstractState> states,
      String expression,
      String... extraNames) {
    var names = ImmutableSet.<String>builder().add(extraNames);
    blocks.forEach(block -> names.addAll(mgrv.extractVariableNames(block)));
    var pack =
        new ContextPack(
            1,
            "",
            "",
            ImmutableList.of(new LoopHeadInfo(head, "", "main")),
            ImmutableMap.of(),
            names.build(),
            new BlockFormulas(ImmutableList.copyOf(blocks)),
            ImmutableList.of(),
            "",
            "");
    return new PredicateValidationPipeline(LogManager.createNullLogManager(), solver, mgrv, false)
        .validateCandidates(
            pack,
            ImmutableList.of(
                new LoopHeadCandidate(
                    ImmutableList.of("N" + head.getNodeNumber()),
                    expression,
                    "",
                    ImmutableList.of())),
            states);
  }

  @Test
  public void scalarUsesHeadFunctionAndCurrentSsaDespiteForeignBlock() {
    var block = VocabularyGuide.parsePredicate("(= x 0)", mgrv, ImmutableSet.of("foreign::x@2"));
    var outcome = validate(List.of(block), List.of(state(5)), "(bvsge x 0)", "main::x@3", "x");
    assertThat(outcome.rejections()).isEmpty();
    assertThat(outcome.validation().validated()).hasSize(1);
    assertThat(mgrv.extractVariableNames(outcome.validation().validated().getFirst().formula()))
        .containsExactly("main::x@5");
  }

  @Test
  public void arrayUsesLocalTemplateAndLastAlignedOccurrence() {
    var outcome =
        validate(
            List.of(arrayBlock("foreign", 2), arrayBlock("main", 5)),
            List.of(state(2), state(5), state(9)),
            "(= a[i] (_ bv1 32))");
    assertThat(outcome.rejections()).isEmpty();
    assertThat(outcome.validation().validated()).hasSize(1);
    assertThat(mgrv.extractVariableNames(outcome.validation().validated().getFirst().formula()))
        .containsExactly("main::a@1", "main::i@5", "*int@5");
  }

  @Test
  public void missingLastContextDoesNotReuseEarlierSsa() {
    var outcome =
        validate(
            List.of(arrayBlock("main", 2), arrayBlock("main", 5)),
            List.of(state(2), new Location(head)),
            "(= a[i] (_ bv1 32))");
    assertThat(outcome.validation().validated()).isEmpty();
    assertThat(outcome.rejections().getFirst().reason())
        .isEqualTo(PredicateValidationPipeline.REASON_NO_SSA_MAP);
  }

  @Test
  public void foreignOnlyArrayTemplateCannotBypassScopeGuard() {
    var outcome =
        validate(
            List.of(arrayBlock("foreign", 2)),
            List.of(state(5)),
            "(= a[i] (_ bv1 32))",
            "main::i@5");
    assertThat(outcome.validation().validated()).isEmpty();
    assertThat(outcome.rejections()).hasSize(1);
  }

  @Test
  public void genericResolverRejectsAmbiguousFunctionNames() {
    assertThat(
            VocabularyGuide.parsePredicate(
                "(= x 0)", mgrv, ImmutableSet.of("foreign::x@2", "main::x@3")))
        .isNull();
  }
}
