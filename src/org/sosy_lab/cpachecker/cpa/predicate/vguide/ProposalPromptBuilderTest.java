// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.truth.Truth.assertThat;

import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableMap;
import com.google.common.collect.ImmutableSet;
import java.util.Optional;
import org.junit.Test;
import org.sosy_lab.cpachecker.cpa.predicate.BlockFormulaStrategy.BlockFormulas;

public class ProposalPromptBuilderTest {

  @Test
  public void buildPrompt_includesDynamicBudgetAndCeSummary() {
    LoopHeadIndex loopHeads = new LoopHeadIndex(Optional.empty());
    ProposalPromptBuilder builder = new ProposalPromptBuilder(loopHeads, false);
    ContextPack pack =
        new ContextPack(
            1,
            "int i,n;\nwhile(i<n){i++;}\n",
            "i",
            ImmutableList.of(),
            ImmutableMap.of(),
            ImmutableSet.of(),
            new BlockFormulas(ImmutableList.of()),
            ImmutableList.of(),
            "L@N1: (bvslt i n)\n",
            "");
    PredicateBudget budget = new PredicateBudget(8, 16);
    PromptMessages safe = builder.buildPrompt(pack, budget, PromptProfile.SAFE, 1);
    assertThat(safe.user()).contains("Return between 8 and 16 predicates");
    assertThat(safe.user()).contains("STRUCTURED SPURIOUS COUNTEREXAMPLE");
    assertThat(safe.user()).contains("L@N1:");
    assertThat(safe.system()).contains("\"candidates\"");
    assertThat(safe.system()).contains("loop-head-candidate-v1");
    assertThat(safe.system()).contains("never broadcasts");
  }

  @Test
  public void buildPrompt_encouragesBroadNonInvariantPredicates() {
    LoopHeadIndex loopHeads = new LoopHeadIndex(Optional.empty());
    ProposalPromptBuilder builder = new ProposalPromptBuilder(loopHeads, false);
    ContextPack pack =
        new ContextPack(
            1,
            "int i;\nwhile(i<10){i++;}\n",
            "i == 10",
            ImmutableList.of(),
            ImmutableMap.of(),
            ImmutableSet.of(),
            new BlockFormulas(ImmutableList.of()),
            ImmutableList.of(),
            "L@N1: (bvslt i (_ bv10 32))\n",
            "");

    PromptMessages safe =
        builder.buildPrompt(pack, new PredicateBudget(8, 12), PromptProfile.SAFE, 1);

    assertThat(safe.user()).contains("does not need to be an invariant");
    assertThat(safe.user()).contains("Prefer broad coverage and informed guesses");
    assertThat(safe.user()).contains("Use the available budget");
    assertThat(safe.user()).contains("Initiation-only, exit-only, threshold");
  }

  @Test
  public void arrayPromptUsesCanonicalSourceSyntax() {
    LoopHeadIndex loopHeads = new LoopHeadIndex(Optional.empty());
    ProposalPromptBuilder builder = new ProposalPromptBuilder(loopHeads, false);
    ContextPack pack =
        new ContextPack(
            1,
            "int A[1024]; int i;\nwhile (i < 1024) { if (A[i] == 0) break; i++; }\n",
            "i < 1024",
            ImmutableList.of(),
            ImmutableMap.of(),
            ImmutableSet.of(),
            new BlockFormulas(ImmutableList.of()),
            ImmutableList.of(),
            "(no CE relations extracted)\n",
            "");

    PromptMessages prompt =
        builder.buildPrompt(pack, new PredicateBudget(4, 8), PromptProfile.SAFE, 1);

    assertThat(prompt.user())
        .contains("array element reads are allowed only in source-level C syntax");
    assertThat(prompt.user()).contains("A[i]");
    assertThat(prompt.user()).doesNotContain("do NOT use array identifiers");
  }

  @Test
  public void historyBlockInsertedWhenProvided() {
    LoopHeadIndex loopHeads = new LoopHeadIndex(Optional.empty());
    ProposalPromptBuilder builder = new ProposalPromptBuilder(loopHeads, false);
    ContextPack pack =
        new ContextPack(
            1,
            "int i,n;\nwhile(i<n){i++;}\n",
            "i",
            ImmutableList.of(),
            ImmutableMap.of(),
            ImmutableSet.of(),
            new BlockFormulas(ImmutableList.of()),
            ImmutableList.of(),
            "L@N1: (bvslt i n)\n",
            "");
    PredicateBudget budget = new PredicateBudget(8, 16);

    PromptMessages without = builder.buildPrompt(pack, budget, PromptProfile.SAFE, 1);
    assertThat(without.user()).doesNotContain("PRIOR CE HISTORY");

    PromptMessages with =
        builder.buildPrompt(pack, budget, PromptProfile.SAFE, 1, "[refinement 1] loop visits: N1 x2\n");
    assertThat(with.user()).contains("PRIOR CE HISTORY (bounded, read-only)");
    assertThat(with.user()).contains("loop visits: N1 x2");
  }

  @Test
  public void nativePredicateContextBlockInsertedWhenProvided() {
    LoopHeadIndex loopHeads = new LoopHeadIndex(Optional.empty());
    ProposalPromptBuilder builder = new ProposalPromptBuilder(loopHeads, false);
    ContextPack pack =
        new ContextPack(
            1,
            "int i,n;\nwhile(i<n){i++;}\n",
            "i",
            ImmutableList.of(),
            ImmutableMap.of(),
            ImmutableSet.of(),
            new BlockFormulas(ImmutableList.of()),
            ImmutableList.of(),
            "L@N1: (bvslt i n)\n",
            "");
    PredicateBudget budget = new PredicateBudget(8, 16);

    PromptMessages without = builder.buildPrompt(pack, budget, PromptProfile.SAFE, 1);
    assertThat(without.user()).doesNotContain("NATIVE CEGAR PRECISION");

    PromptMessages with =
        builder.buildPrompt(
            pack,
            budget,
            PromptProfile.SAFE,
            1,
            "",
            "",
            "[local N1 | native] (bvslt i n)\n");
    assertThat(with.user()).contains("NATIVE CEGAR PRECISION (read-only)");
    assertThat(with.user()).contains("[local N1 | native] (bvslt i n)");
  }

  @Test
  public void safeAndBugShareSourcePrefix() {
    LoopHeadIndex loopHeads = new LoopHeadIndex(Optional.empty());
    ProposalPromptBuilder builder = new ProposalPromptBuilder(loopHeads, false);
    ContextPack pack =
        new ContextPack(
            1,
            "int x;\nwhile(1){ x=0; }\n",
            "x == 1",
            ImmutableList.of(),
            ImmutableMap.of(),
            ImmutableSet.of(),
            new BlockFormulas(ImmutableList.of()),
            ImmutableList.of(),
            "(no CE relations extracted)\n",
            "");
    PredicateBudget budget = new PredicateBudget(4, 8);
    PromptMessages safe = builder.buildPrompt(pack, budget, PromptProfile.SAFE, 1);
    PromptMessages bug = builder.buildPrompt(pack, budget, PromptProfile.BUG_HUNT, 1);
    String sourceMarker = "Source code:\n";
    int sourceIdx = safe.user().indexOf(sourceMarker);
    assertThat(sourceIdx).isAtLeast(0);
    assertThat(bug.user().indexOf(sourceMarker)).isEqualTo(sourceIdx);
    int sharedEnd = sourceIdx + sourceMarker.length() + pack.sourceCode().length();
    assertThat(safe.user().substring(0, sharedEnd)).isEqualTo(bug.user().substring(0, sharedEnd));
    assertThat(safe.user()).contains("Target assertion:");
    assertThat(bug.user()).contains("Assertion (may FAIL");
    assertThat(bug.user()).contains("assertion FAILURE");
  }
}
