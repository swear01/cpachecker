// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import org.sosy_lab.cpachecker.cfa.model.CFANode;
import org.sosy_lab.java_smt.api.BooleanFormula;

/** A predicate that passed parsing and SMT classification. */
public record ValidatedPredicate(
    BooleanFormula formula,
    CFANode loopHeadNode,
    Classification classification) {

  public enum Classification {
    ENTAILED,
    PRECISION_ONLY
  }
}
