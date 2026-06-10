// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.truth.Truth.assertThat;

import org.junit.Test;
import org.sosy_lab.common.configuration.Configuration;
import org.sosy_lab.common.configuration.InvalidConfigurationException;

public class VGuideOptionsTest {

  @Test
  public void dualModeUsesSamplesOnFirstRefinement() throws InvalidConfigurationException {
    VGuideOptions opts =
        new VGuideOptions(
            Configuration.builder()
                .setOption("vguide.dualPromptMode", "true")
                .setOption("vguide.llmSamplesPerCall", "3")
                .build());
    assertThat(opts.getLlmSamplesForRefinement(1)).isEqualTo(3);
    assertThat(opts.isDualPromptMode()).isTrue();
  }

  @Test
  public void singleModeKeepsFirstRefinementOneDraw() throws InvalidConfigurationException {
    VGuideOptions opts =
        new VGuideOptions(
            Configuration.builder()
                .setOption("vguide.dualPromptMode", "false")
                .setOption("vguide.llmSamplesPerCall", "3")
                .build());
    assertThat(opts.getLlmSamplesForRefinement(1)).isEqualTo(1);
    assertThat(opts.getLlmSamplesForRefinement(2)).isEqualTo(3);
  }
}
