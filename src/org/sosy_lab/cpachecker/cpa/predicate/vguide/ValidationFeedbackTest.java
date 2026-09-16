// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.truth.Truth.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableMap;
import com.google.common.collect.ImmutableSet;
import java.util.List;
import org.junit.Test;
import org.sosy_lab.common.Appender;
import org.sosy_lab.common.log.LogManager;
import org.sosy_lab.cpachecker.cfa.model.CFANode;
import org.sosy_lab.cpachecker.cpa.predicate.BlockFormulaStrategy.BlockFormulas;
import org.sosy_lab.cpachecker.util.predicates.smt.BooleanFormulaManagerView;
import org.sosy_lab.cpachecker.util.predicates.smt.FormulaManagerView;
import org.sosy_lab.java_smt.api.BooleanFormula;

/** Offline tests for the bounded validation-feedback policy. */
public class ValidationFeedbackTest {

  @Test
  public void repairFeedbackKeepsActionableReasonsAndBoundsOutput() {
    List<CandidateRejection> rejections =
        ImmutableList.of(
            rejection("invalid_json"),
            rejection("wrong_schema"),
            rejection("head_not_on_trace"),
            rejection("parse_error"),
            rejection("variable_not_in_scope"),
            rejection("unknown_loop_head"),
            rejection("missing_loop_head"),
            rejection("parse_error"));

    List<String> feedback = VGuideRefinementBridge.repairFeedback(rejections);

    assertThat(feedback).hasSize(5);
    assertThat(feedback)
        .containsAtLeast(
            "reason=invalid_json; head=N1; predicate=(bvslt i n); detail=detail",
            "reason=wrong_schema; head=N1; predicate=(bvslt i n); detail=detail",
            "reason=head_not_on_trace; head=N1; predicate=(bvslt i n); detail=detail",
            "reason=parse_error; head=N1; predicate=(bvslt i n); detail=detail",
            "reason=variable_not_in_scope; head=N1; predicate=(bvslt i n); detail=detail");
    assertThat(feedback.stream().distinct().toList()).hasSize(feedback.size());
  }

  @Test
  public void repairFeedbackExcludesNonActionableReasons() {
    assertThat(
            VGuideRefinementBridge.repairFeedback(
                ImmutableList.of(
                    rejection("no_ssa_map"),
                    rejection("unsupported_array_access"),
                    new CandidateRejection(
                        "", "N1", "(= x x)", "contract_violation", "trivially true or false"))))
        .isEmpty();
  }

  @Test
  public void repairSlotsCountsCandidateObjectsAndCapsDualBudget() {
    CFANode first = CFANode.newDummyCFANode("main");
    CFANode second = CFANode.newDummyCFANode("main");
    LoopHeadInfo firstHead = new LoopHeadInfo(first, "ignored", "main");
    LoopHeadInfo secondHead = new LoopHeadInfo(second, "ignored", "main");
    LoopHeadCandidate multiHead =
        new LoopHeadCandidate(
            ImmutableList.of(firstHead.label(), secondHead.label()),
            "(bvslt i n)",
            "bound",
            ImmutableList.of());
    BooleanFormula firstFormula = mock(BooleanFormula.class);
    ValidatedPredicate firstBinding =
        new ValidatedPredicate(
            firstFormula,
            first,
            ValidatedPredicate.Classification.PRECISION_ONLY,
            "bound",
            ImmutableList.of(),
            false,
            false);
    ValidatedPredicate secondBinding =
        new ValidatedPredicate(
            firstFormula,
            second,
            ValidatedPredicate.Classification.PRECISION_ONLY,
            "bound",
            ImmutableList.of(),
            false,
            false);
    var primary =
        new PredicateValidationPipeline.CandidateValidationOutcome(
            new ValidationResult(ImmutableList.of(firstBinding, secondBinding)),
            ImmutableList.of(),
            ImmutableMap.of(
                firstBinding, multiHead.predicate(), secondBinding, multiHead.predicate()));
    ContextPack pack =
        new ContextPack(
            1,
            "",
            "",
            ImmutableList.of(firstHead, secondHead),
            ImmutableMap.of(),
            ImmutableSet.of(),
            new BlockFormulas(ImmutableList.of()),
            ImmutableList.of(),
            "",
            "");

    assertThat(
            VGuideRefinementBridge.repairSlots(
                pack, ImmutableList.of(multiHead), primary, new PredicateBudget(1, 5), false))
        .isEqualTo(4);
    assertThat(
            VGuideRefinementBridge.repairSlots(
                pack, ImmutableList.of(multiHead), primary, new PredicateBudget(1, 5), true))
        .isEqualTo(5);

    assertThat(
            VGuideRefinementBridge.repairSlots(
                pack, ImmutableList.of(multiHead), primary, new PredicateBudget(1, 1), false))
        .isEqualTo(0);
  }

  @Test
  public void repairValidationPreservesSeededPrimaryWithEmptyRepairOutput() {
    FormulaManagerView fmgr = mock(FormulaManagerView.class);
    BooleanFormulaManagerView booleanManager = mock(BooleanFormulaManagerView.class);
    BooleanFormula primaryFormula = mock(BooleanFormula.class);
    Appender primaryDump = mock(Appender.class);
    when(fmgr.getBooleanFormulaManager()).thenReturn(booleanManager);
    when(fmgr.dumpFormula(primaryFormula)).thenReturn(primaryDump);
    when(primaryDump.toString()).thenReturn("primary-formula");

    CFANode headNode = CFANode.newDummyCFANode("main");
    LoopHeadInfo head = new LoopHeadInfo(headNode, "ignored", "main");
    ValidatedPredicate seeded =
        new ValidatedPredicate(
            primaryFormula,
            headNode,
            ValidatedPredicate.Classification.PRECISION_ONLY,
            "bound",
            ImmutableList.of(),
            false,
            false);
    CandidateRejection seededRejection = rejection("parse_error");
    var primary =
        new PredicateValidationPipeline.CandidateValidationOutcome(
            new ValidationResult(ImmutableList.of(seeded)),
            ImmutableList.of(seededRejection),
            ImmutableMap.of(seeded, "(bvslt i n)"));
    ContextPack pack =
        new ContextPack(
            1,
            "",
            "",
            ImmutableList.of(head),
            ImmutableMap.of(),
            ImmutableSet.of(),
            new BlockFormulas(ImmutableList.of()),
            ImmutableList.of(),
            "",
            "");

    var repaired =
        new PredicateValidationPipeline(LogManager.createNullLogManager(), null, fmgr, false)
            .validateCandidates(pack, ImmutableList.of(), ImmutableList.of(), primary);

    assertThat(repaired.validation().validated()).containsExactly(seeded);
    assertThat(repaired.rawStrings()).containsExactlyEntriesIn(primary.rawStrings());
    assertThat(repaired.rejections()).containsExactly(seededRejection);
  }

  private static CandidateRejection rejection(String reason) {
    return new CandidateRejection("", "N1", "(bvslt i n)", reason, "detail");
  }
}
