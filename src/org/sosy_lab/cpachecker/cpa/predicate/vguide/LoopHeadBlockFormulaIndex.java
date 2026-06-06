// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static org.sosy_lab.cpachecker.util.AbstractStates.extractLocation;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.sosy_lab.cpachecker.cfa.model.CFANode;
import org.sosy_lab.cpachecker.core.interfaces.AbstractState;
import org.sosy_lab.cpachecker.cpa.predicate.BlockFormulaStrategy.BlockFormulas;
import org.sosy_lab.java_smt.api.BooleanFormula;

/**
 * Maps each CFA node on the spurious trace to its block formula. Loop heads not appearing on the
 * trace are omitted (no fallback to the first block).
 */
final class LoopHeadBlockFormulaIndex {

  private LoopHeadBlockFormulaIndex() {}

  static Map<CFANode, BooleanFormula> fromTrace(
      BlockFormulas blockFormulas, List<? extends AbstractState> abstractionTrace) {
    Map<CFANode, BooleanFormula> map = new HashMap<>();
    int n = Math.min(blockFormulas.getSize(), abstractionTrace.size());
    for (int i = 0; i < n; i++) {
      CFANode node = extractLocation(abstractionTrace.get(i));
      if (node != null) {
        map.put(node, blockFormulas.getFormulas().get(i));
      }
    }
    return map;
  }
}
