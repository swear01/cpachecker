// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import org.sosy_lab.common.configuration.Configuration;
import org.sosy_lab.common.configuration.IntegerOption;
import org.sosy_lab.common.configuration.InvalidConfigurationException;
import org.sosy_lab.common.configuration.Option;
import org.sosy_lab.common.configuration.Options;

/** Configuration for unified VGuide orchestration ({@code --option vguide.*}). */
@Options(prefix = "vguide")
public class VGuideOptions {

  @Option(
      secure = true,
      description = "Enable unified VGuide bridge when useVocabularyGuide=true")
  private boolean enable = true;

  @Option(
      secure = true,
      description =
          "Wall-clock budget in seconds for LLM calls during analysis (0 = use remaining"
              + " CPAchecker time limit only)")
  @IntegerOption(min = 0)
  private int wallBudgetSec = 0;

  @Option(
      secure = true,
      description =
          "Hard cap on spurious rounds that invoke LLM (each round may issue multiple API"
              + " draws when llmSamplesPerCall>1). 0 = no LLM.")
  @IntegerOption(min = 0)
  private int maxLlmRoundsPerAnalysis = 1;

  @Option(
      secure = true,
      description =
          "API draws per scheduled LLM round after refinement #1. Refinement #1 always uses 1"
              + " draw (cache seed, no parallel). Total APIs = 1 + (K-1) parallel extras.")
  @IntegerOption(min = 1)
  private int llmSamplesPerCall = 1;

  @Option(
      secure = true,
      description =
          "Max parallel API calls for the (K-1) ensemble extras (refinement #1 never parallel).")
  @IntegerOption(min = 1)
  private int llmSampleParallelism = 4;

  @Option(
      secure = true,
      description =
          "When to call LLM on spurious CE: first_spurious (default), every_n, min_interval,"
              + " every_n_and_interval")
  private String llmCallSchedule = "first_spurious";

  @Option(
      secure = true,
      description =
          "For every_n / every_n_and_interval: call on refinements #1, #1+N, #1+2N, … (N>=1)")
  @IntegerOption(min = 1)
  private int llmEveryNSpuriousRefinements = 5;

  @Option(
      secure = true,
      description =
          "For min_interval / every_n_and_interval: minimum seconds between LLM calls (0 = no"
              + " wait except refinement #1)")
  @IntegerOption(min = 0)
  private int llmMinIntervalSec = 0;

  @Option(
      secure = true,
      description =
          "Directory containing predicate_sets/<benchmark>.md or .json for NO_SPURIOUS"
              + " exception path")
  private String frozenDir = "docs/vguided-cegar/predicate_sets";

  @Option(
      secure = true,
      description = "Strengthen interpolants with predicates ENTAILED on block formulas")
  private boolean allowInterpolantStrengthen = true;

  @Option(
      secure = true,
      description =
          "Run L3 block entailment (block ⊨ pred). When false, skip SMT classification and"
              + " treat all parsed predicates as PRECISION_ONLY (ablation: no ENTAILED /"
              + " strengthen)")
  private boolean enableL3Entailment = true;

  private LlmCallSchedule parsedSchedule = LlmCallSchedule.FIRST_SPURIOUS;

  public VGuideOptions(Configuration config) throws InvalidConfigurationException {
    config.inject(this);
    parsedSchedule = LlmCallSchedule.fromConfig(llmCallSchedule);
  }

  public boolean isEnable() {
    return enable;
  }

  public int getWallBudgetSec() {
    return wallBudgetSec;
  }

  public int getMaxLlmRoundsPerAnalysis() {
    return maxLlmRoundsPerAnalysis;
  }

  public int getLlmSamplesPerCall() {
    return llmSamplesPerCall;
  }

  public int getLlmSampleParallelism() {
    return llmSampleParallelism;
  }

  /** Samples for this spurious round: #1 always 1; later rounds use llmSamplesPerCall. */
  public int getLlmSamplesForRefinement(int refinementIndex) {
    return refinementIndex == 1 ? 1 : Math.max(1, llmSamplesPerCall);
  }

  public LlmCallSchedule getLlmCallSchedule() {
    return parsedSchedule;
  }

  public int getLlmEveryNSpuriousRefinements() {
    return llmEveryNSpuriousRefinements;
  }

  public int getLlmMinIntervalSec() {
    return llmMinIntervalSec;
  }

  public String getFrozenDir() {
    return frozenDir;
  }

  public boolean isAllowInterpolantStrengthen() {
    return allowInterpolantStrengthen;
  }

  public boolean isEnableL3Entailment() {
    return enableL3Entailment;
  }
}
