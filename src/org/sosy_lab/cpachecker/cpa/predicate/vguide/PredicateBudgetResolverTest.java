// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.truth.Truth.assertThat;
import static org.sosy_lab.cpachecker.cfa.model.CFANode.newDummyCFANode;

import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableMap;
import com.google.common.collect.ImmutableSet;
import org.junit.Test;
import org.sosy_lab.cpachecker.cfa.model.CFANode;
import org.sosy_lab.cpachecker.cpa.predicate.BlockFormulaStrategy.BlockFormulas;

public class PredicateBudgetResolverTest {

  private static ContextPack makePack(String source, String assertion, int loopHeadCount) {
    ImmutableList.Builder<LoopHeadInfo> heads = ImmutableList.builder();
    for (int i = 0; i < loopHeadCount; i++) {
      CFANode node = newDummyCFANode("head" + i);
      heads.add(new LoopHeadInfo(node, "N" + (i + 1), "main"));
    }
    return new ContextPack(
        1,
        source,
        assertion,
        heads.build(),
        ImmutableMap.of(),
        ImmutableSet.of(),
        new BlockFormulas(ImmutableList.of()),
        ImmutableList.of(),
        "",
        "");
  }

  @Test
  public void resolve_lowTier() {
    BudgetResolution res =
        budgetResolver().resolve(makePack("int n;\nwhile(1){}\n", "n", 1), 1);
    assertThat(res.tier()).isEqualTo("low");
    assertThat(res.budget().minPerCall()).isEqualTo(4);
    assertThat(res.budget().maxPerCall()).isEqualTo(8);
  }

  @Test
  public void resolve_mediumTier_twoLoopHeads() {
    String source = "int a,b,c,d,e;\nint A[10];\nint i,j;\nwhile(1){}\nwhile(1){}\n";
    BudgetResolution res = budgetResolver().resolve(makePack(source, "i", 2), 1);
    assertThat(res.tier()).isEqualTo("medium");
    assertThat(res.budget().minPerCall()).isEqualTo(6);
    assertThat(res.budget().maxPerCall()).isEqualTo(12);
  }

  @Test
  public void resolve_highTier_parityAndManyVars() {
    String source =
        "int a,b,c,d,e,f,g,h,x;\nwhile(1){}\nwhile(1){}\nwhile(1){}\n";
    BudgetResolution res =
        budgetResolver().resolve(makePack(source, "(bvand x (_ bv1 32))", 3), 2);
    assertThat(res.tier()).isEqualTo("high");
    assertThat(res.budget().minPerCall()).isEqualTo(8);
    assertThat(res.budget().maxPerCall()).isEqualTo(16);
    assertThat(res.complexityScore()).isAtLeast(7);
  }

  @Test
  public void laterRefinement_increasesScore() {
    String source = "int a,b,c,d,e;\nint i,j;\nwhile(1){}\nwhile(1){}\n";
    BudgetResolution first = budgetResolver().resolve(makePack(source, "i", 2), 1);
    BudgetResolution later = budgetResolver().resolve(makePack(source, "i", 2), 2);
    assertThat(later.complexityScore()).isGreaterThan(first.complexityScore());
  }

  private static PredicateBudgetResolver budgetResolver() {
    return new PredicateBudgetResolver();
  }
}
