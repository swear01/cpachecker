// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import com.google.common.collect.ImmutableMap;
import com.google.common.collect.ImmutableSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

/** Maps C source variable names to encoded SSA names appearing in block formulas. */
public final class VarContractBuilder {

  private static final Pattern SOURCE_NAME = Pattern.compile("[A-Za-z_]\\w*");

  private VarContractBuilder() {}

  public static ImmutableMap<String, ImmutableSet<String>> build(Set<String> encodedVariableNames) {
    Map<String, Set<String>> contract = new LinkedHashMap<>();
    for (String encoded : encodedVariableNames) {
      String sourceName = sourceNameFromEncoded(encoded);
      if (sourceName.isEmpty()) {
        continue;
      }
      contract.computeIfAbsent(sourceName, k -> new LinkedHashSet<>()).add(encoded);
    }
    ImmutableMap.Builder<String, ImmutableSet<String>> result = ImmutableMap.builder();
    for (var e : contract.entrySet()) {
      result.put(e.getKey(), ImmutableSet.copyOf(e.getValue()));
    }
    return result.build();
  }

  private static String sourceNameFromEncoded(String encoded) {
    String name = encoded.strip();
    if (name.startsWith("|") && name.endsWith("|") && name.length() > 1) {
      name = name.substring(1, name.length() - 1);
    } else if (!name.contains("::") && !name.contains("@")) {
      return "";
    }
    int scope = name.lastIndexOf("::");
    if (scope >= 0) {
      name = name.substring(scope + 2);
    }
    int at = name.indexOf('@');
    if (at >= 0) {
      name = name.substring(0, at);
    }
    name = name.strip();
    return SOURCE_NAME.matcher(name).matches() ? name : "";
  }

  public static String formatForPrompt(Map<String, ImmutableSet<String>> contract) {
    if (contract.isEmpty()) {
      return "(no encoded variables in counterexample)\n";
    }
    StringBuilder sb = new StringBuilder("Variable contract (use LEFT names in predicates):\n");
    for (var e : contract.entrySet()) {
      sb.append("  ").append(e.getKey()).append(" -> ").append(e.getValue()).append('\n');
    }
    return sb.toString();
  }
}
