// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.google.common.base.CharMatcher;
import com.google.common.base.Splitter;
import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableMap;
import com.google.common.hash.Hashing;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Per-analysis bounded store of structured counterexample history (Issue #5).
 *
 * <p>Each LLM round records the structured CE artifact (`structured-ce-v1` JSON). Consecutive
 * identical CEs are deduplicated into a repeat count. The store keeps the most recent {@link
 * #MAX_ENTRIES} entries (deterministic oldest-first eviction) and renders a bounded, deterministic
 * prompt block: compact per-round summaries plus, in {@code BOUNDED_WITH_DELTA} mode, an explicit
 * delta between the previous round and the current CE (loop-head visit changes, new/removed heads,
 * relations changes).
 *
 * <p>The store is a field of the refinement bridge, so it never outlives one analysis and never
 * leaks history across tasks or runs.
 */
public final class CeHistoryStore {

  public static final int MAX_ENTRIES = 4;
  public static final int MAX_CONTEXT_CHARS = 4000;

  private static final ObjectMapper JSON = new ObjectMapper();

  /** One stored round. {@code repeatCount} counts consecutive identical CEs. */
  public record Entry(int refinementIndex, String fingerprint, String compact, int repeatCount) {}

  /** Observable history state for the analysis dump. */
  public record Snapshot(ImmutableList<Entry> entries, int omitted) {}

  private final List<Entry> entries = new ArrayList<>();
  private int omitted;

  public void record(int refinementIndex, String structuredCeJson) {
    if (structuredCeJson == null || structuredCeJson.isBlank()) {
      return;
    }
    String fingerprint = fingerprint(structuredCeJson);
    String compact = compact(structuredCeJson);
    if (!entries.isEmpty()) {
      Entry last = entries.get(entries.size() - 1);
      if (last.fingerprint().equals(fingerprint)) {
        entries.set(
            entries.size() - 1,
            new Entry(last.refinementIndex(), last.fingerprint(), last.compact(), last.repeatCount() + 1));
        return;
      }
    }
    entries.add(new Entry(refinementIndex, fingerprint, compact, 1));
    while (entries.size() > MAX_ENTRIES) {
      entries.remove(0);
      omitted++;
    }
  }

  public Snapshot snapshot() {
    return new Snapshot(ImmutableList.copyOf(entries), omitted);
  }

  /**
   * Renders the bounded history prompt block for the current CE. Must be called before recording
   * the current round so the current CE is never part of its own history.
   */
  public String buildContext(VGuideOptions.CeHistoryMode mode, String currentCeJson) {
    if (mode == VGuideOptions.CeHistoryMode.OFF || entries.isEmpty()) {
      return "";
    }
    List<Entry> shown = new ArrayList<>(entries);
    if (mode == VGuideOptions.CeHistoryMode.LATEST && !shown.isEmpty()) {
      shown = ImmutableList.of(shown.get(shown.size() - 1));
    }
    StringBuilder out = new StringBuilder();
    for (Entry e : shown) {
      out.append("[refinement ")
          .append(e.refinementIndex())
          .append(", fingerprint ")
          .append(e.fingerprint().substring(0, Math.min(8, e.fingerprint().length())))
          .append(e.repeatCount() > 1 ? ", seen " + e.repeatCount() + "x" : "")
          .append("] ")
          .append(e.compact())
          .append('\n');
    }
    if (mode == VGuideOptions.CeHistoryMode.BOUNDED_WITH_DELTA) {
      out.append("Delta vs previous round:\n")
          .append(delta(entries.get(entries.size() - 1), currentCeJson));
    }
    if (out.length() > MAX_CONTEXT_CHARS) {
      int lastNewline = out.lastIndexOf("\n", MAX_CONTEXT_CHARS);
      if (lastNewline > 0) {
        out.setLength(lastNewline + 1);
      } else {
        out.setLength(MAX_CONTEXT_CHARS);
      }
    }
    return out.toString();
  }

  /** Deterministic textual delta between one stored entry and the current CE. */
  static String delta(Entry previous, String currentCeJson) {
    Map<String, Integer> prevVisits = visitsByHead(previous.compact());
    Map<String, Integer> curVisits =
        currentCeJson == null || currentCeJson.isBlank()
            ? ImmutableMap.of()
            : visitsByHead(compact(currentCeJson));
    if (prevVisits.equals(curVisits)) {
      return "(no change vs previous round)\n";
    }
    StringBuilder out = new StringBuilder();
    TreeMap<String, Integer> all = new TreeMap<>();
    all.putAll(prevVisits);
    all.putAll(curVisits);
    for (Map.Entry<String, Integer> e : all.entrySet()) {
      String label = e.getKey();
      Integer before = prevVisits.get(label);
      Integer after = curVisits.get(label);
      if (before == null) {
        out.append("  new loop head ").append(label).append(" x").append(after).append('\n');
      } else if (after == null) {
        out.append("  head gone ").append(label).append('\n');
      } else if (!before.equals(after)) {
        out.append("  ").append(label).append(" visits ").append(before).append(" -> ").append(after).append('\n');
      }
    }
    return out.toString();
  }

  static String fingerprint(String structuredCeJson) {
    return Hashing.sha256()
        .hashString(structuredCeJson, StandardCharsets.UTF_8)
        .toString();
  }

  /** Compact deterministic per-round summary: sorted loop-head visits + truncated relations. */
  static String compact(String structuredCeJson) {
    Map<String, Integer> visits = new TreeMap<>();
    String relations = "";
    try {
      JsonNode root = JSON.readTree(structuredCeJson);
      JsonNode trace = root.path("trace");
      if (trace.isArray()) {
        for (JsonNode segment : trace) {
          JsonNode head = segment.path("loop_head");
          if (head.isTextual() && !head.asText().isBlank()) {
            visits.merge(head.asText(), segment.path("repeat_count").asInt(1), Integer::sum);
          }
        }
      }
      relations = root.path("relations").asText("");
    } catch (Exception e) {
      // keep whatever was parsed; malformed entries degrade to empty summaries
    }
    StringBuilder out = new StringBuilder();
    if (visits.isEmpty()) {
      out.append("no loop heads on trace");
    } else {
      out.append("loop visits:");
      for (Map.Entry<String, Integer> e : visits.entrySet()) {
        out.append(' ').append(e.getKey()).append(" x").append(e.getValue());
      }
    }
    if (!relations.isBlank()) {
      String rel = relations.strip().replace('\n', ' ');
      if (rel.length() > 200) {
        rel = rel.substring(0, 200);
      }
      out.append("; relations: ").append(rel);
    }
    return out.toString();
  }

  private static Map<String, Integer> visitsByHead(String compact) {
    Map<String, Integer> out = new LinkedHashMap<>();
    String prefix = "loop visits:";
    int start = compact.indexOf(prefix);
    if (start < 0) {
      return out;
    }
    start += prefix.length();
    int end = compact.indexOf(';', start);
    if (end < 0) {
      end = compact.length();
    }
    List<String> tokens =
        Splitter.on(CharMatcher.whitespace())
            .omitEmptyStrings()
            .trimResults()
            .splitToList(compact.substring(start, end));
    for (int i = 0; i + 1 < tokens.size(); i += 2) {
      Matcher m = COUNT_PATTERN.matcher(tokens.get(i + 1));
      if (m.matches()) {
        out.put(tokens.get(i), Integer.parseInt(m.group(1)));
      }
    }
    return out;
  }

  private static final Pattern COUNT_PATTERN = Pattern.compile("x(\\d+)");
}
