// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import com.google.common.collect.ImmutableList;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import org.sosy_lab.cpachecker.cfa.model.CFANode;
import org.sosy_lab.cpachecker.core.interfaces.AbstractState;
import org.sosy_lab.cpachecker.core.interfaces.AbstractStateWithLocation;

/** Serializes authoritative CEGAR trace facts into the versioned prompt artifact. */
final class StructuredCounterexampleBuilder {

  static final String SCHEMA_VERSION = "structured-ce-v1";

  private StructuredCounterexampleBuilder() {}

  static String build(
      String assertion,
      ImmutableList<LoopHeadInfo> loopHeads,
      List<? extends AbstractState> abstractionTrace,
      String relationSummary) {
    Map<CFANode, LoopHeadInfo> heads =
        loopHeads.stream()
            .filter(head -> head != null && head.node() != null)
            .collect(Collectors.toMap(LoopHeadInfo::node, head -> head, (first, ignored) -> first));
    List<TraceSegment> segments = new ArrayList<>();
    for (AbstractState state : abstractionTrace) {
      if (!(state instanceof AbstractStateWithLocation located)) {
        continue;
      }
      CFANode node = located.getLocationNode();
      LoopHeadInfo head = heads.get(node);
      TraceSegment next =
          new TraceSegment(node.getNodeNumber(), node.getFunctionName(), head == null ? "" : head.label(), 1);
      if (!segments.isEmpty() && segments.get(segments.size() - 1).sameLocation(next)) {
        segments.set(segments.size() - 1, segments.get(segments.size() - 1).increment());
      } else {
        segments.add(next);
      }
    }
    StringBuilder out = new StringBuilder("{\"schema_version\":\"")
        .append(SCHEMA_VERSION)
        .append("\",\"assertion\":\"")
        .append(escape(assertion))
        .append("\",\"trace\":[");
    for (int i = 0; i < segments.size(); i++) {
      if (i > 0) {
        out.append(',');
      }
      TraceSegment segment = segments.get(i);
      out.append("{\"node\":").append(segment.nodeNumber())
          .append(",\"function\":\"").append(escape(segment.functionName()))
          .append("\",\"loop_head\":");
      if (segment.loopHead().isEmpty()) {
        out.append("null");
      } else {
        out.append('"').append(escape(segment.loopHead())).append('"');
      }
      out.append(",\"repeat_count\":").append(segment.repeatCount()).append('}');
    }
    return out.append("],\"relations\":\"")
        .append(escape(relationSummary == null ? "" : relationSummary.strip()))
        .append("\",\"unavailable\":[\"branch_conditions\",\"ssa_values\",\"assignments\"]}")
        .toString();
  }

  private static String escape(String value) {
    if (value == null) {
      return "";
    }
    return value.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n");
  }

  private record TraceSegment(int nodeNumber, String functionName, String loopHead, int repeatCount) {
    boolean sameLocation(TraceSegment other) {
      return nodeNumber == other.nodeNumber && functionName.equals(other.functionName());
    }

    TraceSegment increment() {
      return new TraceSegment(nodeNumber, functionName, loopHead, repeatCount + 1);
    }
  }
}
