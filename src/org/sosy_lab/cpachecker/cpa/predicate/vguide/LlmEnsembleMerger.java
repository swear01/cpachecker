// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import com.google.common.collect.ImmutableList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Merges multiple LLM raw responses into one loop-head candidate list. */
public final class LlmEnsembleMerger {

  private LlmEnsembleMerger() {}

  /**
   * Union of parsed candidates from each draw, deduped by (loop heads, predicate) so the same
   * predicate at different loop heads stays distinct. Apply the predicate budget separately to each
   * draw before merging, so later draws can contribute additional candidates.
   */
  public static ImmutableList<LoopHeadCandidate> mergeCandidates(
      List<String> rawResponses, PredicateBudget budget) {
    Map<String, LoopHeadCandidate> byKey = new LinkedHashMap<>();
    for (String raw : rawResponses) {
      Map<String, LoopHeadCandidate> draw = new LinkedHashMap<>();
      for (LoopHeadCandidate c : LoopHeadCandidateParser.parse(raw)) {
        draw.putIfAbsent(c.dedupKey(), c);
        if (draw.size() >= budget.maxPerCall()) {
          break;
        }
      }
      draw.forEach(byKey::putIfAbsent);
    }
    return ImmutableList.copyOf(byKey.values());
  }

  /** Union SAFE then BUG candidates without budget capping, SAFE winning on equal keys. */
  public static ImmutableList<LoopHeadCandidate> mergeDualUnionCandidates(
      ImmutableList<LoopHeadCandidate> safe, ImmutableList<LoopHeadCandidate> bug) {
    Map<String, LoopHeadCandidate> byKey = new LinkedHashMap<>();
    for (LoopHeadCandidate c : safe) {
      byKey.putIfAbsent(c.dedupKey(), c);
    }
    for (LoopHeadCandidate c : bug) {
      byKey.putIfAbsent(c.dedupKey(), c);
    }
    return ImmutableList.copyOf(byKey.values());
  }
}
