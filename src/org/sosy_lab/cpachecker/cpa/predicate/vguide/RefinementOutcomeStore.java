// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import com.google.common.collect.ImmutableList;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Bounded per-analysis store of CEGAR refinement outcomes (Issue #7).
 *
 * <p>Each spurious round starts an entry with the authoritative pre-refinement facts (round index,
 * loop-head visits [heuristic], interpolant count, block count); the LLM candidate outcome is
 * appended when the LLM fired; after refinement the entry finishes with the native precision delta
 * (new predicates added by the refiner). Completed entries render as compact, deterministic prompt
 * lines; the store keeps the most recent {@link #MAX_ENTRIES} rounds (oldest-first eviction,
 * omitted count observable). Facts that CPAchecker cannot provide are never inferred — the schema
 * marks them unavailable.
 */
public final class RefinementOutcomeStore {

  public static final int MAX_ENTRIES = 4;
  public static final String UNAVAILABLE =
      "refiner_status,infeasible_prefix,infeasible_suffix,infeasible_pivot,arg_prune";

  private final Map<Integer, StringBuilder> pending = new HashMap<>();
  private final List<String> completed = new ArrayList<>();
  private int omitted;

  public void recordStarted(
      int refinementIndex, int loopHeadVisits, int interpolantCount, int blockCount) {
    // Rounds are sequential; any still-pending older round will never complete
    // (aborted/failed refinement) — drop it to bound the map.
    pending.keySet().removeIf(round -> round < refinementIndex);
    StringBuilder sb = new StringBuilder("round ")
        .append(refinementIndex)
        .append(": visits=")
        .append(loopHeadVisits)
        .append(" [heuristic] itp=")
        .append(interpolantCount)
        .append(" blocks=")
        .append(blockCount);
    pending.put(refinementIndex, sb);
  }

  /** Appends the LLM candidate outcome of this round (only when the LLM fired). */
  public void recordLlmOutcome(
      int refinementIndex, int validatedCount, int injectedCount, int rejectionCount) {
    StringBuilder sb = pending.get(refinementIndex);
    if (sb == null) {
      return;
    }
    sb.append(" llm=fired validated=")
        .append(validatedCount)
        .append(" injected=")
        .append(injectedCount)
        .append(" rejected=")
        .append(rejectionCount);
  }

  /** Finishes the round with the native precision delta computed before LLM injection. */
  public void recordCompleted(int refinementIndex, int newNativePredicates) {
    StringBuilder sb = pending.remove(refinementIndex);
    if (sb == null) {
      return;
    }
    sb.append(" native_delta=+").append(newNativePredicates);
    completed.add(sb.toString());
    while (completed.size() > MAX_ENTRIES) {
      completed.remove(0);
      omitted++;
    }
  }

  public @org.checkerframework.checker.nullness.qual.Nullable String completedLineFor(
      int refinementIndex) {
    String prefix = "round " + refinementIndex + ":";
    for (int i = completed.size() - 1; i >= 0; i--) {
      if (completed.get(i).startsWith(prefix)) {
        return completed.get(i);
      }
    }
    return null;
  }

  public Snapshot snapshot() {
    return new Snapshot(ImmutableList.copyOf(completed), omitted);
  }

  public record Snapshot(ImmutableList<String> entries, int omitted) {}

  /** Prompt block text; empty when nothing completed yet. */
  public String buildContext() {
    if (completed.isEmpty()) {
      return "";
    }
    StringBuilder out = new StringBuilder();
    for (String line : completed) {
      out.append(line).append('\n');
    }
    if (omitted > 0) {
      out.append("(older rounds omitted: ").append(omitted).append(")\n");
    }
    out.append("unavailable: ").append(UNAVAILABLE).append('\n');
    return out.toString();
  }
}
