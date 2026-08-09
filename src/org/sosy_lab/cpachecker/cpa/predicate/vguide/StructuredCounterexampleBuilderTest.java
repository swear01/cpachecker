// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.truth.Truth.assertThat;
import static org.sosy_lab.cpachecker.cfa.model.CFANode.newDummyCFANode;

import com.google.common.collect.ImmutableList;
import org.junit.Test;
import org.sosy_lab.cpachecker.cfa.model.CFANode;
import org.sosy_lab.cpachecker.core.interfaces.AbstractStateWithLocation;

public class StructuredCounterexampleBuilderTest {

  @Test
  public void serializesDeterministicCompressedTraceWithUnavailableMetadata() {
    CFANode head = newDummyCFANode("main");
    CFANode exit = newDummyCFANode("main");
    String json =
        StructuredCounterexampleBuilder.build(
            "x < n",
            ImmutableList.of(new LoopHeadInfo(head, "ignored", "main")),
            ImmutableList.of(new LocState(head), new LocState(head), new LocState(exit)),
            "L@N" + head.getNodeNumber() + ": (= x n)\n");

    assertThat(json).isEqualTo(StructuredCounterexampleBuilder.build(
        "x < n",
        ImmutableList.of(new LoopHeadInfo(head, "ignored", "main")),
        ImmutableList.of(new LocState(head), new LocState(head), new LocState(exit)),
        "L@N" + head.getNodeNumber() + ": (= x n)\n"));
    assertThat(json).contains("\"schema_version\":\"structured-ce-v1\"");
    assertThat(json).contains("\"repeat_count\":2");
    assertThat(json).contains("\"loop_head\":\"N" + head.getNodeNumber() + "\"");
    assertThat(json).contains("\"unavailable\":[\"branch_conditions\",\"ssa_values\",\"assignments\"]");
  }

  @Test
  public void toleratesDuplicateLoopHeadsAndMissingText() {
    CFANode head = newDummyCFANode("main");
    String json =
        StructuredCounterexampleBuilder.build(
            null,
            ImmutableList.of(
                new LoopHeadInfo(head, "ignored", "main"),
                new LoopHeadInfo(head, "ignored", "main")),
            ImmutableList.of(new LocState(head)),
            null);

    assertThat(json).contains("\"assertion\":\"\"");
    assertThat(json).contains("\"relations\":\"\"");
    assertThat(json).contains("\"loop_head\":\"N" + head.getNodeNumber() + "\"");
  }

  private record LocState(CFANode node) implements AbstractStateWithLocation {
    @Override
    public CFANode getLocationNode() {
      return node;
    }

    @Override
    public java.util.List<org.sosy_lab.cpachecker.cfa.model.CFAEdge> getOutgoingEdges() {
      return java.util.List.of();
    }
  }
}
