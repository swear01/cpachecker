// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import java.nio.file.Path;
import org.sosy_lab.common.configuration.Configuration;
import org.sosy_lab.common.configuration.FileOption;
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
      description = "Wall-clock budget in seconds for LLM calls during analysis (0 = unlimited)")
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
          "Process-wide hard cap on LLM rounds across all VGuide bridges in this JVM. 0 ="
              + " unlimited.")
  @IntegerOption(min = 0)
  private int maxLlmRoundsPerProcess = 0;

  @Option(
      secure = true,
      description =
          "API draws per prompt profile per scheduled LLM round (SAFE and BUG each use K draws"
              + " when dualPromptMode=true). Each profile: 1 sync + (K-1) parallel extras.")
  @IntegerOption(min = 1)
  private int llmSamplesPerCall = 1;

  @Option(
      secure = true,
      description =
          "Run SAFE and BUG_HUNT prompt profiles each LLM round (2×K HTTP when K=llmSamplesPerCall).")
  private boolean dualPromptMode = true;

  @Option(
      secure = true,
      description =
          "Soft lower bound in LLM prompt: aim for at least this many predicates per response"
              + " (not enforced after parse).")
  @IntegerOption(min = 1)
  private int minPredicatesPerCall = 3;

  @Option(
      secure = true,
      description =
          "Hard upper bound per LLM response: prompt asks for at most this many; extras truncated"
              + " after parse (array order = priority).")
  @IntegerOption(min = 1)
  private int maxPredicatesPerCall = 6;

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
          "For every_n_or_interval: also fire (peel/divergence trigger) when the counterexample"
              + " passes loop heads >= this many times, i.e. stock is unrolling a loop. Fires early"
              + " (refinement #2+) instead of waiting for the every_n / interval trigger. 0 = off.")
  @IntegerOption(min = 0)
  private int peelLoopHeadThreshold = 0;

  @Option(
      secure = true,
      description =
          "Enable the frozen verifier-side gate that may suppress optional LLM precision batches")
  private boolean enablePredicateUsefulnessGate = false;

  @Option(
      secure = true,
      description =
          "Bounded counterexample history fed to the LLM (Issue #5): OFF, LATEST (previous round"
              + " only), BOUNDED (recent entries), or BOUNDED_WITH_DELTA (entries + explicit"
              + " current-vs-previous delta)")
  private CeHistoryMode ceHistoryMode = CeHistoryMode.OFF;

  public enum CeHistoryMode {
    OFF,
    LATEST,
    BOUNDED,
    BOUNDED_WITH_DELTA
  }

  @Option(
      secure = true,
      description =
          "Replace prior-round LLM-owned predicates in active precision on each new LLM round"
              + " (P_active(t) = P_native(t) u P_LLM(t)) instead of accumulating (Issue #8)")
  private boolean replaceLlmPredicates = false;

  @Option(
      secure = true,
      description =
          "Directory containing predicate_sets/<benchmark>.md or .json for NO_SPURIOUS"
              + " exception path")
  @FileOption(FileOption.Type.OPTIONAL_INPUT_FILE)
  private Path frozenDir = Path.of("docs/vguided-cegar/predicate_sets");

  @Option(
      secure = true,
      description =
          "Fire LLM before any CEGAR round using source-code only (no CE context). Predicates"
              + " injected into initial precision. Replaces first-spurious trigger.")
  private boolean sourcePriorMode = false;

  @Option(
      secure = true,
      description = "Strengthen interpolants with predicates ENTAILED on block formulas")
  private boolean allowInterpolantStrengthen = true;

  @Option(
      secure = true,
      description =
          "Run L3 block entailment (block ⊨ pred). When false, skip SMT classification and"
              + " treat all parsed predicates as PRECISION_ONLY (default; no ENTAILED /"
              + " strengthen). Enable for parity/invariant-heavy benchmarks.")
  private boolean enableL3Entailment = false;

  @Option(
      secure = true,
      description =
          "Per-call min/max from ContextPack complexity (low 4–8, medium 6–12, high 8–16)."
              + " When false, use minPredicatesPerCall / maxPredicatesPerCall.")
  private boolean enableAdaptivePredicateBudget = false;

  @Option(
      secure = true,
      description = "Max completion tokens per DeepSeek chat completion (raise for max budget ≥12).")
  @IntegerOption(min = 256)
  private int llmMaxCompletionTokens = 1024;

  private LlmCallSchedule parsedSchedule = LlmCallSchedule.FIRST_SPURIOUS;

  public VGuideOptions(Configuration config) throws InvalidConfigurationException {
    config.inject(this);
    if (minPredicatesPerCall > maxPredicatesPerCall) {
      throw new InvalidConfigurationException(
          "vguide.minPredicatesPerCall ("
              + minPredicatesPerCall
              + ") must be <= vguide.maxPredicatesPerCall ("
              + maxPredicatesPerCall
              + ")");
    }
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

  public int getMaxLlmRoundsPerProcess() {
    return maxLlmRoundsPerProcess;
  }

  public int getLlmSamplesPerCall() {
    return llmSamplesPerCall;
  }

  public boolean isDualPromptMode() {
    return dualPromptMode;
  }

  public int getLlmSampleParallelism() {
    return llmSampleParallelism;
  }

  public int getMinPredicatesPerCall() {
    return minPredicatesPerCall;
  }

  public int getMaxPredicatesPerCall() {
    return maxPredicatesPerCall;
  }

  public PredicateBudget getPredicateBudget() {
    return new PredicateBudget(minPredicatesPerCall, maxPredicatesPerCall);
  }

  /** Budget for dump prompt size estimates when adaptive tiers apply. */
  public PredicateBudget getPredicateBudgetForDump() {
    return enableAdaptivePredicateBudget
        ? PredicateBudgetResolver.worstCaseBudget()
        : getPredicateBudget();
  }

  public boolean isEnableAdaptivePredicateBudget() {
    return enableAdaptivePredicateBudget;
  }

  public int getLlmMaxCompletionTokens() {
    return llmMaxCompletionTokens;
  }

  /** Draws per profile for this spurious round. */
  public int getLlmSamplesForRefinement(int refinementIndex) {
    if (dualPromptMode) {
      return Math.max(1, llmSamplesPerCall);
    }
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

  public int getPeelLoopHeadThreshold() {
    return peelLoopHeadThreshold;
  }

  public boolean isReplaceLlmPredicates() {
    return replaceLlmPredicates;
  }

  public boolean isPredicateUsefulnessGateEnabled() {
    return enablePredicateUsefulnessGate;
  }

  public CeHistoryMode getCeHistoryMode() {
    return ceHistoryMode;
  }

  public Path getFrozenDir() {
    return frozenDir;
  }

  public boolean isSourcePriorMode() {
    return sourcePriorMode;
  }

  public boolean isAllowInterpolantStrengthen() {
    return allowInterpolantStrengthen;
  }

  public boolean isEnableL3Entailment() {
    return enableL3Entailment;
  }
}
