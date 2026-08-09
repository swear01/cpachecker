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
  public void preservesNestedLoopHeadOrderAndCompressesLongTrace() {
    CFANode outer = newDummyCFANode("main");
    CFANode branch = newDummyCFANode("main");
    CFANode inner = newDummyCFANode("main");
    ImmutableList.Builder<org.sosy_lab.cpachecker.core.interfaces.AbstractState> trace =
        ImmutableList.builder();
    trace.add(new LocState(outer));
    for (int i = 0; i < 100; i++) {
      trace.add(new LocState(branch));
    }
    trace.add(new LocState(inner));
    String json =
        StructuredCounterexampleBuilder.build(
            "x < n",
            ImmutableList.of(
                new LoopHeadInfo(outer, "ignored", "main"),
                new LoopHeadInfo(inner, "ignored", "main")),
            trace.build(),
            "");

    assertThat(json).contains("\"loop_head\":\"N" + outer.getNodeNumber() + "\"");
    assertThat(json).contains("\"loop_head\":\"N" + inner.getNodeNumber() + "\"");
    assertThat(json).contains("\"repeat_count\":100");
    assertThat(json.indexOf("\"node\":" + outer.getNodeNumber()))
        .isLessThan(json.indexOf("\"node\":" + inner.getNodeNumber()));
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
    String escaped =
        StructuredCounterexampleBuilder.build(
            "a\r\tb", ImmutableList.of(), ImmutableList.of(), "c\r\td");
    assertThat(escaped).contains("\"assertion\":\"a\\r\\tb\"");
    assertThat(escaped).contains("\"relations\":\"c\\r\\td\"");
    assertThat(StructuredCounterexampleBuilder.build("a\u0001b", ImmutableList.of(), ImmutableList.of(), ""))
        .contains("\"assertion\":\"a\\u0001b\"");
    assertThat(StructuredCounterexampleBuilder.build("", null, null, ""))
        .contains("\"trace\":[]");
    assertThat(
            StructuredCounterexampleBuilder.build(
                "", ImmutableList.of(), ImmutableList.of(new LocState(null)), ""))
        .contains("\"trace\":[]");
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
