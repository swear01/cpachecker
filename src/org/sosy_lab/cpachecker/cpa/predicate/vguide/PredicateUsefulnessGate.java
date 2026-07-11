// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableSet;
import com.google.common.hash.Hashing;
import java.nio.charset.StandardCharsets;
import org.sosy_lab.cpachecker.util.predicates.smt.FormulaManagerView;

final class PredicateUsefulnessGate {

  static final String RULE_VERSION = "frozen-20260711";
  private static final int MAX_SHORT_PEEL_VISITS = 8;
  private static final int MIN_MULTIPLICATIVE_PREDICATES_TO_REJECT = 2;

  enum Action {
    ACCEPT,
    REJECT_AND_SUPPRESS_FUTURE_CALLS
  }

  record Decision(
      Action action,
      int loopHeadVisits,
      int uniqueValidatedPredicates,
      int uniqueMultiplicativePredicates,
      ImmutableList<String> canonicalPredicateHashes) {

    boolean rejects() {
      return action == Action.REJECT_AND_SUPPRESS_FUTURE_CALLS;
    }
  }

  private PredicateUsefulnessGate() {}

  static Decision evaluate(
      int pLoopHeadVisits, ValidationResult pCurrentBatch, FormulaManagerView pFmgr) {
    return evaluateDumped(
        pLoopHeadVisits,
        pCurrentBatch.validated().stream()
            .map(validated -> pFmgr.dumpFormula(validated.formula()).toString())
            .toList());
  }

  static Decision evaluateDumped(int pLoopHeadVisits, Iterable<String> pPredicateFormulas) {
    ImmutableList<String> uniqueFormulas =
        ImmutableList.sortedCopyOf(ImmutableSet.copyOf(pPredicateFormulas));
    int multiplicativePredicates = 0;
    for (String formula : uniqueFormulas) {
      if (formula.contains("bvmul")) {
        multiplicativePredicates++;
      }
    }
    Action action =
        pLoopHeadVisits <= MAX_SHORT_PEEL_VISITS
                && multiplicativePredicates >= MIN_MULTIPLICATIVE_PREDICATES_TO_REJECT
            ? Action.REJECT_AND_SUPPRESS_FUTURE_CALLS
            : Action.ACCEPT;
    ImmutableList<String> hashes =
        uniqueFormulas.stream()
            .map(
                formula ->
                    Hashing.sha256().hashString(formula, StandardCharsets.UTF_8).toString())
            .collect(ImmutableList.toImmutableList());
    return new Decision(
        action, pLoopHeadVisits, uniqueFormulas.size(), multiplicativePredicates, hashes);
  }
}
