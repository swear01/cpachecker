// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import java.util.LinkedHashSet;
import java.util.Set;
import java.util.regex.Pattern;

/** Maps spurious CE context to per-call predicate min/max (see ADAPTIVE_PREDICATE_BUDGET_PLAN). */
public final class PredicateBudgetResolver {

  private static final Pattern NESTED_ASSERT =
      Pattern.compile("bvand|bvurem|bvmul", Pattern.CASE_INSENSITIVE);

  public BudgetResolution resolve(ContextPack pack, int refinementIndex) {
    int score = complexityScore(pack, refinementIndex);
    String tier;
    PredicateBudget budget;
    if (score <= 3) {
      tier = "low";
      budget = new PredicateBudget(4, 8);
    } else if (score <= 6) {
      tier = "medium";
      budget = new PredicateBudget(6, 12);
    } else {
      tier = "high";
      budget = new PredicateBudget(8, 16);
    }
    return new BudgetResolution(budget, tier, score);
  }

  /** Worst-case budget for dump size estimates (high tier). */
  public static PredicateBudget worstCaseBudget() {
    return new PredicateBudget(8, 16);
  }

  private static int complexityScore(ContextPack pack, int refinementIndex) {
    int score = 0;
    int loopHeads = pack.loopHeads().size();
    score += Math.min(3, loopHeads);

    String assertion = pack.assertion();
    if (!assertion.isEmpty() && NESTED_ASSERT.matcher(assertion).find()) {
      score += 2;
    }

    int varCount = scalarVarCount(pack);
    if (varCount >= 5) {
      score += 1;
    }
    if (varCount >= 8) {
      score += 1;
    }

    if (SourceVariableHints.hasArrayDecl(pack.sourceCode())) {
      score += 1;
    }

    if (refinementIndex > 1) {
      score += 1;
    }
    return score;
  }

  private static int scalarVarCount(ContextPack pack) {
    if (!pack.varContract().isEmpty()) {
      Set<String> names = new LinkedHashSet<>();
      pack.varContract().values().forEach(names::addAll);
      return names.size();
    }
    return SourceVariableHints.scalarDeclCount(pack.sourceCode());
  }
}
