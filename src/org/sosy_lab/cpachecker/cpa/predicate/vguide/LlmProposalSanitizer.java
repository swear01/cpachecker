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

/** Drops L1-invalid or duplicate predicate strings after JSON parse. */
public final class LlmProposalSanitizer {

  private static final int MAX_PREDICATES = 12;

  private LlmProposalSanitizer() {}

  public static ImmutableList<String> sanitize(List<String> raw) {
    Set<String> seen = new LinkedHashSet<>();
    List<String> out = new ArrayList<>();
    for (String p : raw) {
      if (p == null) {
        continue;
      }
      String stripped = p.strip();
      if (stripped.isEmpty() || !PredicateContractValidator.isValid(stripped)) {
        continue;
      }
      if (seen.add(stripped)) {
        out.add(stripped);
      }
      if (out.size() >= MAX_PREDICATES) {
        break;
      }
    }
    return ImmutableList.copyOf(out);
  }
}
