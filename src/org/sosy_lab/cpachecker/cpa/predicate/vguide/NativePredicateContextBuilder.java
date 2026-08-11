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
  public record Entry(String scope, String origin, String smt, boolean subsumed) {}

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
        // Entries are sorted; once the cap is hit, stop to keep a contiguous prefix.
        omitted += candidates.size() - kept.size();
        break;
      }
      kept.add(e);
      chars += lineChars;
    }
    markSubsumed(kept);
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
    candidates.add(new Entry(scope, origin, smt, false));
  }

  private static String formatLine(Entry e) {
    return "[" + e.scope() + " | " + e.origin() + "] " + e.smt();
  }

  /**
   * Syntactic subsumption heuristic (metadata only, never a correctness proof): a predicate is
   * marked subsumed when another predicate at the same scope implies it. Supported shapes:
   * same-direction constant bounds with the same variable (bvsge/bvsle/bvslt/bvsgt) and
   * conjunction-atom containment. Subsumed predicates are kept in the context and dump.
   */
  private static void markSubsumed(List<Entry> candidates) {
    for (int i = 0; i < candidates.size(); i++) {
      Entry a = candidates.get(i);
      for (int j = 0; j < candidates.size(); j++) {
        if (i == j || !a.scope().equals(candidates.get(j).scope())) {
          continue;
        }
        if (subsumes(a.smt(), candidates.get(j).smt())) {
          candidates.set(
              j, new Entry(candidates.get(j).scope(), candidates.get(j).origin(), candidates.get(j).smt(), true));
        }
      }
    }
  }

  private static boolean subsumes(String subsumer, String subsumee) {
    Bound b1 = parseBound(subsumer);
    Bound b2 = parseBound(subsumee);
    if (b1 != null
        && b2 != null
        && b1.variable.equals(b2.variable)
        && b1.op.equals(b2.op)
        && b1.bitwidth == b2.bitwidth
        && b1.bitwidth <= 64) {
      return switch (b1.op) {
        case "bvsge", "bvsgt" -> Long.compare(b1.signedValue(), b2.signedValue()) >= 0;
        case "bvsle", "bvslt" -> Long.compare(b1.signedValue(), b2.signedValue()) <= 0;
        default -> false;
      };
    }
    if (subsumer.startsWith("(and ")) {
      return splitConjuncts(subsumer).contains(subsumee);
    }
    return false;
  }

  private record Bound(String variable, String op, long unsignedValue, int bitwidth) {
    /** Sign-extend the unsigned bitvector literal to a signed long. */
    long signedValue() {
      if (bitwidth >= 64) {
        return unsignedValue;
      }
      long sign = 1L << (bitwidth - 1);
      return (unsignedValue & (sign - 1)) - (unsignedValue & sign);
    }
  }

  private static @org.checkerframework.checker.nullness.qual.Nullable Bound parseBound(String smt) {
    var m = BOUND_PATTERN.matcher(smt);
    if (!m.matches()) {
      return null;
    }
    try {
      return new Bound(
          m.group(2),
          m.group(1),
          Long.parseUnsignedLong(m.group(3)),
          Integer.parseInt(m.group(4)));
    } catch (NumberFormatException e) {
      return null;
    }
  }

  /**
   * Top-level conjuncts of an {@code (and ...)} formula, split on whitespace at depth 0 so
   * unparenthesized conjuncts are kept and negated/nested atoms are not matched by substring.
   */
  private static List<String> splitConjuncts(String andFormula) {
    List<String> conjuncts = new ArrayList<>();
    if (!andFormula.startsWith("(and ") || !andFormula.endsWith(")") || andFormula.length() <= 6) {
      return conjuncts;
    }
    String inner = andFormula.substring("(and ".length(), andFormula.length() - 1);
    int depth = 0;
    StringBuilder current = new StringBuilder();
    for (int i = 0; i < inner.length(); i++) {
      char c = inner.charAt(i);
      if (c == '(') {
        depth++;
        current.append(c);
      } else if (c == ')') {
        depth--;
        current.append(c);
      } else if (Character.isWhitespace(c) && depth == 0) {
        if (current.length() > 0) {
          conjuncts.add(current.toString().strip());
          current.setLength(0);
        }
      } else {
        current.append(c);
      }
    }
    if (current.length() > 0) {
      conjuncts.add(current.toString().strip());
    }
    return conjuncts;
  }

  private static final java.util.regex.Pattern BOUND_PATTERN =
      java.util.regex.Pattern.compile(
          "^\\((bvsge|bvsgt|bvsle|bvslt) (\\S+) \\(_ bv(\\d+) (\\d+)\\)\\)$");

  private static String selectionRule() {
    return "global + loop-head-owning functions + loop-head locals; canonical dedup; sorted; cap "
        + MAX_PREDICATES
        + " predicates / "
        + MAX_CHARS
        + " chars";
  }
}
