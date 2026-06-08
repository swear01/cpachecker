// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import com.google.common.collect.ImmutableList;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

/** Merges multiple LLM raw responses into one predicate candidate list. */
public final class LlmEnsembleMerger {

  private LlmEnsembleMerger() {}

  /**
   * Union of parsed predicates from each draw (dedupe by exact string), then sanitizer/validator
   * run downstream on the combined list.
   */
  public static ImmutableList<String> unionValidate(List<String> rawResponses) {
    return unionValidate(rawResponses, new PredicateBudget(1, Integer.MAX_VALUE));
  }

  public static ImmutableList<String> unionValidate(
      List<String> rawResponses, PredicateBudget budget) {
    Set<String> seen = new LinkedHashSet<>();
    List<String> merged = new ArrayList<>();
    for (String raw : rawResponses) {
      for (String p : LlmResponseParser.parsePredicates(raw)) {
        if (seen.add(p)) {
          merged.add(p);
        }
      }
    }
    return budget.capOrdered(merged);
  }
}
