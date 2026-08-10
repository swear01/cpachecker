// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import com.google.common.collect.ImmutableList;
import org.sosy_lab.cpachecker.cfa.model.CFANode;
import org.sosy_lab.java_smt.api.BooleanFormula;

/**
 * A predicate that passed parsing and SMT classification at one explicit loop head.
 *
 * <p>One record covers exactly one (formula, loop head) binding; a multi-head candidate expands to
 * one record per head. {@code role} and {@code variables} are candidate metadata recorded for
 * grouped validation and dump attribution.
 */
public record ValidatedPredicate(
    BooleanFormula formula,
    CFANode loopHeadNode,
    Classification classification,
    String role,
    ImmutableList<String> variables) {

  public enum Classification {
    ENTAILED,
    PRECISION_ONLY
  }
}
