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
import org.sosy_lab.cpachecker.cfa.model.CFAEdge;
import org.sosy_lab.cpachecker.cfa.model.CFANode;
import org.sosy_lab.cpachecker.core.interfaces.AbstractState;
import org.sosy_lab.cpachecker.core.interfaces.AbstractStateWithLocation;
import org.sosy_lab.cpachecker.cpa.predicate.BlockFormulaStrategy.BlockFormulas;
import org.sosy_lab.cpachecker.util.predicates.smt.SolverViewBasedTest0;
import org.sosy_lab.java_smt.api.BooleanFormula;

/** Loop-head block formulas must come from trace alignment only (no first-block fallback). */
public class LoopHeadBlockFormulaIndexTest extends SolverViewBasedTest0 {

  @Test
  public void mapsOnlyNodesOnTrace_noFallbackForMissingLoopHead() {
    CFANode onTrace = newDummyCFANode("onTrace");
    CFANode loopHeadNotOnTrace = newDummyCFANode("loopHead");
    BooleanFormula fOnTrace = bmgrv.makeTrue();
    BooleanFormula fLoop = bmgrv.makeFalse();

    var map =
        LoopHeadBlockFormulaIndex.fromTrace(
            new BlockFormulas(ImmutableList.of(fOnTrace)),
            ImmutableList.of(new LocState(onTrace)));

    assertThat(map).containsEntry(onTrace, fOnTrace);
    assertThat(map).doesNotContainKey(loopHeadNotOnTrace);
    assertThat(map.get(loopHeadNotOnTrace)).isNull();
    assertThat(fLoop).isNotNull();
  }

  private record LocState(CFANode node) implements AbstractStateWithLocation {
    @Override
    public CFANode getLocationNode() {
      return node;
    }

    @Override
    public Iterable<CFAEdge> getOutgoingEdges() {
      return List.of();
    }
  }
}
