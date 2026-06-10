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

  public static ImmutableList<AttributedRawPredicate> attributeAll(
      List<String> rawPredicates, PromptProfile profile) {
    List<AttributedRawPredicate> out = new ArrayList<>();
    for (String raw : rawPredicates) {
      out.add(new AttributedRawPredicate(raw, profile));
    }
    return ImmutableList.copyOf(out);
  }

  /** Union SAFE then BUG predicates without {@link PredicateBudget#capOrdered}. */
  public static ImmutableList<AttributedRawPredicate> mergeDualUnion(
      ImmutableList<AttributedRawPredicate> safe,
      ImmutableList<AttributedRawPredicate> bug) {
    Set<String> seen = new LinkedHashSet<>();
    List<AttributedRawPredicate> merged = new ArrayList<>();
    for (AttributedRawPredicate p : safe) {
      if (seen.add(p.raw())) {
        merged.add(p);
      }
    }
    for (AttributedRawPredicate p : bug) {
      if (seen.add(p.raw())) {
        merged.add(p);
      }
    }
    return ImmutableList.copyOf(merged);
  }
}
