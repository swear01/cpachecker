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
  public void defaultsToSafeOnly() throws InvalidConfigurationException {
    VGuideOptions opts = new VGuideOptions(Configuration.defaultConfiguration());

    assertThat(opts.isDualPromptMode()).isFalse();
  }

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

  @Test
  public void predicateUsefulnessGateIsOptIn() throws InvalidConfigurationException {
    VGuideOptions defaults = new VGuideOptions(Configuration.defaultConfiguration());
    VGuideOptions enabled =
        new VGuideOptions(
            Configuration.builder()
                .setOption("vguide.enablePredicateUsefulnessGate", "true")
                .build());

    assertThat(defaults.isPredicateUsefulnessGateEnabled()).isFalse();
    assertThat(enabled.isPredicateUsefulnessGateEnabled()).isTrue();
  }

  @Test
  public void defaultPredicateBudgetUsesEstablishedRange() throws InvalidConfigurationException {
    PredicateBudget budget =
        new VGuideOptions(Configuration.defaultConfiguration()).getPredicateBudget();

    assertThat(budget.minPerCall()).isEqualTo(8);
    assertThat(budget.maxPerCall()).isEqualTo(12);
  }

  @Test
  public void compilerOnlyDoesNotNeedLlmClient() throws InvalidConfigurationException {
    VGuideOptions opts =
        new VGuideOptions(
            Configuration.builder()
                .setOption("vguide.enablePrecisionCompiler", "true")
                .setOption("vguide.maxLlmRoundsPerAnalysis", "0")
                .build());

    assertThat(opts.isPrecisionCompilerEnabled()).isTrue();
    assertThat(opts.needsLlmClient()).isFalse();
  }
}
