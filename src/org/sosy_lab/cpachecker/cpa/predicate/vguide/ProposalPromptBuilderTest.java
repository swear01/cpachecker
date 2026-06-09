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
  public void buildFirstSpurious_includesDynamicBudget() {
    LoopHeadIndex loopHeads = new LoopHeadIndex(Optional.empty());
    ProposalPromptBuilder builder = new ProposalPromptBuilder(loopHeads);
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
            "");
    PredicateBudget budget = new PredicateBudget(8, 16);
    String prompt = builder.buildFirstSpurious(pack, budget);
    assertThat(prompt).contains("Return between 8 and 16 predicates");
    assertThat(prompt).contains("\"predicates\"");
    assertThat(prompt).doesNotContain("fewer rather than weak fillers");
  }
}
