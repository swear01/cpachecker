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
 * loop heads, top-level declarations and the assertion (issue #74). Only applied when the
 * source exceeds a threshold; small sources pass through untouched.
 */
final class SourceSlicer {

  /** Sources larger than this many characters are sliced before being sent to the LLM. */
  static final int SLICE_THRESHOLD = 100_000;

  /** Fallback head size for oversized sources with no usable ranges. */
  static final int HEAD_LIMIT = 50_000;

  private SourceSlicer() {}

  /**
   * Line (1-based) of the first {@code __VERIFIER_assert(...)} or {@code reach_error();} call
   * site in the source, skipping helper declarations/definitions (e.g. {@code extern void
   * __VERIFIER_assert(int);} or {@code void reach_error() {...}} at the top of benchmark files),
   * or -1 if none is found.
   */
  static int assertionLine(String source) {
    String[] lines = source.split("\n", -1);
    for (int i = 0; i < lines.length; i++) {
      String trimmed = lines[i].trim();
      boolean helper =
          trimmed.startsWith("extern")
              || trimmed.startsWith("#define")
              || trimmed.startsWith("void __VERIFIER_assert")
              || trimmed.startsWith("static inline void __VERIFIER_assert")
              || trimmed.startsWith("void reach_error")
              || trimmed.startsWith("static inline void reach_error");
      if (!helper && (lines[i].contains("__VERIFIER_assert(") || lines[i].contains("reach_error();"))) {
        return i + 1;
      }
    }
    return -1;
  }

  /**
   * 1-based line ranges of all top-level lines (brace depth 0): includes, global declarations
   * and function signatures. Keeps declarations that retained slices reference (e.g. constant
   * array shapes). Heuristic: braces inside comments/strings are not tracked.
   */
  static List<int[]> topLevelDeclarationRanges(String source) {
    String stripped = stripComments(source);
    String[] lines = stripped.split("\n", -1);
    List<int[]> ranges = new ArrayList<>();
    int depth = 0;
    for (int i = 0; i < lines.length; i++) {
      String line = lines[i];
      int before = depth;
      depth = Math.max(0, depth + countBraces(line));
      if (before == 0 && !line.isBlank()) {
        ranges.add(new int[] {i + 1, i + 1});
      }
    }
    return ranges;
  }

  /** First {@value #HEAD_LIMIT} characters at a line boundary, with a truncation note. */
  static String head(String source) {
    String[] lines = source.split("\n", -1);
    StringBuilder sb = new StringBuilder();
    sb.append("// source truncated to head (")
        .append(lines.length)
        .append(" lines total)\n");
    for (String line : lines) {
      if (sb.length() + line.length() + 1 > HEAD_LIMIT) {
        break;
      }
      sb.append(line).append('\n');
    }
    return sb.toString();
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
      int start = Math.max(1, r[0] - margin);
      int end = Math.max(r[0], r[1]) + margin;
      if (merged.isEmpty() || start > merged.get(merged.size() - 1)[1] + 1) {
        merged.add(new int[] {start, end});
      } else {
        merged.get(merged.size() - 1)[1] = Math.max(merged.get(merged.size() - 1)[1], end);
      }
    }
    return merged;
  }

  private static int countBraces(String line) {
    int count = 0;
    for (int i = 0; i < line.length(); i++) {
      char c = line.charAt(i);
      if (c == '{') {
        count++;
      } else if (c == '}') {
        count--;
      }
    }
    return count;
  }

  /** Replaces comments with blanks (keeps line structure) so braces in comments are ignored. */
  private static String stripComments(String source) {
    StringBuilder sb = new StringBuilder(source.length());
    boolean inBlock = false;
    int i = 0;
    while (i < source.length()) {
      char c = source.charAt(i);
      if (inBlock) {
        if (c == '*' && i + 1 < source.length() && source.charAt(i + 1) == '/') {
          inBlock = false;
          i++;
        }
        sb.append(c == '\n' ? '\n' : ' ');
        i++;
        continue;
      }
      if (c == '/' && i + 1 < source.length() && source.charAt(i + 1) == '/') {
        while (i < source.length() && source.charAt(i) != '\n') {
          sb.append(' ');
          i++;
        }
        continue;
      }
      if (c == '/' && i + 1 < source.length() && source.charAt(i + 1) == '*') {
        inBlock = true;
        sb.append("  ");
        i += 2;
        continue;
      }
      sb.append(c);
      i++;
    }
    return sb.toString();
  }
}
