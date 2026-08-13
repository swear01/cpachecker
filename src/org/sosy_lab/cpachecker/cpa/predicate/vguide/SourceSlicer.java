// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import com.google.common.base.Splitter;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

/**
 * Slices a large C source to the line ranges relevant for the LLM: the counterexample path,
 * loop heads, top-level declarations and the assertion sites (issue #74). Only applied when the
 * source exceeds a threshold; small sources pass through untouched.
 */
final class SourceSlicer {

  /** Sources larger than this many characters are sliced before being sent to the LLM. */
  static final int SLICE_THRESHOLD = 100_000;

  /** Fallback head size for oversized sources with no usable ranges. */
  static final int HEAD_LIMIT = 50_000;

  private SourceSlicer() {}

  /**
   * 1-based line ranges of all {@code __VERIFIER_assert(...)} and {@code reach_error();} call
   * sites, skipping helper declarations/definitions (e.g. the multi-line SV-COMP helper
   * {@code void __VERIFIER_assert(int cond) { ERROR: {reach_error();abort();} }}) and comments.
   * Each range covers the whole call (from the opening line to the line of the closing paren).
   */
  static List<int[]> assertionRanges(String source) {
    String stripped = stripCommentsAndStrings(source);
    List<String> lines = splitLines(stripped);
    List<int[]> ranges = new ArrayList<>();
    boolean inHelper = false;
    int helperDepth = 0;
    for (int i = 0; i < lines.size(); i++) {
      String trimmed = lines.get(i).trim();
      boolean helperSignature =
          trimmed.startsWith("extern")
              || trimmed.startsWith("#define")
              || trimmed.startsWith("void __VERIFIER_assert")
              || trimmed.startsWith("static inline void __VERIFIER_assert")
              || trimmed.startsWith("void reach_error")
              || trimmed.startsWith("static inline void reach_error");
      if (inHelper) {
        helperDepth += countBraces(lines.get(i));
        if (helperDepth <= 0) {
          inHelper = false;
        }
        continue;
      }
      if (helperSignature) {
        inHelper = true;
        helperDepth = countBraces(lines.get(i));
        continue;
      }
      int assertIdx = lines.get(i).indexOf("__VERIFIER_assert(");
      int reachIdx = lines.get(i).indexOf("reach_error();");
      int idx = assertIdx >= 0 && (reachIdx < 0 || assertIdx < reachIdx) ? assertIdx : reachIdx;
      if (idx < 0) {
        continue;
      }
      int endLine = closingParenLine(lines, i, idx);
      ranges.add(new int[] {i + 1, endLine + 1});
    }
    return ranges;
  }

  /**
   * 1-based line ranges of all top-level lines (brace depth 0): includes, global declarations
   * and function signatures. Keeps declarations that retained slices reference (e.g. constant
   * array shapes). Preprocessor lines and string literals do not change the depth.
   */
  static List<int[]> topLevelDeclarationRanges(String source) {
    String stripped = stripCommentsAndStrings(source);
    List<String> lines = splitLines(stripped);
    List<int[]> ranges = new ArrayList<>();
    int depth = 0;
    for (int i = 0; i < lines.size(); i++) {
      String line = lines.get(i);
      int before = depth;
      // preprocessor lines and macro continuations are self-contained: they neither open a
      // block nor depend on one
      if (!line.stripLeading().startsWith("#") && !line.endsWith("\\")) {
        depth = Math.max(0, depth + countBraces(line));
      }
      if (before == 0 && !line.isBlank()) {
        ranges.add(new int[] {i + 1, i + 1});
      }
    }
    return ranges;
  }

  /** First {@value #HEAD_LIMIT} characters at a line boundary, with a truncation note. */
  static String head(String source) {
    List<String> lines = splitLines(source);
    StringBuilder sb = new StringBuilder();
    sb.append("// source truncated to head (")
        .append(lines.size())
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
    List<String> lines = splitLines(source);
    List<int[]> merged = mergeRanges(ranges, margin);
    if (merged.isEmpty()) {
      return source;
    }
    StringBuilder sb = new StringBuilder();
    sb.append("// source truncated to counterexample path + loop heads + assertion (")
        .append(merged.size())
        .append(" segments of ")
        .append(lines.size())
        .append(" lines)\n");
    for (int[] r : merged) {
      int start = Math.max(1, r[0]);
      int end = Math.min(lines.size(), r[1]);
      sb.append("// [lines ").append(start).append('-').append(end).append("]\n");
      for (int i = start; i <= end; i++) {
        sb.append(lines.get(i - 1)).append('\n');
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

  /** Line index of the paren matching the '(' at {@code openIdx} in line {@code lineIdx}. */

  /** Splits into lines, dropping the phantom empty element after a trailing newline. */
  private static List<String> splitLines(String source) {
    List<String> lines = Splitter.on('\n').splitToList(source);
    if (!lines.isEmpty() && lines.get(lines.size() - 1).isEmpty()) {
      return lines.subList(0, lines.size() - 1);
    }
    return lines;
  }

  private static int closingParenLine(List<String> lines, int lineIdx, int openIdx) {
    int depth = 0;
    for (int i = lineIdx; i < lines.size(); i++) {
      String line = lines.get(i);
      for (int j = (i == lineIdx ? openIdx : 0); j < line.length(); j++) {
        char c = line.charAt(j);
        if (c == '(') {
          depth++;
        } else if (c == ')' && --depth == 0) {
          return i;
        }
      }
    }
    return lineIdx;
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

  /**
   * Replaces comments and string/char literals with blanks (keeps line structure) so braces
   * inside them are ignored.
   */
  private static String stripCommentsAndStrings(String source) {
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
      if (c == '"' || c == '\'') {
        char quote = c;
        sb.append(c);
        i++;
        while (i < source.length() && source.charAt(i) != quote) {
          if (source.charAt(i) == '\\' && i + 1 < source.length()) {
            sb.append("  ");
            i += 2;
            continue;
          }
          sb.append(source.charAt(i) == '\n' ? '\n' : ' ');
          i++;
        }
        if (i < source.length()) {
          sb.append(quote);
          i++;
        }
        continue;
      }
      sb.append(c);
      i++;
    }
    return sb.toString();
  }
}
