// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import com.google.common.collect.ImmutableList;
import java.util.LinkedHashSet;
import java.util.Optional;
import java.util.Set;
import org.sosy_lab.cpachecker.cfa.model.CFANode;
import org.sosy_lab.cpachecker.util.LoopStructure;
import org.sosy_lab.cpachecker.util.LoopStructure.Loop;

/** Collects loop-head CFA nodes (LBE-aligned injection sites). */
public final class LoopHeadIndex {

  private final ImmutableList<LoopHeadInfo> loopHeads;

  public LoopHeadIndex(Optional<LoopStructure> loopStructure) {
    Set<CFANode> seen = new LinkedHashSet<>();
    ImmutableList.Builder<LoopHeadInfo> builder = ImmutableList.builder();
    if (loopStructure.isPresent()) {
      for (Loop loop : loopStructure.orElseThrow().getAllLoops()) {
        for (CFANode head : loop.getLoopHeads()) {
          if (seen.add(head)) {
            builder.add(
                new LoopHeadInfo(head, "N" + head.getNodeNumber(), head.getFunctionName()));
          }
        }
      }
    }
    loopHeads = builder.build();
  }

  public ImmutableList<LoopHeadInfo> getLoopHeads() {
    return loopHeads;
  }

  public String formatForPrompt() {
    if (loopHeads.isEmpty()) {
      return "(no loop heads detected)\n";
    }
    StringBuilder sb = new StringBuilder();
    sb.append("LOOP HEADS (inject predicates here — use source variable names only):\n");
    for (LoopHeadInfo h : loopHeads) {
      sb.append("  ")
          .append(h.label())
          .append(" (function ")
          .append(h.functionName())
          .append(" loop head)\n");
    }
    return sb.toString();
  }
}
