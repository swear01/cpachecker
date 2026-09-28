// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.truth.Truth.assertThat;
import static org.sosy_lab.cpachecker.cfa.model.CFANode.newDummyCFANode;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.google.common.collect.ImmutableList;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import org.junit.Test;
import org.sosy_lab.common.ShutdownNotifier;
import org.sosy_lab.common.log.LogManager;
import org.sosy_lab.cpachecker.cfa.CFA;
import org.sosy_lab.cpachecker.cfa.CFACreator;
import org.sosy_lab.cpachecker.cfa.ast.AAstNode;
import org.sosy_lab.cpachecker.cfa.ast.FileLocation;
import org.sosy_lab.cpachecker.cfa.model.CFAEdge;
import org.sosy_lab.cpachecker.cfa.model.CFAEdgeType;
import org.sosy_lab.cpachecker.cfa.model.CFANode;
import org.sosy_lab.cpachecker.cfa.model.c.CAssumeEdge;
import org.sosy_lab.cpachecker.cfa.model.c.CStatementEdge;
import org.sosy_lab.cpachecker.core.interfaces.AbstractStateWithLocation;
import org.sosy_lab.cpachecker.cpa.arg.ARGState;
import org.sosy_lab.cpachecker.cpa.arg.path.ARGPath;
import org.sosy_lab.cpachecker.util.CFAUtils;
import org.sosy_lab.cpachecker.util.test.TestDataTools;

public class StructuredCounterexampleBuilderTest {

  @Test
  public void proofStepsUseTakenContiguousArgPathAndKeepAssignmentsWhole() throws Exception {
    Path source = java.nio.file.Files.createTempFile("vguide_steps_", ".c");
    source.toFile().deleteOnExit();
    java.nio.file.Files.writeString(
        source, "int main(){int x=0; if (x < 1) x = 123456789; else x = 2; return x;}\n");
    CFA cfa =
        new CFACreator(
                TestDataTools.configurationForTest().build(),
                LogManager.createTestLogManager(),
                ShutdownNotifier.createDummy())
            .parseFileAndCreateCFA(ImmutableList.of(source.toString()));
    CAssumeEdge falseEdge =
        CFAUtils.allEdges(cfa)
            .filter(CAssumeEdge.class)
            .filter(edge -> !edge.getTruthAssumption())
            .first()
            .get();
    CStatementEdge assignment =
        falseEdge.getSuccessor().getLeavingEdges().stream()
            .filter(CStatementEdge.class::isInstance)
            .map(CStatementEdge.class::cast)
            .filter(edge -> edge.getRawStatement().contains("x = 2"))
            .findFirst()
            .get();
    ARGPath path =
        new ARGPath(
            ImmutableList.of(
                new ARGState(null, null), new ARGState(null, null), new ARGState(null, null)),
            ImmutableList.of(falseEdge, assignment),
            ImmutableList.of(falseEdge, assignment));
    String json =
        StructuredCounterexampleBuilder.withProofSteps(
            StructuredCounterexampleBuilder.build("", ImmutableList.of(), ImmutableList.of(), ""),
            path.getFullPath(),
            ImmutableList.of(
                new LoopHeadInfo(falseEdge.getPredecessor(), "Before", "main"),
                new LoopHeadInfo(falseEdge.getSuccessor(), "After", "main")),
            Optional.empty());

    JsonNode parsed = new ObjectMapper().readTree(json);
    assertThat(parsed.has("relations")).isTrue();
    assertThat(parsed.path("proof_steps").size()).isEqualTo(2);
    assertThat(parsed.path("proof_steps").get(0).path("taken").asBoolean()).isFalse();
    assertThat(parsed.path("proof_steps").get(1).path("rhs").asText()).isEqualTo("2");
    JsonNode headRelations = parsed.path("proof_steps").get(0).path("head_relations");
    assertThat(headRelations.size()).isEqualTo(2);
    assertThat(headRelations.get(0).path("head").asText())
        .isEqualTo("N" + falseEdge.getPredecessor().getNodeNumber());
    assertThat(headRelations.get(1).path("head").asText())
        .isEqualTo("N" + falseEdge.getSuccessor().getNodeNumber());
    assertThat(headRelations.get(0).path("relation").asText()).isEqualTo("unknown");
    assertThat(headRelations.get(1).path("relation").asText()).isEqualTo("unknown");
    assertThat(json).doesNotContain("123456789");
    assertThat(json).doesNotContain("\"branch_conditions\"");
    assertThat(json).contains("\"unavailable\":[\"ssa_values\"]");

    String unavailable =
        StructuredCounterexampleBuilder.build("", ImmutableList.of(), ImmutableList.of(), "");
    assertThat(
            StructuredCounterexampleBuilder.withProofSteps(
                unavailable, ImmutableList.of(), ImmutableList.of(), Optional.empty()))
        .isEqualTo(unavailable);
  }

  @Test
  public void proofStepsKeepASuffixWithoutFillingHolesBeforeAnOversizedStep() throws Exception {
    Path source = java.nio.file.Files.createTempFile("vguide_long_steps_", ".c");
    source.toFile().deleteOnExit();
    java.nio.file.Files.writeString(
        source,
        "int main(){char *s;int x=0;if(x<1)return 123456789;else{"
            + "x=x+1;".repeat(200)
            + "s=\"" + "a".repeat(20_000) + "\";"
            + "x=2;}return x;}\n");
    CFA cfa =
        new CFACreator(
                TestDataTools.configurationForTest().build(),
                LogManager.createTestLogManager(),
                ShutdownNotifier.createDummy())
            .parseFileAndCreateCFA(ImmutableList.of(source.toString()));
    CAssumeEdge falseEdge =
        CFAUtils.allEdges(cfa)
            .filter(CAssumeEdge.class)
            .filter(edge -> !edge.getTruthAssumption())
            .first()
            .get();
    List<CFAEdge> path = new ArrayList<>();
    path.add(falseEdge);
    CFANode node = falseEdge.getSuccessor();
    while (node.getNumLeavingEdges() == 1) {
      CFAEdge edge = node.getLeavingEdge(0);
      path.add(edge);
      node = edge.getSuccessor();
    }
    for (int index = 0; index < path.size() - 1; index++) {
      assertThat(path.get(index).getSuccessor()).isEqualTo(path.get(index + 1).getPredecessor());
    }

    JsonNode parsed =
        new ObjectMapper()
            .readTree(
                StructuredCounterexampleBuilder.withProofSteps(
                    StructuredCounterexampleBuilder.build(
                        "", ImmutableList.of(), ImmutableList.of(), ""),
                    path,
                    ImmutableList.of(),
                    cfa.getLoopStructure()));

    assertThat(parsed.path("proof_steps_omitted").asInt()).isEqualTo(202);
    assertThat(parsed.path("proof_steps").size()).isEqualTo(1);
    assertThat(parsed.path("proof_steps").toString().length())
        .isAtMost(StructuredCounterexampleBuilder.MAX_PROOF_STEP_CHARS);
    assertThat(parsed.path("proof_steps").get(0).path("occurrence").asInt()).isGreaterThan(1);
    assertThat(
            parsed
                .path("proof_steps")
                .get(parsed.path("proof_steps").size() - 1)
                .path("rhs")
                .asText())
        .isEqualTo("2");
  }

  @Test
  public void serializesDeterministicCompressedTraceWithUnavailableMetadata() {
    CFANode head = newDummyCFANode("main");
    CFANode exit = newDummyCFANode("main");
    String json =
        StructuredCounterexampleBuilder.build(
            "x < n",
            ImmutableList.of(new LoopHeadInfo(head, "ignored", "main")),
            ImmutableList.of(
                new LocState(head, List.of()),
                new LocState(head, List.of()),
                new LocState(exit, List.of())),
            "L@N" + head.getNodeNumber() + ": (= x n)\n");

    assertThat(json)
        .isEqualTo(
            StructuredCounterexampleBuilder.build(
                "x < n",
                ImmutableList.of(new LoopHeadInfo(head, "ignored", "main")),
                ImmutableList.of(
                    new LocState(head, List.of()),
                    new LocState(head, List.of()),
                    new LocState(exit, List.of())),
                "L@N" + head.getNodeNumber() + ": (= x n)\n"));
    assertThat(json).contains("\"schema_version\":\"structured-ce-v2\"");
    assertThat(json).contains("\"repeat_count\":2");
    assertThat(json).contains("\"loop_head\":\"N" + head.getNodeNumber() + "\"");
    assertThat(json)
        .contains("\"unavailable\":[\"branch_conditions\",\"ssa_values\",\"assignments\"]");
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
                new LocState(head, List.of(new SourcedEdge(Path.of("bench.c"), 0, 4, 7, 9, 1, 5)))),
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
    assertThat(
            StructuredCounterexampleBuilder.build(
                "a\u0001b", ImmutableList.of(), ImmutableList.of(), ""))
        .contains("\"assertion\":\"a\\u0001b\"");
    assertThat(StructuredCounterexampleBuilder.build("", null, null, "")).contains("\"trace\":[]");
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
        Path file, int offset, int length, int startLine, int endLine, int startCol, int endCol) {
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
