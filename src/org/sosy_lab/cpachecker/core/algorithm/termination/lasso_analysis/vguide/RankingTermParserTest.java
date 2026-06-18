// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-FileCopyrightText: 2026 Dirk Beyer <https://www.sosy-lab.org>
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.core.algorithm.termination.lasso_analysis.vguide;

import static com.google.common.truth.Truth.assertThat;

import com.google.common.collect.ImmutableMap;
import org.junit.Before;
import org.junit.Test;
import org.sosy_lab.cpachecker.util.predicates.smt.SolverViewBasedTest0;
import org.sosy_lab.java_smt.SolverContextFactory.Solvers;
import org.sosy_lab.java_smt.api.BooleanFormula;
import org.sosy_lab.java_smt.api.NumeralFormula.IntegerFormula;

/** Unit tests for {@link RankingTermParser}: grammar coverage and rejection of unsupported forms. */
public class RankingTermParserTest extends SolverViewBasedTest0 {

  @Override
  protected Solvers solverToUse() {
    return Solvers.SMTINTERPOL;
  }

  private RankingTermParser parser;

  @Before
  public void setUpParser() {
    parser =
        new RankingTermParser(
            mgrv, ImmutableMap.of("i", "i", "n", "n", "x", "x", "y", "y"));
  }

  private IntegerFormula v(String name) {
    return imgrv.makeVariable(name);
  }

  private void assertTermEquiv(IntegerFormula actual, IntegerFormula expected) throws Exception {
    assertThat(actual).isNotNull();
    assertThat(solver.isUnsat(bmgrv.not(imgrv.equal(actual, expected)))).isTrue();
  }

  private void assertBoolEquiv(BooleanFormula actual, BooleanFormula expected) throws Exception {
    assertThat(actual).isNotNull();
    assertThat(solver.isUnsat(bmgrv.not(bmgrv.equivalence(actual, expected)))).isTrue();
  }

  // ---- terms ------------------------------------------------------------------

  @Test
  public void parsesSubtraction() throws Exception {
    assertTermEquiv(parser.parseTerm("(- n i)"), imgrv.subtract(v("n"), v("i")));
  }

  @Test
  public void parsesLinearCombination() throws Exception {
    assertTermEquiv(
        parser.parseTerm("(+ (* 2 x) y)"),
        imgrv.add(imgrv.multiply(imgrv.makeNumber(2), v("x")), v("y")));
  }

  @Test
  public void parsesUnaryNegation() throws Exception {
    assertTermEquiv(parser.parseTerm("(- i)"), imgrv.negate(v("i")));
  }

  @Test
  public void rejectsNonlinearProduct() {
    assertThat(parser.parseTerm("(* x y)")).isNull();
  }

  @Test
  public void rejectsUnknownVariable() {
    assertThat(parser.parseTerm("(- z i)")).isNull();
  }

  @Test
  public void rejectsUnbalancedParens() {
    assertThat(parser.parseTerm("(- n i")).isNull();
    assertThat(parser.parseTerm("(- n i))")).isNull();
  }

  // ---- invariants -------------------------------------------------------------

  @Test
  public void emptyOrTrueInvariantIsTrue() throws Exception {
    assertBoolEquiv(parser.parseInvariant(null), bmgrv.makeTrue());
    assertBoolEquiv(parser.parseInvariant(""), bmgrv.makeTrue());
    assertBoolEquiv(parser.parseInvariant("true"), bmgrv.makeTrue());
  }

  @Test
  public void parsesGreaterEqual() throws Exception {
    // (>= y 1) encoded as !(y < 1)
    assertBoolEquiv(
        parser.parseInvariant("(>= y 1)"), bmgrv.not(imgrv.lessThan(v("y"), imgrv.makeNumber(1))));
  }

  @Test
  public void parsesConjunctionOfRelations() throws Exception {
    BooleanFormula expected =
        bmgrv.and(
            bmgrv.not(imgrv.lessThan(v("y"), imgrv.makeNumber(1))), imgrv.lessThan(v("i"), v("n")));
    assertBoolEquiv(parser.parseInvariant("(and (>= y 1) (< i n))"), expected);
  }

  @Test
  public void rejectsNonlinearInsideInvariant() {
    assertThat(parser.parseInvariant("(>= y (* x x))")).isNull();
  }
}
