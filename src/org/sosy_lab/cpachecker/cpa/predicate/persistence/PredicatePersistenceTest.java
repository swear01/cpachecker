// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-FileCopyrightText: 2007-2020 Dirk Beyer <https://www.sosy-lab.org>
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.persistence;

import static com.google.common.truth.Truth.assertThat;
import static com.google.common.truth.Truth.assertWithMessage;
import static org.junit.Assert.assertThrows;

import com.google.common.base.CharMatcher;
import com.google.common.base.Splitter;
import java.io.BufferedReader;
import java.io.StringReader;
import java.util.List;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.junit.runners.Parameterized;
import org.junit.runners.Parameterized.Parameter;
import org.junit.runners.Parameterized.Parameters;
import org.sosy_lab.common.configuration.Configuration;
import org.sosy_lab.cpachecker.cfa.ImmutableCFA;
import org.sosy_lab.cpachecker.cfa.model.CFANode;
import org.sosy_lab.cpachecker.cpa.predicate.PredicatePrecision;
import org.sosy_lab.cpachecker.cpa.predicate.PredicatePrecisionBootstrapper;
import org.sosy_lab.cpachecker.util.Pair;
import org.sosy_lab.cpachecker.util.predicates.AbstractionManager;
import org.sosy_lab.cpachecker.util.predicates.regions.SymbolicRegionManager;
import org.sosy_lab.cpachecker.util.predicates.smt.SolverViewBasedTest0;
import org.sosy_lab.cpachecker.util.test.TestDataTools;
import org.sosy_lab.java_smt.SolverContextFactory.Solvers;
import org.sosy_lab.java_smt.api.BooleanFormula;

@RunWith(Parameterized.class)
public class PredicatePersistenceTest extends SolverViewBasedTest0 {

  @Parameters(name = "{0}")
  public static Solvers[] getAllSolvers() {
    return Solvers.values();
  }

  @Parameter(0)
  public Solvers solverToUse;

  @Override
  protected Solvers solverToUse() {
    return solverToUse;
  }

  @Test
  public void testSplitFormula_Syntactically() {
    requireIntegers();

    BooleanFormula f1 =
        imgr.equal(imgr.makeVariable("variable_with_long_name"), imgr.makeNumber(1));
    BooleanFormula f2 =
        imgr.equal(
            imgr.makeVariable("variable_with_long_name2"),
            imgr.makeVariable("variable_with_long_name"));
    BooleanFormula f = bmgr.and(f1, f2);

    Pair<String, List<String>> result = PredicatePersistenceUtils.splitFormula(mgrv, f);
    String assertFormula = result.getFirst();
    List<String> declarationFormulas = result.getSecond();

    assertThat(assertFormula).startsWith("(assert ");
    assertThat(assertFormula).endsWith(")");
    assertThat(assertFormula).doesNotContain("\n");

    assertThatAllParenthesesAreClosed(assertFormula);

    for (String declaration : declarationFormulas) {
      String statement = Splitter.on(' ').split(declaration).iterator().next();
      assertWithMessage("Statement of %s", declaration)
          .that(statement)
          .isAnyOf("(define-fun", "(declare-fun", "(set-info", "(set-logic");

      assertThat(declaration).endsWith(")");
      assertThatAllParenthesesAreClosed(declaration);
    }
  }

  @Test
  public void testPredicateMapAcceptedRejectedAndPlacedByScope() throws Exception {
    ImmutableCFA cfa = TestDataTools.makeCFA("int main() { int x; x = 0; }");
    Configuration config = TestDataTools.configurationForTest().build();
    AbstractionManager amgr =
        new AbstractionManager(new SymbolicRegionManager(solver), config, logger, solver);
    PredicatePrecisionBootstrapper.InitialPredicatesOptions options =
        new PredicatePrecisionBootstrapper.InitialPredicatesOptions();
    PredicateMapParser parser =
        new PredicateMapParser(cfa, logger, mgrv, amgr, options);
    CFANode localNode =
        cfa.nodes().stream()
            .filter(node -> node.getFunctionName().equals("main"))
            .filter(node -> node != cfa.getMainFunction())
            .findFirst()
            .orElseThrow();

    String map =
        "(declare-fun x () Int)\n\n"
            + "*:\n(assert (= x 0))\n\n"
            + "main:\n(assert (= x 1))\n\n"
            + "main N"
            + localNode.getNodeNumber()
            + ":\n(assert (= x 2))\n";
    PredicatePrecision precision =
        parser.parsePredicates(new BufferedReader(new StringReader(map)), "accepted.predmap");

    assertThat(precision.getGlobalPredicates()).hasSize(1);
    assertThat(precision.getFunctionPredicates().get("main")).hasSize(2);
    assertThat(precision.getLocalPredicates().get(localNode)).hasSize(3);
    assertThat(precision.getPredicates(localNode, 1)).hasSize(3);

    String malformed = "(declare-fun x () Int)\n\nnot-a-key:\n(assert (= x 0))\n";
    assertThrows(
        PredicatePersistenceUtils.PredicateParsingFailedException.class,
        () -> parser.parsePredicates(new BufferedReader(new StringReader(malformed)), "rejected"));
  }

  private void assertThatAllParenthesesAreClosed(String formula) {
    assertWithMessage("number of closing parentheses")
        .that(CharMatcher.anyOf(")").countIn(formula))
        .isEqualTo(CharMatcher.anyOf("(").countIn(formula));
  }
}
