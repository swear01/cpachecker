// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Level;
import org.sosy_lab.common.log.LogManager;

/** Decides whether a spurious refinement should trigger an LLM API call. */
public final class LlmCallScheduler {

  private final LogManager logger;
  private final LlmCallSchedule schedule;
  private final int maxCallsPerAnalysis;
  private final int maxCallsPerProcess;
  private final int everyNSpuriousRefinements;
  private final long minIntervalMs;

  private static final AtomicInteger PROCESS_LLM_CALLS_DONE = new AtomicInteger();

  private int llmCallsDone;
  private long lastLlmCallMs;

  public LlmCallScheduler(VGuideOptions options, LogManager logger) {
    this.logger = logger;
    schedule = options.getLlmCallSchedule();
    maxCallsPerAnalysis = options.getMaxLlmRoundsPerAnalysis();
    maxCallsPerProcess = options.getMaxLlmRoundsPerProcess();
    everyNSpuriousRefinements = Math.max(1, options.getLlmEveryNSpuriousRefinements());
    long intervalSec = options.getLlmMinIntervalSec();
    minIntervalMs = intervalSec > 0 ? intervalSec * 1000L : 0L;
  }

  /** Returns whether an LLM call is allowed for this spurious refinement index. */
  public boolean shouldCall(int refinementIndex) {
    if (llmCallsDone >= maxCallsPerAnalysis) {
      logger.log(
          Level.FINE,
          "VGuide LLM skip: max calls reached (",
          llmCallsDone,
          "/",
          maxCallsPerAnalysis,
          ")");
      return false;
    }
    if (isProcessRoundCapReached()) {
      logger.log(
          Level.FINE,
          "VGuide LLM skip: process round cap reached (",
          PROCESS_LLM_CALLS_DONE.get(),
          "/",
          maxCallsPerProcess,
          ")");
      return false;
    }
    boolean refinementSlot = matchesRefinementSchedule(refinementIndex);
    boolean intervalOk = matchesIntervalSchedule(refinementIndex);
    boolean call =
        switch (schedule) {
          case FIRST_SPURIOUS -> refinementIndex == 1;
          case EVERY_N_SPURIOUS -> refinementSlot;
          case MIN_INTERVAL -> intervalOk;
          case EVERY_N_AND_INTERVAL -> refinementSlot && intervalOk;
        };
    if (!call) {
      logger.log(
          Level.FINE,
          "VGuide LLM skip at refinement #",
          refinementIndex,
          " schedule=",
          schedule,
          " everyN=",
          everyNSpuriousRefinements,
          " minIntervalSec=",
          minIntervalMs / 1000);
    }
    return call;
  }

  public void recordCallCompleted() {
    llmCallsDone++;
    if (maxCallsPerProcess > 0) {
      PROCESS_LLM_CALLS_DONE.incrementAndGet();
    }
    lastLlmCallMs = System.currentTimeMillis();
  }

  public int getLlmCallsDone() {
    return llmCallsDone;
  }

  public boolean isMaxRoundsReached() {
    return llmCallsDone >= maxCallsPerAnalysis;
  }

  public boolean isProcessRoundCapReached() {
    return maxCallsPerProcess > 0 && PROCESS_LLM_CALLS_DONE.get() >= maxCallsPerProcess;
  }

  /** Reason when {@link #shouldCall(int)} is false (after max-rounds check). */
  public String skipReason(int refinementIndex) {
    if (isMaxRoundsReached()) {
      return "max_rounds";
    }
    if (isProcessRoundCapReached()) {
      return "process_round_cap";
    }
    if (!matchesRefinementSchedule(refinementIndex) && schedule != LlmCallSchedule.MIN_INTERVAL) {
      return "schedule";
    }
    if (!matchesIntervalSchedule(refinementIndex)) {
      return "schedule";
    }
    return "schedule";
  }

  private boolean matchesRefinementSchedule(int refinementIndex) {
    if (refinementIndex == 1) {
      return true;
    }
    if (schedule == LlmCallSchedule.FIRST_SPURIOUS || schedule == LlmCallSchedule.MIN_INTERVAL) {
      return false;
    }
    int n = everyNSpuriousRefinements;
    return n == 1 || (refinementIndex - 1) % n == 0;
  }

  private boolean matchesIntervalSchedule(int refinementIndex) {
    if (refinementIndex == 1) {
      return true;
    }
    if (schedule == LlmCallSchedule.FIRST_SPURIOUS
        || schedule == LlmCallSchedule.EVERY_N_SPURIOUS) {
      return false;
    }
    if (minIntervalMs <= 0) {
      return true;
    }
    if (lastLlmCallMs == 0) {
      return true;
    }
    return System.currentTimeMillis() - lastLlmCallMs >= minIntervalMs;
  }

  static void resetProcessRoundCounterForTest() {
    PROCESS_LLM_CALLS_DONE.set(0);
  }
}
