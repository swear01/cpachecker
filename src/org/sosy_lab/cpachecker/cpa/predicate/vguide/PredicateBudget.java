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

/** Min/max predicate count per LLM response (prompt guidance + post-parse cap). */
public record PredicateBudget(int minPerCall, int maxPerCall) {

  public PredicateBudget {
    if (minPerCall < 1) {
      throw new IllegalArgumentException("minPerCall must be >= 1");
    }
    if (maxPerCall < minPerCall) {
      throw new IllegalArgumentException("maxPerCall must be >= minPerCall");
    }
  }

  /** Preserve order; dedupe; truncate to {@link #maxPerCall()}. */
  public ImmutableList<String> capOrdered(List<String> predicates) {
    Set<String> seen = new LinkedHashSet<>();
    List<String> out = new ArrayList<>();
    for (String p : predicates) {
      if (p == null || p.isBlank()) {
        continue;
      }
      if (seen.add(p.strip())) {
        out.add(p.strip());
        if (out.size() >= maxPerCall) {
          break;
        }
      }
    }
    return ImmutableList.copyOf(out);
  }
}
