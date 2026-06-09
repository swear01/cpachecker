// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import com.google.common.base.Splitter;
import com.google.common.collect.ImmutableList;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Scans C source for variables safe to mention in LLM predicate proposals. */
public final class SourceVariableHints {

  private static final Pattern SCALAR_DECL =
      Pattern.compile("\\bint\\s+([A-Za-z_]\\w*)\\s*;");
  private static final Pattern ARRAY_DECL =
      Pattern.compile("\\bint\\s+([A-Za-z_]\\w*)\\s*\\[");

  private SourceVariableHints() {}

  public static ImmutableList<String> scalarNames(String source) {
    Set<String> scalars = new LinkedHashSet<>();
    Set<String> arrays = new LinkedHashSet<>();
    Matcher scalar = SCALAR_DECL.matcher(source);
    while (scalar.find()) {
      scalars.add(scalar.group(1));
    }
    Matcher array = ARRAY_DECL.matcher(source);
    while (array.find()) {
      arrays.add(array.group(1));
    }
    scalars.removeAll(arrays);
    return ImmutableList.copyOf(scalars);
  }

  public static boolean hasArrayDecl(String source) {
    return ARRAY_DECL.matcher(source).find();
  }

  /** Count scalar int declarations (supports comma-separated names per line). */
  public static int scalarDeclCount(String source) {
    int count = 0;
    Matcher line = Pattern.compile("\\bint\\s+([^;]+);").matcher(source);
    while (line.find()) {
      String decl = line.group(1).trim();
      if (decl.contains("[")) {
        continue;
      }
      count += Splitter.on(',').trimResults().omitEmptyStrings().splitToList(decl).size();
    }
    return count;
  }

  public static String formatForPrompt(String source, java.util.Map<String, ?> contract) {
    ImmutableList<String> scalars = scalarNames(source);
    if (scalars.isEmpty() && contract.isEmpty()) {
      return "";
    }
    StringBuilder sb = new StringBuilder();
    if (!scalars.isEmpty()) {
      sb.append("Allowed scalar variables (use ONLY these names): ")
          .append(scalars)
          .append('\n');
    }
    if (hasArrayDecl(source)) {
      sb.append(
          """
          Array program: do NOT use array identifiers (e.g. A) or C subscripts (A[i]) in predicates.
          Use only index/counter scalars (e.g. i) with bounds and loop-guard relations.
          BAD (rejected): (= A[i] 0), (select A i), |main::A@1|
          GOOD: (bvsge i (_ bv0 32)), (bvsle i (_ bv1024 32))
          """);
    }
    if (!contract.isEmpty()) {
      sb.append("Contract keys must match allowed scalars above.\n");
    }
    return sb.toString();
  }
}
