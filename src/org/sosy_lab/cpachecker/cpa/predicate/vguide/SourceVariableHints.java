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
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Scans C source for variables safe to mention in LLM predicate proposals. */
public final class SourceVariableHints {

  private static final Pattern INT_DECL = Pattern.compile("\\bint\\s+([^;]+);");
  private static final Pattern DECLARATOR_NAME =
      Pattern.compile("\\s*\\*?\\s*([A-Za-z_]\\w*)\\s*(?:=.*)?");
  private static final Pattern ARRAY_DECL =
      Pattern.compile("\\bint\\s+([A-Za-z_]\\w*)\\s*\\[");

  private SourceVariableHints() {}

  public static ImmutableList<String> scalarNames(String source) {
    Set<String> scalars = new LinkedHashSet<>();
    Matcher declaration = INT_DECL.matcher(source);
    while (declaration.find()) {
      for (String declarator : splitDeclarators(declaration.group(1))) {
        if (declarator.contains("[")) {
          continue;
        }
        Matcher name = DECLARATOR_NAME.matcher(declarator);
        if (name.matches()) {
          scalars.add(name.group(1));
        }
      }
    }
    return ImmutableList.copyOf(scalars);
  }

  public static boolean hasArrayDecl(String source) {
    return ARRAY_DECL.matcher(source).find();
  }

  /** Count scalar int declarations (supports comma-separated names per line). */
  public static int scalarDeclCount(String source) {
    int count = 0;
    Matcher declaration = INT_DECL.matcher(source);
    while (declaration.find()) {
      for (String declarator : splitDeclarators(declaration.group(1))) {
        if (declarator.contains("[")) {
          continue;
        }
        Matcher name = DECLARATOR_NAME.matcher(declarator);
        if (name.matches()) {
          count++;
        }
      }
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
          Array program: array element reads are allowed only in source-level C syntax A[i].
          Do not use bare array identifiers, select/store, heap names, or SSA names.
          GOOD: (= A[i] 0), (bvsge i (_ bv0 32)), (bvsle i (_ bv1024 32))
          """);
    }
    if (!contract.isEmpty()) {
      sb.append("Contract keys must match allowed scalars above.\n");
    }
    return sb.toString();
  }

  private static List<String> splitDeclarators(String declaration) {
    List<String> parts = new ArrayList<>();
    int parenDepth = 0;
    int bracketDepth = 0;
    int braceDepth = 0;
    int start = 0;
    for (int i = 0; i < declaration.length(); i++) {
      char c = declaration.charAt(i);
      switch (c) {
        case '(' -> parenDepth++;
        case ')' -> parenDepth = Math.max(0, parenDepth - 1);
        case '[' -> bracketDepth++;
        case ']' -> bracketDepth = Math.max(0, bracketDepth - 1);
        case '{' -> braceDepth++;
        case '}' -> braceDepth = Math.max(0, braceDepth - 1);
        case ',' -> {
          if (parenDepth == 0 && bracketDepth == 0 && braceDepth == 0) {
            parts.add(declaration.substring(start, i).strip());
            start = i + 1;
          }
        }
        default -> {}
      }
    }
    parts.add(declaration.substring(start).strip());
    return parts;
  }
}
