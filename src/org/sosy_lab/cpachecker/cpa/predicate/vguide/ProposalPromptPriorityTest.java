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

public class ProposalPromptPriorityTest {

  @Test
  public void headPriorityUsesPositiveSummaryEvidenceWithoutExcludingOmittedHeads() {
    ContextPack pack =
        new ContextPack(
            1,
            "int counter, limit; while (counter < limit) { counter++; }\n",
            "counter >= limit",
            ImmutableList.of(),
            ImmutableMap.of(),
            ImmutableSet.of(),
            new BlockFormulas(ImmutableList.of()),
            ImmutableList.of(),
            "L@N7: (bvslt counter limit)\n",
            "");
    PredicateBudget budget = new PredicateBudget(8, 12);

    for (boolean minimal : new boolean[] {false, true}) {
      ProposalPromptBuilder builder =
          new ProposalPromptBuilder(new LoopHeadIndex(Optional.empty()), minimal);
      for (PromptProfile profile : PromptProfile.values()) {
        PromptMessages prompt = builder.buildPrompt(pack, budget, profile, 1);
        PromptMessages repair =
            builder.buildRepair(pack, ImmutableList.of("invalid"), budget, profile, 2);

        assertThat(prompt.system())
            .contains(
                "When the current counterexample summary shows L@N entries, prioritize useful");
        assertThat(prompt.system())
            .contains("absence from the summary does not prove a head was unvisited");
        assertThat(prompt.system()).doesNotContain("N7");
        assertThat(prompt.system()).doesNotContain("(bvslt counter limit)");
        assertThat(prompt.user()).contains(pack.ceSummary());
        assertThat(repair.system()).isEqualTo(prompt.system());
        assertThat(repair.user()).contains(pack.ceSummary());
      }
    }
  }
}
