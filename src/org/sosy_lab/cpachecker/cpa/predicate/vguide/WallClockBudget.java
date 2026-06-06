// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

/** Tracks wall-clock budget for LLM calls during one analysis. */
public final class WallClockBudget {

  private static final long MIN_MS_FOR_LLM = 15_000L;

  private final long analysisStartMs;
  private final long budgetMs;
  private long llmUsedMs;

  public WallClockBudget(int wallBudgetSec) {
    analysisStartMs = System.currentTimeMillis();
    budgetMs = wallBudgetSec > 0 ? wallBudgetSec * 1000L : Long.MAX_VALUE;
  }

  public boolean hasRemainingForLlm() {
    long elapsed = System.currentTimeMillis() - analysisStartMs;
    long remaining = budgetMs - elapsed - llmUsedMs;
    return remaining >= MIN_MS_FOR_LLM;
  }

  public void recordLlmCall(long durationMs) {
    llmUsedMs += durationMs;
  }
}
