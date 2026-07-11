// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.truth.Truth.assertThat;

import org.junit.Test;
import org.sosy_lab.common.configuration.Configuration;
import org.sosy_lab.common.log.LogManager;

public class LlmCallSchedulerTest {

  private static LlmCallScheduler scheduler(String schedule, int max, int everyN, int minSec)
      throws Exception {
    return scheduler(schedule, max, everyN, minSec, 0);
  }

  private static LlmCallScheduler scheduler(
      String schedule, int max, int everyN, int minSec, int processMax)
      throws Exception {
    Configuration config =
        Configuration.builder()
            .setOption("vguide.llmCallSchedule", schedule)
            .setOption("vguide.maxLlmRoundsPerAnalysis", Integer.toString(max))
            .setOption("vguide.maxLlmRoundsPerProcess", Integer.toString(processMax))
            .setOption("vguide.llmEveryNSpuriousRefinements", Integer.toString(everyN))
            .setOption("vguide.llmMinIntervalSec", Integer.toString(minSec))
            .build();
    return new LlmCallScheduler(new VGuideOptions(config), LogManager.createTestLogManager());
  }

  /** Manually-advanced clock so the wall-clock trigger can be tested deterministically. */
  private static final class FakeClock implements java.util.function.LongSupplier {
    private long nowMs;

    FakeClock(long startMs) {
      nowMs = startMs;
    }

    void advanceSec(int seconds) {
      nowMs += seconds * 1000L;
    }

    @Override
    public long getAsLong() {
      return nowMs;
    }
  }

  private static LlmCallScheduler schedulerWithClock(
      String schedule, int max, int everyN, int minSec, java.util.function.LongSupplier clock)
      throws Exception {
    Configuration config =
        Configuration.builder()
            .setOption("vguide.llmCallSchedule", schedule)
            .setOption("vguide.maxLlmRoundsPerAnalysis", Integer.toString(max))
            .setOption("vguide.maxLlmRoundsPerProcess", "0")
            .setOption("vguide.llmEveryNSpuriousRefinements", Integer.toString(everyN))
            .setOption("vguide.llmMinIntervalSec", Integer.toString(minSec))
            .build();
    return new LlmCallScheduler(
        new VGuideOptions(config), LogManager.createTestLogManager(), clock);
  }

  private static LlmCallScheduler schedulerWithPeel(int peelThreshold, int everyN, int minSec)
      throws Exception {
    Configuration config =
        Configuration.builder()
            .setOption("vguide.llmCallSchedule", "every_n_or_interval")
            .setOption("vguide.maxLlmRoundsPerAnalysis", "20")
            .setOption("vguide.maxLlmRoundsPerProcess", "0")
            .setOption("vguide.llmEveryNSpuriousRefinements", Integer.toString(everyN))
            .setOption("vguide.llmMinIntervalSec", Integer.toString(minSec))
            .setOption("vguide.peelLoopHeadThreshold", Integer.toString(peelThreshold))
            .build();
    return new LlmCallScheduler(
        new VGuideOptions(config), LogManager.createTestLogManager(), new FakeClock(0));
  }

  @Test
  public void firstSpurious_onlyRefinementOne() throws Exception {
    LlmCallScheduler.resetProcessRoundCounterForTest();
    LlmCallScheduler s = scheduler("first_spurious", 10, 5, 0);
    assertThat(s.shouldCall(1, 0)).isTrue();
    assertThat(s.shouldCall(2, 0)).isFalse();
    assertThat(s.shouldCall(6, 0)).isFalse();
  }

  @Test
  public void everyN_callsOnOneAndEveryNth() throws Exception {
    LlmCallScheduler.resetProcessRoundCounterForTest();
    LlmCallScheduler s = scheduler("every_n", 10, 5, 0);
    assertThat(s.shouldCall(1, 0)).isTrue();
    assertThat(s.shouldCall(2, 0)).isFalse();
    assertThat(s.shouldCall(6, 0)).isTrue();
    assertThat(s.shouldCall(11, 0)).isTrue();
    assertThat(s.shouldCall(7, 0)).isFalse();
  }

  @Test
  public void maxCallsCapsTotalInvocations() throws Exception {
    LlmCallScheduler.resetProcessRoundCounterForTest();
    LlmCallScheduler s = scheduler("every_n", 2, 1, 0);
    assertThat(s.shouldCall(1, 0)).isTrue();
    s.recordCallCompleted();
    assertThat(s.shouldCall(2, 0)).isTrue();
    s.recordCallCompleted();
    assertThat(s.shouldCall(3, 0)).isFalse();
  }

  @Test
  public void processRoundCapAppliesAcrossSchedulers() throws Exception {
    LlmCallScheduler.resetProcessRoundCounterForTest();
    LlmCallScheduler firstBridge = scheduler("every_n", 10, 1, 0, 2);
    LlmCallScheduler secondBridge = scheduler("every_n", 10, 1, 0, 2);

    assertThat(firstBridge.shouldCall(1, 0)).isTrue();
    firstBridge.recordCallCompleted();
    assertThat(secondBridge.shouldCall(1, 0)).isTrue();
    secondBridge.recordCallCompleted();

    assertThat(firstBridge.shouldCall(2, 0)).isFalse();
    assertThat(firstBridge.skipReason(2)).isEqualTo("process_round_cap");
  }

  @Test
  public void everyNOrInterval_countTriggerFiresAtNNotOne() throws Exception {
    LlmCallScheduler.resetProcessRoundCounterForTest();
    // minSec=0 disables the time trigger, isolating the count trigger.
    LlmCallScheduler s = schedulerWithClock("every_n_or_interval", 20, 5, 0, new FakeClock(0));
    assertThat(s.shouldCall(1, 0)).isFalse(); // key fix: no auto-fire at refinement #1
    assertThat(s.shouldCall(4, 0)).isFalse();
    assertThat(s.shouldCall(5, 0)).isTrue();
    assertThat(s.shouldCall(6, 0)).isFalse();
    assertThat(s.shouldCall(10, 0)).isTrue();
  }

  @Test
  public void everyNOrInterval_timeTriggerWaitsDFromStart() throws Exception {
    LlmCallScheduler.resetProcessRoundCounterForTest();
    FakeClock clock = new FakeClock(1_000_000L);
    // everyN huge so the count trigger never fires within the test; D = 10s.
    LlmCallScheduler s = schedulerWithClock("every_n_or_interval", 20, 100_000, 10, clock);
    assertThat(s.shouldCall(1, 0)).isFalse(); // 0s elapsed < 10s
    clock.advanceSec(9);
    assertThat(s.shouldCall(2, 0)).isFalse(); // 9s < 10s
    clock.advanceSec(1);
    assertThat(s.shouldCall(3, 0)).isTrue(); // 10s elapsed since analysis start
  }

  @Test
  public void everyNOrInterval_timeTriggerReArmsAfterCall() throws Exception {
    LlmCallScheduler.resetProcessRoundCounterForTest();
    FakeClock clock = new FakeClock(0);
    LlmCallScheduler s = schedulerWithClock("every_n_or_interval", 20, 100_000, 10, clock);
    clock.advanceSec(10);
    assertThat(s.shouldCall(2, 0)).isTrue();
    s.recordCallCompleted(); // last-call timestamp = now
    assertThat(s.shouldCall(3, 0)).isFalse(); // 0s since last call
    clock.advanceSec(10);
    assertThat(s.shouldCall(4, 0)).isTrue(); // 10s since last call
  }

  @Test
  public void everyNOrInterval_orSemanticsCountFiresWhileTimeNotElapsed() throws Exception {
    LlmCallScheduler.resetProcessRoundCounterForTest();
    // D = 100s (never elapses here), but the count trigger at #5 still fires -> proves OR.
    LlmCallScheduler s = schedulerWithClock("every_n_or_interval", 20, 5, 100, new FakeClock(0));
    assertThat(s.shouldCall(5, 0)).isTrue();
  }

  @Test
  public void everyNOrInterval_peelFiresEarlyAtThreshold() throws Exception {
    LlmCallScheduler.resetProcessRoundCounterForTest();
    // peel threshold 4; count (everyN huge) and time (minSec 0) off -> isolate the peel trigger.
    LlmCallScheduler s = schedulerWithPeel(4, 100_000, 0);
    assertThat(s.shouldCall(1, 10)).isFalse(); // never at refinement #1 even with high peel
    assertThat(s.shouldCall(2, 3)).isFalse(); // 3 < 4
    assertThat(s.shouldCall(2, 4)).isTrue(); // peel fires early once loop-head visits reach 4
    assertThat(s.shouldCall(3, 6)).isTrue();
  }

  @Test
  public void everyNOrInterval_peelDisabledWhenThresholdZero() throws Exception {
    LlmCallScheduler.resetProcessRoundCounterForTest();
    LlmCallScheduler s = schedulerWithPeel(0, 100_000, 0); // peel off
    assertThat(s.shouldCall(3, 100)).isFalse(); // huge peel ignored when threshold is 0
  }

  @Test
  public void predicateUsefulnessSuppressionIsPerAnalysis() throws Exception {
    LlmCallScheduler.resetProcessRoundCounterForTest();
    LlmCallScheduler suppressed = scheduler("every_n", 10, 1, 0);
    LlmCallScheduler unaffected = scheduler("every_n", 10, 1, 0);

    suppressed.suppressForPredicateUsefulnessGate();

    assertThat(suppressed.shouldCall(1, 0)).isFalse();
    assertThat(suppressed.skipReason(1)).isEqualTo("predicate_usefulness_gate");
    assertThat(unaffected.shouldCall(1, 0)).isTrue();
  }
}
