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
import org.junit.Test;
import org.sosy_lab.cpachecker.cfa.model.CFANode;
import org.sosy_lab.cpachecker.cpa.predicate.BlockFormulaStrategy.BlockFormulas;
import org.sosy_lab.cpachecker.util.predicates.smt.SolverViewBasedTest0;
import org.sosy_lab.java_smt.api.BooleanFormula;

public class CeSummaryBuilderTest extends SolverViewBasedTest0 {

  @Test
  public void listsLoopHeadBlockSummary() {
    CFANode head = newDummyCFANode("loop");
    LoopHeadInfo headInfo = new LoopHeadInfo(head, "N1", "main");
    BooleanFormula block = bmgrv.not(bmgrv.makeTrue());
    BlockFormulas formulas = new BlockFormulas(ImmutableList.of(block));
    ImmutableMap<String, ImmutableSet<String>> contract = ImmutableMap.of();
    String summary =
        CeSummaryBuilder.build(
            mgrv,
            formulas,
            ImmutableList.of(),
            ImmutableList.of(headInfo),
            contract,
            "i < n",
            ImmutableList.of(new LocState(head)));
    assertThat(summary).contains("L@N" + head.getNodeNumber());
    assertThat(summary).doesNotContain("declare-fun");
  }

  private record LocState(CFANode node)
      implements org.sosy_lab.cpachecker.core.interfaces.AbstractStateWithLocation {
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
