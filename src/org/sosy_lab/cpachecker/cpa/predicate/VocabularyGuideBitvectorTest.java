// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-FileCopyrightText: 2007-2020 Dirk Beyer <https://www.sosy-lab.org>
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate;

import static com.google.common.truth.Truth.assertThat;

import java.util.List;
import java.util.Set;
import org.junit.Test;
import org.sosy_lab.cpachecker.util.predicates.smt.FormulaManagerView;
import org.sosy_lab.cpachecker.util.predicates.smt.SolverViewBasedTest0;
import org.sosy_lab.java_smt.api.BooleanFormula;

public class VocabularyGuideBitvectorTest extends SolverViewBasedTest0 {
  @Override
  protected org.sosy_lab.java_smt.SolverContextFactory.Solvers solverToUse() {
    return org.sosy_lab.java_smt.SolverContextFactory.Solvers.MATHSAT5;
  }

  @Test
  public void preservesEveryOperandOfChainableAndAssociativeOperators() throws Exception {
    for (String expression :
        List.of(
            "(= #x01 #x01 #x02)",
            "(= (bvadd #x01 #x02 #x03) #x06)",
            "(= (bvmul #x02 #x03 #x04) #x18)")) {
      BooleanFormula formula = parse(expression, mgrv);
      assertThat(formula).isNotNull();
      boolean expected = !expression.equals("(= #x01 #x01 #x02)");
      assertThat(solver.isUnsat(expected ? bmgrv.not(formula) : formula)).isTrue();
    }
  }

  @Test
  public void bitvectorNegationPreservesOperandWidth() throws Exception {
    for (String value : List.of("#x80", "#x8000", "#x8000000000000000")) {
      BooleanFormula formula = parse("(= (bvneg " + value + ") " + value + ")", mgrv);
      assertThat(formula).isNotNull();
      assertThat(solver.isUnsat(bmgrv.not(formula))).isTrue();
    }
  }

  @Test
  public void rejectsExtraOrMissingOperandsInsteadOfTruncating() {
    for (String expression :
        List.of(
            "(bvslt x y z)",
            "(not (= x y) (= x z))",
            "(= (bvsub x y z) x)",
            "(= (bvshl x y z) x)",
            "(= (bvneg x y) x)",
            "(= ((_ extract 7 0) x y) #x00)",
            "(= ((_ sign_extend 8) #x00 #x01) #x0000)",
            "(= x)",
            "(and)",
            "(= (bvadd x) x)",
            "(= (select heap i j) x)")) {
      assertThat(parse(expression, mgrv)).isNull();
    }
  }

  private static BooleanFormula parse(String expression, FormulaManagerView fmgr) {
    return VocabularyGuide.parsePredicate(expression, fmgr, Set.of());
  }
}
