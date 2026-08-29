// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.truth.Truth.assertThat;
import static org.sosy_lab.cpachecker.cfa.model.CFANode.newDummyCFANode;

import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableMap;
import com.google.common.collect.ImmutableSet;
import java.util.List;
import org.junit.Test;
import org.sosy_lab.common.log.LogManager;
import org.sosy_lab.cpachecker.cfa.model.CFAEdge;
import org.sosy_lab.cpachecker.cfa.model.CFANode;
import org.sosy_lab.cpachecker.core.interfaces.AbstractState;
import org.sosy_lab.cpachecker.core.interfaces.AbstractStateWithLocation;
import org.sosy_lab.cpachecker.cpa.predicate.BlockFormulaStrategy.BlockFormulas;
import org.sosy_lab.cpachecker.cpa.predicate.VocabularyGuide;
import org.sosy_lab.cpachecker.util.predicates.smt.SolverViewBasedTest0;
import org.sosy_lab.java_smt.api.BooleanFormula;

/**
 * Mapping policy: candidates validate only at their named loop heads; no implicit broadcast;
 * variables must be visible at the named head; initiation candidates are processed before
 * supporting ones for group-consistency diagnostics.
 */
public class PredicateValidationPipelineTest extends SolverViewBasedTest0 {

  private static final LogManager LOGGER = LogManager.createNullLogManager();
  private static final ImmutableSet<String> ENCODED_F1_X = ImmutableSet.of("f1::x@N5");

  private LoopHeadInfo headA;
  private LoopHeadInfo headB;
  private LoopHeadInfo headOffTrace;

  private void makeHeads() {
    headA = new LoopHeadInfo(newDummyCFANode("f1"), "ignored", "f1");
    headB = new LoopHeadInfo(newDummyCFANode("f1"), "ignored", "f1");
    headOffTrace = new LoopHeadInfo(newDummyCFANode("f3"), "ignored", "f3");
  }

  private BooleanFormula parse(String formula, ImmutableSet<String> encoded) {
    return VocabularyGuide.parsePredicate(formula, mgrv, encoded);
  }

  private ContextPack pack(ImmutableSet<String> encoded, BooleanFormula... blocks) {
    ImmutableList<LoopHeadInfo> heads = ImmutableList.of(headA, headB, headOffTrace);
    return new ContextPack(
        1,
        "",
        "",
        heads,
        ImmutableMap.of(),
        encoded,
        new BlockFormulas(ImmutableList.copyOf(blocks)),
        ImmutableList.of(),
        "",
        "");
  }

  private static List<? extends AbstractState> trace(CFANode... nodes) {
    ImmutableList.Builder<AbstractState> out = ImmutableList.builder();
    for (CFANode node : nodes) {
      out.add(new LocState(node));
    }
    return out.build();
  }

  private static LoopHeadCandidate candidate(String label, String predicate) {
    return new LoopHeadCandidate(ImmutableList.of(label), predicate, "", ImmutableList.of());
  }

  @Test
  public void validatesCandidateOnlyAtItsNamedHead_noBroadcast() {
    makeHeads();
    BooleanFormula block = parse("(= x (_ bv1 32))", ENCODED_F1_X);
    PredicateValidationPipeline pipeline =
        new PredicateValidationPipeline(LOGGER, solver, mgrv, false);

    var outcome =
        pipeline.validateCandidates(
            pack(ENCODED_F1_X, block, block),
            ImmutableList.of(candidate(headA.label(), "(= x (_ bv1 32))")),
            trace(headA.node(), headB.node()));

    assertThat(outcome.validation().validated()).hasSize(1);
    assertThat(outcome.validation().validated().get(0).loopHeadNode()).isEqualTo(headA.node());
    assertThat(outcome.rejections()).isEmpty();
  }

  @Test
  public void multiHeadCandidateValidatedAtEachNamedHead() {
    makeHeads();
    BooleanFormula block = parse("(= x (_ bv1 32))", ENCODED_F1_X);
    PredicateValidationPipeline pipeline =
        new PredicateValidationPipeline(LOGGER, solver, mgrv, false);

    var outcome =
        pipeline.validateCandidates(
            pack(ENCODED_F1_X, block, block),
            ImmutableList.of(
                new LoopHeadCandidate(
                    ImmutableList.of(headA.label(), headB.label()),
                    "(= x (_ bv1 32))",
                    "",
                    ImmutableList.of())),
            trace(headA.node(), headB.node()));

    assertThat(outcome.validation().validated()).hasSize(2);
    assertThat(
            outcome.validation().validated().stream().map(v -> v.loopHeadNode()).toList())
        .containsExactly(headA.node(), headB.node());
    assertThat(outcome.rejections()).isEmpty();
  }

  @Test
  public void unknownLoopHeadRejected() {
    makeHeads();
    BooleanFormula block = parse("(= x (_ bv1 32))", ENCODED_F1_X);
    PredicateValidationPipeline pipeline =
        new PredicateValidationPipeline(LOGGER, solver, mgrv, false);

    var outcome =
        pipeline.validateCandidates(
            pack(ENCODED_F1_X, block),
            ImmutableList.of(candidate("N999", "(= x (_ bv1 32))")),
            trace(headA.node()));

    assertThat(outcome.validation().validated()).isEmpty();
    assertThat(outcome.rejections()).hasSize(1);
    assertThat(outcome.rejections().get(0).reason())
        .isEqualTo(PredicateValidationPipeline.REASON_UNKNOWN_LOOP_HEAD);
  }

  @Test
  public void headNotOnTraceRejected() {
    makeHeads();
    BooleanFormula block = parse("(= x (_ bv1 32))", ENCODED_F1_X);
    PredicateValidationPipeline pipeline =
        new PredicateValidationPipeline(LOGGER, solver, mgrv, false);

    var outcome =
        pipeline.validateCandidates(
            pack(ENCODED_F1_X, block),
            ImmutableList.of(candidate(headOffTrace.label(), "(= x (_ bv1 32))")),
            trace(headA.node()));

    assertThat(outcome.validation().validated()).isEmpty();
    assertThat(outcome.rejections()).hasSize(1);
    assertThat(outcome.rejections().get(0).reason())
        .isEqualTo(PredicateValidationPipeline.REASON_HEAD_NOT_ON_TRACE);
  }

  @Test
  public void parseErrorRejected() {
    makeHeads();
    BooleanFormula block = parse("(= x (_ bv1 32))", ENCODED_F1_X);
    PredicateValidationPipeline pipeline =
        new PredicateValidationPipeline(LOGGER, solver, mgrv, false);

    var outcome =
        pipeline.validateCandidates(
            pack(ENCODED_F1_X, block),
            ImmutableList.of(candidate(headA.label(), "(= x")),
            trace(headA.node()));

    assertThat(outcome.validation().validated()).isEmpty();
    assertThat(outcome.rejections()).hasSize(1);
    assertThat(outcome.rejections().get(0).reason())
        .isEqualTo(PredicateValidationPipeline.REASON_PARSE_ERROR);
  }

  @Test
  public void l3EntailmentClassifiesEntailedAndPrecisionOnly() {
    makeHeads();
    BooleanFormula block = parse("(= x (_ bv1 32))", ENCODED_F1_X);
    PredicateValidationPipeline pipeline =
        new PredicateValidationPipeline(LOGGER, solver, mgrv, true);

    var outcome =
        pipeline.validateCandidates(
            pack(ENCODED_F1_X, block),
            ImmutableList.of(
                candidate(headA.label(), "(bvsge x (_ bv0 32))"),
                candidate(headA.label(), "(= x (_ bv2 32))")),
            trace(headA.node()));

    assertThat(outcome.validation().validated()).hasSize(2);
    assertThat(outcome.validation().validated().get(0).classification())
        .isEqualTo(ValidatedPredicate.Classification.ENTAILED);
    assertThat(outcome.validation().validated().get(1).classification())
        .isEqualTo(ValidatedPredicate.Classification.PRECISION_ONLY);
    assertThat(outcome.rejections()).isEmpty();
  }

  @Test
  public void rejectedHeadsDoNotBlockOtherHeadsOfSameCandidate() {
    makeHeads();
    BooleanFormula block = parse("(= x (_ bv1 32))", ENCODED_F1_X);
    PredicateValidationPipeline pipeline =
        new PredicateValidationPipeline(LOGGER, solver, mgrv, false);

    var outcome =
        pipeline.validateCandidates(
            pack(ENCODED_F1_X, block),
            ImmutableList.of(
                new LoopHeadCandidate(
                    ImmutableList.of(headA.label(), headOffTrace.label()),
                    "(= x (_ bv1 32))",
                    "",
                    ImmutableList.of())),
            trace(headA.node()));

    assertThat(outcome.validation().validated()).hasSize(1);
    assertThat(outcome.validation().validated().get(0).loopHeadNode()).isEqualTo(headA.node());
    assertThat(outcome.rejections()).hasSize(1);
    assertThat(outcome.rejections().get(0).reason())
        .isEqualTo(PredicateValidationPipeline.REASON_HEAD_NOT_ON_TRACE);
  }

  @Test
  public void duplicateHeadPredicatePairsValidatedOnce() {
    makeHeads();
    BooleanFormula block = parse("(= x (_ bv1 32))", ENCODED_F1_X);
    PredicateValidationPipeline pipeline =
        new PredicateValidationPipeline(LOGGER, solver, mgrv, true);

    var outcome =
        pipeline.validateCandidates(
            pack(ENCODED_F1_X, block, block),
            ImmutableList.of(
                candidate(headA.label(), "(= x (_ bv1 32))"),
                new LoopHeadCandidate(
                    ImmutableList.of(headA.label(), headB.label()),
                    "(= x (_ bv1 32))",
                    "",
                    ImmutableList.of())),
            trace(headA.node(), headB.node()));

    // (headA, formula) proposed twice but validated once; (headB, formula) once.
    assertThat(outcome.validation().validated()).hasSize(2);
    assertThat(
            outcome.validation().validated().stream().map(v -> v.loopHeadNode()).toList())
        .containsExactly(headA.node(), headB.node());
    assertThat(outcome.rejections()).isEmpty();
  }

  @Test
  public void variableNotInEncodedVocabularyRejected() {
    makeHeads();
    BooleanFormula block = parse("(= x (_ bv1 32))", ENCODED_F1_X);
    PredicateValidationPipeline pipeline =
        new PredicateValidationPipeline(LOGGER, solver, mgrv, false);

    // "w" is neither an encoded variable nor a source name of any encoded variable.
    var outcome =
        pipeline.validateCandidates(
            pack(ENCODED_F1_X, block),
            ImmutableList.of(candidate(headA.label(), "(bvsge w (_ bv0 32))")),
            trace(headA.node()));

    assertThat(outcome.validation().validated()).isEmpty();
    assertThat(outcome.rejections()).hasSize(1);
    assertThat(outcome.rejections().get(0).reason())
        .isEqualTo(PredicateValidationPipeline.REASON_VARIABLE_NOT_IN_SCOPE);
  }

  @Test
  public void variableFromOtherFunctionRejectedAtHead() {
    makeHeads();
    // x only exists in function f2; the named head is in f1.
    ImmutableSet<String> encoded = ImmutableSet.of("f2::x@N5");
    BooleanFormula block = parse("(= x (_ bv1 32))", encoded);
    PredicateValidationPipeline pipeline =
        new PredicateValidationPipeline(LOGGER, solver, mgrv, false);

    var outcome =
        pipeline.validateCandidates(
            pack(encoded, block),
            ImmutableList.of(candidate(headA.label(), "(bvsge x (_ bv0 32))")),
            trace(headA.node()));

    assertThat(outcome.validation().validated()).isEmpty();
    assertThat(outcome.rejections()).hasSize(1);
    assertThat(outcome.rejections().get(0).reason())
        .isEqualTo(PredicateValidationPipeline.REASON_VARIABLE_NOT_IN_SCOPE);
  }

  @Test
  public void variableVisibleAtNamedHeadAccepted() {
    makeHeads();
    BooleanFormula block = parse("(= x (_ bv1 32))", ENCODED_F1_X);
    PredicateValidationPipeline pipeline =
        new PredicateValidationPipeline(LOGGER, solver, mgrv, false);

    var outcome =
        pipeline.validateCandidates(
            pack(ENCODED_F1_X, block),
            ImmutableList.of(candidate(headA.label(), "(bvsge x (_ bv0 32))")),
            trace(headA.node()));

    assertThat(outcome.validation().validated()).hasSize(1);
    assertThat(outcome.rejections()).isEmpty();
  }

  @Test
  public void standardBitvectorLiteralsAcceptedAsConstants() {
    makeHeads();
    BooleanFormula block = parse("(= x (_ bv1 32))", ENCODED_F1_X);
    PredicateValidationPipeline pipeline =
        new PredicateValidationPipeline(LOGGER, solver, mgrv, false);

    var outcome =
        pipeline.validateCandidates(
            pack(ENCODED_F1_X, block),
            ImmutableList.of(
                candidate(headA.label(), "(bvslt x #x00000064)"),
                candidate(headA.label(), "(bvsge x #b00000001)")),
            trace(headA.node()));

    assertThat(outcome.validation().validated()).hasSize(2);
    assertThat(outcome.validation().validated().get(0).formula())
        .isEqualTo(parse("(bvslt x (_ bv100 32))", ENCODED_F1_X));
    assertThat(outcome.validation().validated().get(1).formula())
        .isEqualTo(parse("(bvsge x (_ bv1 8))", ENCODED_F1_X));
    assertThat(outcome.rejections()).isEmpty();
  }

  @Test
  public void overSpecificFlaggedWhenVariableAbsentFromHeadBlock() {
    makeHeads();
    // y is on the trace (encoded vocabulary) but absent from the head block formula.
    ImmutableSet<String> encoded = ImmutableSet.of("f1::x@N5", "f1::y@N9");
    BooleanFormula block = parse("(= x (_ bv1 32))", encoded);
    PredicateValidationPipeline pipeline =
        new PredicateValidationPipeline(LOGGER, solver, mgrv, false);

    var outcome =
        pipeline.validateCandidates(
            pack(encoded, block),
            ImmutableList.of(candidate(headA.label(), "(bvsge y (_ bv0 32))")),
            trace(headA.node()));

    assertThat(outcome.validation().validated()).hasSize(1);
    assertThat(outcome.validation().validated().get(0).overSpecific()).isTrue();
    assertThat(outcome.rejections()).isEmpty();
  }

  @Test
  public void supportingCandidateConflictingWithInitiationSetFlagged() {
    makeHeads();
    BooleanFormula block = parse("(= x (_ bv1 32))", ENCODED_F1_X);
    PredicateValidationPipeline pipeline =
        new PredicateValidationPipeline(LOGGER, solver, mgrv, true);

    var outcome =
        pipeline.validateCandidates(
            pack(ENCODED_F1_X, block),
            // supporting candidate listed first must still be processed after initiation.
            ImmutableList.of(
                new LoopHeadCandidate(
                    ImmutableList.of(headA.label()),
                    "(= x (_ bv2 32))",
                    "supporting",
                    ImmutableList.of()),
                new LoopHeadCandidate(
                    ImmutableList.of(headA.label()),
                    "(= x (_ bv1 32))",
                    "initiation",
                    ImmutableList.of())),
            trace(headA.node()));

    assertThat(outcome.validation().validated()).hasSize(2);
    assertThat(outcome.validation().validated().get(0).role()).isEqualTo("initiation");
    assertThat(outcome.validation().validated().get(0).groupConflict()).isFalse();
    assertThat(outcome.validation().validated().get(1).role()).isEqualTo("supporting");
    assertThat(outcome.validation().validated().get(1).groupConflict()).isTrue();
    assertThat(outcome.rejections()).isEmpty();
  }

  @Test
  public void conflictingCandidateDoesNotPoisonGroupCheckForLaterCandidates() {
    makeHeads();
    BooleanFormula block = parse("(= x (_ bv1 32))", ENCODED_F1_X);
    PredicateValidationPipeline pipeline =
        new PredicateValidationPipeline(LOGGER, solver, mgrv, true);

    var outcome =
        pipeline.validateCandidates(
            pack(ENCODED_F1_X, block),
            ImmutableList.of(
                new LoopHeadCandidate(
                    ImmutableList.of(headA.label()),
                    "(= x (_ bv1 32))",
                    "initiation",
                    ImmutableList.of()),
                new LoopHeadCandidate(
                    ImmutableList.of(headA.label()),
                    "(= x (_ bv2 32))",
                    "supporting",
                    ImmutableList.of()),
                new LoopHeadCandidate(
                    ImmutableList.of(headA.label()),
                    "(bvsge x (_ bv0 32))",
                    "bound",
                    ImmutableList.of())),
            trace(headA.node()));

    assertThat(outcome.validation().validated()).hasSize(3);
    assertThat(outcome.validation().validated().get(0).groupConflict()).isFalse();
    assertThat(outcome.validation().validated().get(1).groupConflict()).isTrue();
    // The conflicting candidate must not poison the group set: the third candidate
    // is checked only against the consistent prefix (initiation).
    assertThat(outcome.validation().validated().get(2).groupConflict()).isFalse();
    assertThat(outcome.rejections()).isEmpty();
  }

  @Test
  public void mixedWidthCandidateValidatesWithSignExtension() {
    makeHeads();
    // x is a 32-bit variable in the encoded vocabulary.
    BooleanFormula block = parse("(= x (_ bv1 32))", ENCODED_F1_X);
    PredicateValidationPipeline pipeline =
        new PredicateValidationPipeline(LOGGER, solver, mgrv, false);

    // A 64-bit constant against a 32-bit variable is aligned by sign-extension
    // (C integer promotion), so the candidate validates instead of being rejected.
    var outcome =
        pipeline.validateCandidates(
            pack(ENCODED_F1_X, block),
            ImmutableList.of(candidate(headA.label(), "(bvsge x (_ bv0 64))")),
            trace(headA.node()));

    assertThat(outcome.validation().validated()).hasSize(1);
    assertThat(outcome.rejections()).isEmpty();
  }

  @Test
  public void sameNameDifferentBitWidthCandidatesBothValidate() {
    makeHeads();
    BooleanFormula block = parse("(= x (_ bv1 32))", ENCODED_F1_X);
    PredicateValidationPipeline pipeline =
        new PredicateValidationPipeline(LOGGER, solver, mgrv, false);

    var outcome =
        pipeline.validateCandidates(
            pack(ENCODED_F1_X, block),
            ImmutableList.of(
                candidate(headA.label(), "(bvsge x (_ bv0 32))"),
                candidate(headA.label(), "(bvsge x (_ bv0 64))")),
            trace(headA.node()));

    // Both candidates validate; the 64-bit constant is sign-extended to match x,
    // which makes the two formulas identical and deduplicated into one entry.
    assertThat(outcome.validation().validated()).hasSize(1);
    assertThat(outcome.rejections()).isEmpty();
  }

  @Test
  public void nestedLoopHeadsValidateOnlyAtNamedHead() {
    // Nested loops: outer head and inner head both on the spurious trace.
    headA = new LoopHeadInfo(newDummyCFANode("f1"), "ignored", "f1"); // outer
    headB = new LoopHeadInfo(newDummyCFANode("f1"), "ignored", "f1"); // inner
    headOffTrace = new LoopHeadInfo(newDummyCFANode("f3"), "ignored", "f3");
    BooleanFormula outerBlock = parse("(bvslt x (_ bv10 32))", ENCODED_F1_X);
    BooleanFormula innerBlock = parse("(bvsge x (_ bv0 32))", ENCODED_F1_X);
    PredicateValidationPipeline pipeline =
        new PredicateValidationPipeline(LOGGER, solver, mgrv, false);

    var outcome =
        pipeline.validateCandidates(
            pack(ENCODED_F1_X, outerBlock, innerBlock),
            ImmutableList.of(candidate(headB.label(), "(bvsge x (_ bv0 32))")),
            trace(headA.node(), headB.node()));

    // The inner-head candidate is validated only at the inner head, never broadcast
    // to the outer head.
    assertThat(outcome.validation().validated()).hasSize(1);
    assertThat(outcome.validation().validated().get(0).loopHeadNode()).isEqualTo(headB.node());
    assertThat(outcome.rejections()).isEmpty();
  }

  private record LocState(CFANode node) implements AbstractStateWithLocation {
    @Override
    public CFANode getLocationNode() {
      return node;
    }

    @Override
    public Iterable<CFAEdge> getOutgoingEdges() {
      return ImmutableList.of();
    }
  }
}
