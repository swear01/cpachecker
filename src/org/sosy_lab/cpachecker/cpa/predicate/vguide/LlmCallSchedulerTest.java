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
    Configuration config =
        Configuration.builder()
            .setOption("vguide.llmCallSchedule", schedule)
            .setOption("vguide.maxLlmRoundsPerAnalysis", Integer.toString(max))
            .setOption("vguide.llmEveryNSpuriousRefinements", Integer.toString(everyN))
            .setOption("vguide.llmMinIntervalSec", Integer.toString(minSec))
            .build();
    return new LlmCallScheduler(new VGuideOptions(config), LogManager.createTestLogManager());
  }

  @Test
  public void firstSpurious_onlyRefinementOne() throws Exception {
    LlmCallScheduler s = scheduler("first_spurious", 10, 5, 0);
    assertThat(s.shouldCall(1)).isTrue();
    assertThat(s.shouldCall(2)).isFalse();
    assertThat(s.shouldCall(6)).isFalse();
  }

  @Test
  public void everyN_callsOnOneAndEveryNth() throws Exception {
    LlmCallScheduler s = scheduler("every_n", 10, 5, 0);
    assertThat(s.shouldCall(1)).isTrue();
    assertThat(s.shouldCall(2)).isFalse();
    assertThat(s.shouldCall(6)).isTrue();
    assertThat(s.shouldCall(11)).isTrue();
    assertThat(s.shouldCall(7)).isFalse();
  }

  @Test
  public void maxCallsCapsTotalInvocations() throws Exception {
    LlmCallScheduler s = scheduler("every_n", 2, 1, 0);
    assertThat(s.shouldCall(1)).isTrue();
    s.recordCallCompleted();
    assertThat(s.shouldCall(2)).isTrue();
    s.recordCallCompleted();
    assertThat(s.shouldCall(3)).isFalse();
  }
}
