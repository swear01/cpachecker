// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import java.util.Locale;

/** When to invoke the LLM during spurious CEGAR refinements. */
public enum LlmCallSchedule {

  /** Only the first spurious refinement (refinement #1). Default, lowest API cost. */
  FIRST_SPURIOUS,

  /**
   * Call on refinement #1, then every {@code llmEveryNSpuriousRefinements} spurious refinements
   * (#1, #1+N, #1+2N, …), subject to {@code maxLlmRoundsPerAnalysis}.
   */
  EVERY_N_SPURIOUS,

  /**
   * Call when at least {@code llmMinIntervalSec} seconds have passed since the previous LLM call
   * (always calls on refinement #1). Subject to max rounds cap.
   */
  MIN_INTERVAL,

  /** Both {@link #EVERY_N_SPURIOUS} and {@link #MIN_INTERVAL} must be satisfied. */
  EVERY_N_AND_INTERVAL;

  public static LlmCallSchedule fromConfig(String value) throws IllegalArgumentException {
    if (value == null || value.isBlank()) {
      return FIRST_SPURIOUS;
    }
    return switch (value.strip().toLowerCase(Locale.ROOT).replace('-', '_')) {
      case "first_spurious", "first", "bootstrap" -> FIRST_SPURIOUS;
      case "every_n", "every_n_spurious", "everyn" -> EVERY_N_SPURIOUS;
      case "min_interval", "interval", "time" -> MIN_INTERVAL;
      case "every_n_and_interval", "every_n_interval", "both" -> EVERY_N_AND_INTERVAL;
      default ->
          throw new IllegalArgumentException(
              "Unknown vguide.llmCallSchedule: "
                  + value
                  + " (use first_spurious, every_n, min_interval, every_n_and_interval)");
    };
  }
}
