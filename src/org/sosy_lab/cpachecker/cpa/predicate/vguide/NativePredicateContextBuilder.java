// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import com.google.common.collect.ImmutableList;
import com.google.common.collect.Multimap;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/**
 * Deterministic, bounded rendering of the current native CEGAR predicate precision for the LLM
 * (Issue #6).
 *
 * <p>Predicates are canonicalized to SMT strings and tagged with scope and origin. Origin is
 * {@code native} unless the (scope, canonical formula) key was recorded as LLM-injected by the
 * bridge — LLM-owned predicates are never disguised as native CEGAR predicates. Only relevant
 * predicates are exposed: globals, function-scoped predicates of functions that own a loop head,
 * and local predicates at loop-head nodes. Output is deduplicated, sorted, and capped
 * deterministically; dropped entries are counted, never silently discarded.
 */
public final class NativePredicateContextBuilder {

  public static final int MAX_PREDICATES = 40;
  public static final int MAX_CHARS = 3000;

  /** One exposed predicate: scope (global / function F / local N12), origin, canonical SMT. */
  public record Entry(String scope, String origin, String smt) {}

  public record Context(ImmutableList<Entry> entries, int omitted, String selectionRule) {}

  private final Set<String> llmOwnedKeys;

  public NativePredicateContextBuilder(Set<String> llmOwnedKeys) {
    this.llmOwnedKeys = llmOwnedKeys;
  }

  public Context build(
      List<String> globalPredicates,
      Multimap<String, String> functionPredicates,
      Multimap<String, String> localPredicates,
      ImmutableList<LoopHeadInfo> loopHeads) {
    Set<String> loopHeadLabels = new HashSet<>();
    Set<String> owningFunctions = new HashSet<>();
    for (LoopHeadInfo head : loopHeads) {
      loopHeadLabels.add(head.label());
      owningFunctions.add(head.functionName());
    }
    List<Entry> candidates = new ArrayList<>();
    Set<String> seen = new HashSet<>();
    for (String smt : globalPredicates) {
      add(candidates, seen, "global", smt);
    }
    for (String function : functionPredicates.keySet()) {
      if (!owningFunctions.contains(function)) {
        continue;
      }
      for (String smt : functionPredicates.get(function)) {
        add(candidates, seen, "function " + function, smt);
      }
    }
    for (String label : localPredicates.keySet()) {
      if (!loopHeadLabels.contains(label)) {
        continue;
      }
      for (String smt : localPredicates.get(label)) {
        add(candidates, seen, "local " + label, smt);
      }
    }
    candidates.sort(Comparator.comparing(Entry::scope).thenComparing(Entry::smt));

    int omitted = 0;
    List<Entry> kept = new ArrayList<>();
    int chars = 0;
    for (Entry e : candidates) {
      int lineChars = formatLine(e).length();
      if (kept.size() >= MAX_PREDICATES || chars + lineChars > MAX_CHARS) {
        omitted++;
        continue;
      }
      kept.add(e);
      chars += lineChars;
    }
    return new Context(
        ImmutableList.copyOf(kept), omitted, selectionRule());
  }

  /** Prompt block text; empty when nothing is exposed. */
  public static String format(Context context) {
    StringBuilder out = new StringBuilder();
    for (Entry e : context.entries()) {
      out.append(formatLine(e)).append('\n');
    }
    return out.toString();
  }

  private void add(List<Entry> candidates, Set<String> seen, String scope, String smt) {
    String key = scope + "|" + smt;
    if (!seen.add(key)) {
      return;
    }
    String origin = llmOwnedKeys.contains(key) ? "llm" : "native";
    candidates.add(new Entry(scope, origin, smt));
  }

  private static String formatLine(Entry e) {
    return "[" + e.scope() + " | " + e.origin() + "] " + e.smt();
  }

  private static String selectionRule() {
    return "global + loop-head-owning functions + loop-head locals; canonical dedup; sorted; cap "
        + MAX_PREDICATES
        + " predicates / "
        + MAX_CHARS
        + " chars";
  }
}
