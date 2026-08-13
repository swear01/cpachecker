// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

/**
 * Slices a large C source to the line ranges relevant for the LLM: the counterexample path,
 * loop heads and the assertion (issue #74). Only applied when the source exceeds a threshold;
 * small sources pass through untouched.
 */
final class SourceSlicer {

  /** Sources larger than this many characters are sliced before being sent to the LLM. */
  static final int SLICE_THRESHOLD = 100_000;

  private SourceSlicer() {}

  /** Line (1-based) of the first {@code __VERIFIER_assert(...)} or {@code reach_error()} call in the source, or -1. */
  static int assertionLine(String source) {
    int idx = indexOfFirst(source, "__VERIFIER_assert", "reach_error();");
    if (idx < 0) {
      return -1;
    }
    int line = 1;
    for (int i = 0; i < idx; i++) {
      if (source.charAt(i) == '\n') {
        line++;
      }
    }
    return line;
  }

  /** Index of the earliest occurrence of any of the needles, or -1. */
  private static int indexOfFirst(String source, String... needles) {
    int best = -1;
    for (String needle : needles) {
      int idx = source.indexOf(needle);
      if (idx >= 0 && (best < 0 || idx < best)) {
        best = idx;
      }
    }
    return best;
  }

  /**
   * Merges the given 1-based line ranges (each {@code [start, end]}, inclusive) with a context
   * margin and emits the corresponding source lines.
   */
  static String slice(String source, List<int[]> ranges, int margin) {
    String[] lines = source.split("\n", -1);
    List<int[]> merged = mergeRanges(ranges, margin);
    if (merged.isEmpty()) {
      return source;
    }
    StringBuilder sb = new StringBuilder();
    sb.append("// source truncated to counterexample path + loop heads + assertion (")
        .append(merged.size())
        .append(" segments of ")
        .append(lines.length)
        .append(" lines)\n");
    for (int[] r : merged) {
      int start = Math.max(1, r[0]);
      int end = Math.min(lines.length, r[1]);
      sb.append("// [lines ").append(start).append('-').append(end).append("]\n");
      for (int i = start; i <= end; i++) {
        sb.append(lines[i - 1]).append('\n');
      }
    }
    return sb.toString();
  }

  /** Merges overlapping/adjacent ranges and expands each by {@code margin} lines. */
  private static List<int[]> mergeRanges(List<int[]> ranges, int margin) {
    List<int[]> sorted = new ArrayList<>(ranges);
    sorted.sort(Comparator.comparingInt(r -> r[0]));
    List<int[]> merged = new ArrayList<>();
    for (int[] r : sorted) {
      int end = Math.max(r[0], r[1]);
      int start = Math.max(1, r[0] - margin);
      end = end + margin;
      if (merged.isEmpty() || start > merged.get(merged.size() - 1)[1] + 1) {
        merged.add(new int[] {start, end});
      } else {
        merged.get(merged.size() - 1)[1] = Math.max(merged.get(merged.size() - 1)[1], end);
      }
    }
    return merged;
  }
}
