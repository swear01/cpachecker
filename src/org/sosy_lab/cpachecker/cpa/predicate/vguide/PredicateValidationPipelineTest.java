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

/** Mapping policy: candidates validate only at their named loop heads; no implicit broadcast. */
public class PredicateValidationPipelineTest extends SolverViewBasedTest0 {

  private static final LogManager LOGGER = LogManager.createNullLogManager();

  private LoopHeadInfo headA;
  private LoopHeadInfo headB;
  private LoopHeadInfo headOffTrace;

  private ContextPack pack(BooleanFormula... blocks) {
    ImmutableList<LoopHeadInfo> heads = ImmutableList.of(headA, headB, headOffTrace);
    return new ContextPack(
        1,
        "",
        "",
        heads,
        ImmutableMap.of(),
        ImmutableSet.of(),
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
    headA = new LoopHeadInfo(newDummyCFANode("f1"), "ignored", "f1");
    headB = new LoopHeadInfo(newDummyCFANode("f2"), "ignored", "f2");
    headOffTrace = new LoopHeadInfo(newDummyCFANode("f3"), "ignored", "f3");
    BooleanFormula block =
        VocabularyGuide.parsePredicate("(= x (_ bv1 32))", mgrv, ImmutableSet.of());
    PredicateValidationPipeline pipeline =
        new PredicateValidationPipeline(LOGGER, solver, mgrv, false);

    var outcome =
        pipeline.validateCandidates(
            pack(block, block),
            ImmutableList.of(candidate(headA.label(), "(= x (_ bv1 32))")),
            trace(headA.node(), headB.node()));

    assertThat(outcome.validation().validated()).hasSize(1);
    assertThat(outcome.validation().validated().get(0).loopHeadNode()).isEqualTo(headA.node());
    assertThat(outcome.rejections()).isEmpty();
  }

  @Test
  public void multiHeadCandidateValidatedAtEachNamedHead() {
    headA = new LoopHeadInfo(newDummyCFANode("f1"), "ignored", "f1");
    headB = new LoopHeadInfo(newDummyCFANode("f2"), "ignored", "f2");
    headOffTrace = new LoopHeadInfo(newDummyCFANode("f3"), "ignored", "f3");
    BooleanFormula block =
        VocabularyGuide.parsePredicate("(= x (_ bv1 32))", mgrv, ImmutableSet.of());
    PredicateValidationPipeline pipeline =
        new PredicateValidationPipeline(LOGGER, solver, mgrv, false);

    var outcome =
        pipeline.validateCandidates(
            pack(block, block),
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
    headA = new LoopHeadInfo(newDummyCFANode("f1"), "ignored", "f1");
    headB = new LoopHeadInfo(newDummyCFANode("f2"), "ignored", "f2");
    headOffTrace = new LoopHeadInfo(newDummyCFANode("f3"), "ignored", "f3");
    BooleanFormula block =
        VocabularyGuide.parsePredicate("(= x (_ bv1 32))", mgrv, ImmutableSet.of());
    PredicateValidationPipeline pipeline =
        new PredicateValidationPipeline(LOGGER, solver, mgrv, false);

    var outcome =
        pipeline.validateCandidates(
            pack(block),
            ImmutableList.of(candidate("N999", "(= x (_ bv1 32))")),
            trace(headA.node()));

    assertThat(outcome.validation().validated()).isEmpty();
    assertThat(outcome.rejections()).hasSize(1);
    assertThat(outcome.rejections().get(0).reason())
        .isEqualTo(PredicateValidationPipeline.REASON_UNKNOWN_LOOP_HEAD);
  }

  @Test
  public void headNotOnTraceRejected() {
    headA = new LoopHeadInfo(newDummyCFANode("f1"), "ignored", "f1");
    headB = new LoopHeadInfo(newDummyCFANode("f2"), "ignored", "f2");
    headOffTrace = new LoopHeadInfo(newDummyCFANode("f3"), "ignored", "f3");
    BooleanFormula block =
        VocabularyGuide.parsePredicate("(= x (_ bv1 32))", mgrv, ImmutableSet.of());
    PredicateValidationPipeline pipeline =
        new PredicateValidationPipeline(LOGGER, solver, mgrv, false);

    var outcome =
        pipeline.validateCandidates(
            pack(block),
            ImmutableList.of(candidate(headOffTrace.label(), "(= x (_ bv1 32))")),
            trace(headA.node()));

    assertThat(outcome.validation().validated()).isEmpty();
    assertThat(outcome.rejections()).hasSize(1);
    assertThat(outcome.rejections().get(0).reason())
        .isEqualTo(PredicateValidationPipeline.REASON_HEAD_NOT_ON_TRACE);
  }

  @Test
  public void parseErrorRejected() {
    headA = new LoopHeadInfo(newDummyCFANode("f1"), "ignored", "f1");
    headB = new LoopHeadInfo(newDummyCFANode("f2"), "ignored", "f2");
    headOffTrace = new LoopHeadInfo(newDummyCFANode("f3"), "ignored", "f3");
    BooleanFormula block =
        VocabularyGuide.parsePredicate("(= x (_ bv1 32))", mgrv, ImmutableSet.of());
    PredicateValidationPipeline pipeline =
        new PredicateValidationPipeline(LOGGER, solver, mgrv, false);

    var outcome =
        pipeline.validateCandidates(
            pack(block),
            ImmutableList.of(candidate(headA.label(), "(= x")),
            trace(headA.node()));

    assertThat(outcome.validation().validated()).isEmpty();
    assertThat(outcome.rejections()).hasSize(1);
    assertThat(outcome.rejections().get(0).reason())
        .isEqualTo(PredicateValidationPipeline.REASON_PARSE_ERROR);
  }

  @Test
  public void l3EntailmentClassifiesEntailedAndPrecisionOnly() {
    headA = new LoopHeadInfo(newDummyCFANode("f1"), "ignored", "f1");
    headB = new LoopHeadInfo(newDummyCFANode("f2"), "ignored", "f2");
    headOffTrace = new LoopHeadInfo(newDummyCFANode("f3"), "ignored", "f3");
    BooleanFormula block =
        VocabularyGuide.parsePredicate("(= x (_ bv1 32))", mgrv, ImmutableSet.of());
    PredicateValidationPipeline pipeline =
        new PredicateValidationPipeline(LOGGER, solver, mgrv, true);

    var outcome =
        pipeline.validateCandidates(
            pack(block),
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
    headA = new LoopHeadInfo(newDummyCFANode("f1"), "ignored", "f1");
    headB = new LoopHeadInfo(newDummyCFANode("f2"), "ignored", "f2");
    headOffTrace = new LoopHeadInfo(newDummyCFANode("f3"), "ignored", "f3");
    BooleanFormula block =
        VocabularyGuide.parsePredicate("(= x (_ bv1 32))", mgrv, ImmutableSet.of());
    PredicateValidationPipeline pipeline =
        new PredicateValidationPipeline(LOGGER, solver, mgrv, false);

    var outcome =
        pipeline.validateCandidates(
            pack(block),
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
