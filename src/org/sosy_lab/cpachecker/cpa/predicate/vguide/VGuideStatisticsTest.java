// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-FileCopyrightText: 2026 SSU-WEI HUANG <https://github.com/swear01>
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.truth.Truth.assertThat;

import com.google.common.collect.ImmutableList;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.Rule;
import org.junit.Test;
import org.junit.rules.TemporaryFolder;
import org.sosy_lab.common.log.LogManager;

public class VGuideStatisticsTest {

  @Rule public TemporaryFolder tempFolder = new TemporaryFolder();

  @Test
  public void telemetryRecordsWhetherCounterexampleVisitedLoopHead() throws Exception {
    Path output = tempFolder.getRoot().toPath().resolve("telemetry.json");
    VGuideStatistics statistics =
        new VGuideStatistics(LogManager.createTestLogManager(), output);
    AgentPortfolio.PortfolioResult portfolio =
        new AgentPortfolio.PortfolioResult(ImmutableList.of(), ImmutableList.of());

    assertThat(Files.readString(output)).isEqualTo("[ ]");
    statistics.record(1, portfolio, ImmutableList.of(), 0, true);
    assertThat(Files.readString(output))
        .contains("\"counterexample_visits_loop_head\" : true");
  }
}
