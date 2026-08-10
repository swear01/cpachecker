// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import com.google.common.collect.ImmutableList;

/**
 * One LLM proposal bound to explicit loop-head labels.
 *
 * <p>There is no implicit broadcast: the candidate is validated and injected only at the named
 * loop heads. {@code role} and {@code variables} are metadata for later grouped validation and
 * dump attribution, not correctness inputs.
 */
public record LoopHeadCandidate(
    ImmutableList<String> loopHeads, String predicate, String role, ImmutableList<String> variables) {

  public LoopHeadCandidate {
    loopHeads = loopHeads == null ? ImmutableList.of() : loopHeads;
    predicate = predicate == null ? "" : predicate;
    role = role == null ? "" : role;
    variables = variables == null ? ImmutableList.of() : variables;
  }

  /** Dedup key that keeps the same predicate at different loop heads distinct. */
  public String dedupKey() {
    return String.join(",", loopHeads) + "#" + predicate;
  }
}
