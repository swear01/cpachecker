// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-FileCopyrightText: 2026 Dirk Beyer <https://www.sosy-lab.org>
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.core.algorithm.termination.lasso_analysis.vguide;

import static org.sosy_lab.cpachecker.cfa.ast.c.CBinaryExpression.BinaryOperator.BITWISE_AND;
import static org.sosy_lab.cpachecker.cfa.ast.c.CBinaryExpression.BinaryOperator.GREATER_EQUAL;
import static org.sosy_lab.cpachecker.cfa.ast.c.CBinaryExpression.BinaryOperator.LESS_THAN;
import static org.sosy_lab.cpachecker.cfa.ast.c.CBinaryExpression.BinaryOperator.MULTIPLY;
import static org.sosy_lab.cpachecker.cfa.ast.c.CBinaryExpression.BinaryOperator.PLUS;

import java.util.Map;
import org.checkerframework.checker.nullness.qual.Nullable;
import org.sosy_lab.cpachecker.cfa.ast.FileLocation;
import org.sosy_lab.cpachecker.cfa.ast.c.CBinaryExpressionBuilder;
import org.sosy_lab.cpachecker.cfa.ast.c.CExpression;
import org.sosy_lab.cpachecker.cfa.ast.c.CIdExpression;
import org.sosy_lab.cpachecker.cfa.ast.c.CIntegerLiteralExpression;
import org.sosy_lab.cpachecker.cfa.ast.c.CVariableDeclaration;
import org.sosy_lab.cpachecker.cfa.types.c.CNumericTypes;
import org.sosy_lab.cpachecker.core.algorithm.termination.TerminationUtils;
import org.sosy_lab.cpachecker.core.algorithm.termination.lasso_analysis.RankingRelation;
import org.sosy_lab.cpachecker.core.algorithm.termination.lasso_analysis.vguide.RankingTermParser.LinearTerm;
import org.sosy_lab.cpachecker.exceptions.UnrecognizedCodeException;
import org.sosy_lab.cpachecker.util.predicates.smt.FormulaManagerView;
import org.sosy_lab.java_smt.api.BooleanFormula;
import org.sosy_lab.java_smt.api.NumeralFormula.IntegerFormula;

/**
 * Builds a {@link RankingRelation} for a verified linear ranking function, mirroring exactly the
 * primed/unprimed encoding of {@link
 * org.sosy_lab.cpachecker.core.algorithm.termination.lasso_analysis.RankingRelationBuilder}: the
 * relation is {@code f(primed) >= 0 & f(unprimed) < f(primed)} where {@code primed} are the
 * loop-entry snapshot variables ({@code <var>__TERMINATION_PRIMED}) and {@code unprimed} the current
 * variables, i.e. the measure was non-negative and strictly decreased. The optional supporting
 * invariant (already verified inductive) is attached so the TerminationAlgorithm can publish it.
 */
final class RankingRelationFactory {

  private static final String PRIMED_FORMULA_SUFFIX = "__TERMINATION_PRIMED";

  private final FormulaManagerView fmgr;
  private final CBinaryExpressionBuilder cBuilder;
  private final Map<String, CVariableDeclaration> declsByQualifiedName;

  RankingRelationFactory(
      FormulaManagerView pFmgr,
      CBinaryExpressionBuilder pCBuilder,
      Map<String, CVariableDeclaration> pDeclsByQualifiedName) {
    fmgr = pFmgr;
    cBuilder = pCBuilder;
    declsByQualifiedName = pDeclsByQualifiedName;
  }

  /**
   * Returns the ranking relation for {@code f} (and optional supporting invariant), or {@code null}
   * if a C expression could not be built (then the candidate is simply not reported).
   */
  @Nullable
  RankingRelation create(LinearTerm f, BooleanFormula supportingInvariant, boolean hasInvariant) {
    try {
      CExpression cRelation = buildCRelation(f);
      BooleanFormula fRelation = buildFormulaRelation(f);
      RankingRelation rr = new RankingRelation(cRelation, fRelation, cBuilder, fmgr);
      if (hasInvariant) {
        rr = rr.withSupportingInvariants(java.util.List.of(supportingInvariant));
      }
      return rr;
    } catch (UnrecognizedCodeException e) {
      return null;
    }
  }

  // ---- formula side: f(primed) >= 0 & f(unprimed) < f(primed) -----------------

  private BooleanFormula buildFormulaRelation(LinearTerm f) {
    IntegerFormula unprimed = f.toFormula(fmgr.getIntegerFormulaManager(), "");
    IntegerFormula primed = f.toFormula(fmgr.getIntegerFormulaManager(), PRIMED_FORMULA_SUFFIX);
    IntegerFormula zero = fmgr.getIntegerFormulaManager().makeNumber(0);
    BooleanFormula primedNonNegative = fmgr.makeGreaterOrEqual(primed, zero, true);
    BooleanFormula decreases = fmgr.makeLessThan(unprimed, primed, true);
    return fmgr.makeAnd(primedNonNegative, decreases);
  }

  // ---- C-expression side (used to build the assume edges) ---------------------

  private CExpression buildCRelation(LinearTerm f) throws UnrecognizedCodeException {
    CExpression unprimed = buildCTerm(f, false);
    CExpression primed = buildCTerm(f, true);
    CExpression primedNonNegative =
        cBuilder.buildBinaryExpression(primed, intLiteral(0), GREATER_EQUAL);
    CExpression decreases = cBuilder.buildBinaryExpression(unprimed, primed, LESS_THAN);
    return cBuilder.buildBinaryExpression(primedNonNegative, decreases, BITWISE_AND);
  }

  private CExpression buildCTerm(LinearTerm f, boolean primed) throws UnrecognizedCodeException {
    CExpression sum = intLiteral(f.constant());
    for (Map.Entry<String, Long> e : f.coefficients().entrySet()) {
      CVariableDeclaration decl = declsByQualifiedName.get(e.getKey());
      if (decl == null) {
        throw new UnrecognizedCodeException("ranking variable not found: " + e.getKey(), decl);
      }
      CVariableDeclaration useDecl = primed ? TerminationUtils.createPrimedVariable(decl) : decl;
      CExpression var = new CIdExpression(FileLocation.DUMMY, useDecl);
      CExpression summand =
          e.getValue() == 1L
              ? var
              : cBuilder.buildBinaryExpression(intLiteral(e.getValue()), var, MULTIPLY);
      sum = cBuilder.buildBinaryExpression(sum, summand, PLUS);
    }
    return sum;
  }

  private static CExpression intLiteral(long value) {
    return CIntegerLiteralExpression.createDummyLiteral(value, CNumericTypes.LONG_LONG_INT);
  }
}
