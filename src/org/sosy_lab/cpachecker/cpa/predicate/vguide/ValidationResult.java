// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import com.google.common.collect.ImmutableList;

/** Outcome of validating LLM predicate proposals. */
public record ValidationResult(ImmutableList<ValidatedPredicate> validated) {

  public ImmutableList<ValidatedPredicate> entailed() {
    return validated.stream()
        .filter(v -> v.classification() == ValidatedPredicate.Classification.ENTAILED)
        .collect(ImmutableList.toImmutableList());
  }

  public ImmutableList<ValidatedPredicate> precisionOnly() {
    return validated.stream()
        .filter(v -> v.classification() == ValidatedPredicate.Classification.PRECISION_ONLY)
        .collect(ImmutableList.toImmutableList());
  }
}
