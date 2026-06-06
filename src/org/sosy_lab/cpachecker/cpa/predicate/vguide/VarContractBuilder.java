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
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Maps C source variable names to encoded SSA names appearing in block formulas. */
public final class VarContractBuilder {

  private static final Pattern ENCODED_VAR = Pattern.compile("\\|([^|]+)\\|");

  private VarContractBuilder() {}

  public static ImmutableMap<String, ImmutableSet<String>> build(Set<String> encodedVariableNames) {
    Map<String, Set<String>> contract = new LinkedHashMap<>();
    for (String encoded : encodedVariableNames) {
      Matcher m = ENCODED_VAR.matcher(encoded);
      if (!m.find()) {
        continue;
      }
      String inner = m.group(1);
      String sourceName = sourceNameFromEncoded(inner);
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

  private static String sourceNameFromEncoded(String inner) {
    String name = inner;
    int scope = name.lastIndexOf("::");
    if (scope >= 0) {
      name = name.substring(scope + 2);
    }
    int at = name.indexOf('@');
    if (at >= 0) {
      name = name.substring(0, at);
    }
    return name.strip();
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
