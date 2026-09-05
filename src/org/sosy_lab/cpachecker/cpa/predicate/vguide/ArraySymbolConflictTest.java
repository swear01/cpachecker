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

import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableMap;
import com.google.common.collect.ImmutableSet;
import java.util.LinkedHashSet;
import org.junit.Test;
import org.sosy_lab.common.collect.PathCopyingPersistentTreeMap;
import org.sosy_lab.cpachecker.cfa.model.CFANode;
import org.sosy_lab.cpachecker.cfa.types.c.CNumericTypes;
import org.sosy_lab.cpachecker.core.interfaces.AbstractStateWithLocation;
import org.sosy_lab.cpachecker.cpa.composite.CompositeState;
import org.sosy_lab.cpachecker.cpa.predicate.BlockFormulaStrategy.BlockFormulas;
import org.sosy_lab.cpachecker.cpa.predicate.PredicateAbstractState;
import org.sosy_lab.cpachecker.cpa.predicate.VocabularyGuide;
import org.sosy_lab.cpachecker.util.predicates.AbstractionFormula;
import org.sosy_lab.cpachecker.util.predicates.pathformula.PathFormula;
import org.sosy_lab.cpachecker.util.predicates.pathformula.SSAMap;
import org.sosy_lab.cpachecker.util.predicates.smt.SolverViewBasedTest0;
import org.sosy_lab.java_smt.SolverContextFactory.Solvers;
import org.sosy_lab.java_smt.api.BooleanFormula;
import org.sosy_lab.java_smt.api.FormulaType;

/** Native symbol declarations must retain the trace's bitwidth through candidate injection. */
public class ArraySymbolConflictTest extends SolverViewBasedTest0 {

  @Override
  protected Solvers solverToUse() {
    return Solvers.MATHSAT5;
  }

  @Test
  public void resolvesGlobalSsaWithoutMatchingLongerNames() {
    var vars = new LinkedHashSet<>(ImmutableList.of("main::SIZE_EXTRA@2", "SIZE@3"));
    var parsed =
        VocabularyGuide.parsePredicate(
            "(bvslt SIZE (_ bv10 32))", mgrv, vars, ImmutableMap.of(), ImmutableMap.of("SIZE", 16));

    assertThat(parsed).isNotNull();
    assertThat(mgrv.extractVariableNames(parsed)).containsExactly("SIZE@3");
    assertThat(mgrv.getFormulaType(mgrv.extractVariables(parsed).get("SIZE@3")))
        .isEqualTo(FormulaType.getBitvectorTypeWithSize(16));
  }

  @Test
  public void scalarCandidatesPreserveNativeGlobalWidthsAndDeduplicate() {
    for (int bits : ImmutableList.of(16, 64)) {
      String name = bits == 16 ? "SIZE" : "ARR_SIZE";
      BooleanFormula block =
          bvmgr.lessThan(bvmgr.makeBitvector(bits, 1), bvmgr.makeVariable(bits, name + "@3"), true);
      LoopHeadInfo head = new LoopHeadInfo(newDummyCFANode("main"), "ignored", "main");
      ContextPack pack =
          new ContextPack(
              1,
              "",
              "",
              ImmutableList.of(head),
              ImmutableMap.of(),
              ImmutableSet.of(name + "@3"),
              new BlockFormulas(ImmutableList.of(block)),
              ImmutableList.of(),
              "",
              "");
      LoopHeadCandidate candidate =
          new LoopHeadCandidate(
              ImmutableList.of(head.label()),
              "(bvsge " + name + " (_ bv0 32))",
              "",
              ImmutableList.of());
      var outcome =
          new PredicateValidationPipeline(logger, solver, mgrv, false)
              .validateCandidates(
                  pack,
                  ImmutableList.of(candidate, candidate),
                  ImmutableList.of(new LocState(head.node())));

      assertThat(outcome.rejections()).isEmpty();
      assertThat(outcome.validation().validated()).hasSize(1);
      assertThat(outcome.rawStrings().get(outcome.validation().validated().getFirst()))
          .isEqualTo(candidate.predicate());
      BooleanFormula formula = outcome.validation().validated().getFirst().formula();
      assertThat(mgrv.extractVariableNames(formula)).containsExactly(name + "@3");
      assertThat(mgrv.getFormulaType(mgrv.extractVariables(formula).get(name + "@3")))
          .isEqualTo(FormulaType.getBitvectorTypeWithSize(bits));
      // These are the two consumers that crashed after accepting a mistyped candidate.
      mgrv.uninstantiate(block);
      mgrv.uninstantiate(formula);
      assertThat(mgrv.extractVariables(mgrv.uninstantiate(formula)).get(name))
          .isEqualTo(bvmgr.makeVariable(bits, name));
    }
  }

  @Test
  public void arrayCandidatesUseTargetHeadSsaAndNativeScalarWidths() {
    BooleanFormula block =
        mgrv.parse(
            "(declare-fun SIZE@3 () (_ BitVec 16))"
                + " (declare-fun |main::i@2| () (_ BitVec 32))"
                + " (declare-fun |main::a@1| () (_ BitVec 32))"
                + " (declare-fun *short_int@1 () (Array (_ BitVec 32) (_ BitVec 16)))"
                + " (assert (and (bvslt |main::i@2| ((_ sign_extend 16) SIZE@3))"
                + " (= (select *short_int@1 (bvadd |main::a@1|"
                + " (bvshl |main::i@2| (_ bv1 32)))) (_ bv0 16))))");
    var ssa = SSAMap.emptySSAMap().builder();
    ssa.setIndex("SIZE", CNumericTypes.SHORT_INT, 4);
    ssa.setIndex("main::i", CNumericTypes.INT, 5);
    ssa.setIndex("main::a", CNumericTypes.INT, 1);
    ssa.setIndex("*short_int", CNumericTypes.SHORT_INT, 2);
    PathFormula path = mock(PathFormula.class);
    when(path.getSsa()).thenReturn(ssa.build());
    PredicateAbstractState pas =
        PredicateAbstractState.mkAbstractionState(
            path, mock(AbstractionFormula.class), PathCopyingPersistentTreeMap.of());
    LoopHeadInfo head = new LoopHeadInfo(newDummyCFANode("main"), "ignored", "main");
    ContextPack pack =
        new ContextPack(
            1,
            "",
            "",
            ImmutableList.of(head),
            ImmutableMap.of(),
            ImmutableSet.copyOf(mgrv.extractVariableNames(block)),
            new BlockFormulas(ImmutableList.of(block)),
            ImmutableList.of(),
            "",
            "");
    LoopHeadCandidate candidate =
        new LoopHeadCandidate(
            ImmutableList.of(head.label()),
            "(and (bvslt i SIZE) (= (a i) (_ bv0 16)))",
            "",
            ImmutableList.of());
    var outcome =
        new PredicateValidationPipeline(logger, solver, mgrv, false)
            .validateCandidates(
                pack,
                ImmutableList.of(candidate),
                ImmutableList.of(
                    new CompositeState(ImmutableList.of(new LocState(head.node()), pas))));

    assertThat(outcome.rejections()).isEmpty();
    assertThat(outcome.validation().validated()).hasSize(1);
    assertThat(outcome.rawStrings().get(outcome.validation().validated().getFirst()))
        .isEqualTo(candidate.predicate());
    BooleanFormula formula = outcome.validation().validated().getFirst().formula();
    assertThat(mgrv.extractVariableNames(formula))
        .containsExactly("SIZE@4", "main::i@5", "main::a@1", "*short_int@2");
    assertThat(mgrv.getFormulaType(mgrv.extractVariables(formula).get("SIZE@4")))
        .isEqualTo(FormulaType.getBitvectorTypeWithSize(16));
    mgrv.uninstantiate(block);
    mgrv.uninstantiate(formula);
  }

  private record LocState(CFANode getLocationNode) implements AbstractStateWithLocation {}
}
