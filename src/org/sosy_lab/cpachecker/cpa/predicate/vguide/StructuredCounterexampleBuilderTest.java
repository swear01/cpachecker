// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.truth.Truth.assertThat;
import static org.sosy_lab.cpachecker.cfa.model.CFANode.newDummyCFANode;

import com.google.common.collect.ImmutableList;
import java.util.List;
import org.junit.Test;
import java.nio.file.Path;
import java.util.Optional;
import org.sosy_lab.cpachecker.cfa.ast.AAstNode;
import org.sosy_lab.cpachecker.cfa.ast.FileLocation;
import org.sosy_lab.cpachecker.cfa.model.CFAEdge;
import org.sosy_lab.cpachecker.cfa.model.CFAEdgeType;
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
            ImmutableList.of(new LocState(head, List.of()), new LocState(head, List.of()), new LocState(exit, List.of())),
            "L@N" + head.getNodeNumber() + ": (= x n)\n");

    assertThat(json).isEqualTo(StructuredCounterexampleBuilder.build(
        "x < n",
        ImmutableList.of(new LoopHeadInfo(head, "ignored", "main")),
        ImmutableList.of(new LocState(head, List.of()), new LocState(head, List.of()), new LocState(exit, List.of())),
        "L@N" + head.getNodeNumber() + ": (= x n)\n"));
    assertThat(json).contains("\"schema_version\":\"structured-ce-v2\"");
    assertThat(json).contains("\"repeat_count\":2");
    assertThat(json).contains("\"loop_head\":\"N" + head.getNodeNumber() + "\"");
    assertThat(json).contains("\"unavailable\":[\"branch_conditions\",\"ssa_values\",\"assignments\"]");
    // dummy nodes have no real file locations: source must be explicitly unavailable.
    assertThat(json).contains("\"source\":null");
  }

  @Test
  public void realEdgeLocationsProduceSourceSlice() {
    CFANode head = newDummyCFANode("main");
    String json =
        StructuredCounterexampleBuilder.build(
            "x < n",
            ImmutableList.of(new LoopHeadInfo(head, "ignored", "main")),
            ImmutableList.of(
                new LocState(
                    head,
                    List.of(
                        new SourcedEdge(
                            Path.of("bench.c"), 0, 4, 7, 9, 1, 5)))),
            "");
    assertThat(json).contains("\"source\":{\"file\":\"bench.c\",\"line\":7,\"end_line\":9}");
  }

  @Test
  public void preservesNestedLoopHeadOrderAndCompressesLongTrace() {
    CFANode outer = newDummyCFANode("main");
    CFANode branch = newDummyCFANode("main");
    CFANode inner = newDummyCFANode("main");
    ImmutableList.Builder<org.sosy_lab.cpachecker.core.interfaces.AbstractState> trace =
        ImmutableList.builder();
    trace.add(new LocState(outer, List.of()));
    for (int i = 0; i < 100; i++) {
      trace.add(new LocState(branch, List.of()));
    }
    trace.add(new LocState(inner, List.of()));
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
            ImmutableList.of(new LocState(head, List.of())),
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
                "", ImmutableList.of(), ImmutableList.of(new LocState(null, List.of())), ""))
        .contains("\"trace\":[]");
  }

  private record LocState(CFANode node, List<CFAEdge> edges) implements AbstractStateWithLocation {
    @Override
    public CFANode getLocationNode() {
      return node;
    }

    @Override
    public Iterable<CFAEdge> getOutgoingEdges() {
      return edges;
    }
  }

  private record SourcedEdge(FileLocation location) implements CFAEdge {
    SourcedEdge(
        Path file,
        int offset,
        int length,
        int startLine,
        int endLine,
        int startCol,
        int endCol) {
      this(new FileLocation(file, offset, length, startLine, endLine, startCol, endCol));
    }

    @Override
    public CFAEdgeType getEdgeType() {
      return CFAEdgeType.StatementEdge;
    }

    @Override
    public CFANode getPredecessor() {
      return null;
    }

    @Override
    public CFANode getSuccessor() {
      return null;
    }

    @Override
    public Optional<AAstNode> getRawAST() {
      return Optional.empty();
    }

    @Override
    public int getLineNumber() {
      return location.getStartingLineNumber();
    }

    @Override
    public FileLocation getFileLocation() {
      return location;
    }

    @Override
    public String getRawStatement() {
      return "x < n;";
    }

    @Override
    public String getCode() {
      return "x < n;";
    }

    @Override
    public String getDescription() {
      return "x < n;";
    }
  }
}
