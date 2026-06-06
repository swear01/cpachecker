// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import java.util.regex.Pattern;

/** L1 contract validation (ported from archive b5_validate_candidates.py). */
public final class PredicateContractValidator {

  private static final Pattern[] FORBIDDEN = {
    Pattern.compile("\\|[a-z_]\\w+::"),
    Pattern.compile("\\.def_\\d+"),
    Pattern.compile("(?<!\\|)\\b\\w+@\\d+\\b"),
    Pattern.compile("\\b[A-Za-z_]\\w*\\s*\\["), // C array subscript A[i], not SMT symbols
    Pattern.compile("\\bselect\\b"),
    Pattern.compile("\\bstore\\b"),
    Pattern.compile("\\bbvshl\\b"),
    Pattern.compile("\\bbvlshr\\b"),
    Pattern.compile("\\bbvashr\\b"),
  };

  private PredicateContractValidator() {}

  public static boolean isValid(String predicateText) {
    String stripped = predicateText.strip();
    if (stripped.isEmpty() || !stripped.startsWith("(")) {
      return false;
    }
    for (Pattern p : FORBIDDEN) {
      if (p.matcher(stripped).find()) {
        return false;
      }
    }
    return true;
  }
}
