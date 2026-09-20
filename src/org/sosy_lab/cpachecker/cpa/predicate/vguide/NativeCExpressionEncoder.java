// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import java.util.List;
import org.sosy_lab.common.ShutdownNotifier;
import org.sosy_lab.common.configuration.Configuration;
import org.sosy_lab.common.configuration.InvalidConfigurationException;
import org.sosy_lab.common.log.LogManager;
import org.sosy_lab.cpachecker.cfa.CFA;
import org.sosy_lab.cpachecker.cfa.CParser;
import org.sosy_lab.cpachecker.cfa.CProgramScope;
import org.sosy_lab.cpachecker.cfa.ast.AbstractSimpleDeclaration;
import org.sosy_lab.cpachecker.cfa.ast.c.CVariableDeclaration;
import org.sosy_lab.cpachecker.cfa.model.CFANode;
import org.sosy_lab.cpachecker.exceptions.CPATransferException;
import org.sosy_lab.cpachecker.exceptions.CParserException;
import org.sosy_lab.cpachecker.util.CFAUtils;
import org.sosy_lab.cpachecker.util.predicates.pathformula.PathFormula;
import org.sosy_lab.cpachecker.util.predicates.pathformula.PathFormulaManager;
import org.sosy_lab.java_smt.api.BooleanFormula;

/** Encode explicitly tagged source C using the analysis' own types, SSA, and memory model. */
final class NativeCExpressionEncoder {
  static final String PREFIX = "c:";

  private final CFA cfa;
  private final CParser parser;
  private final CProgramScope scope;
  private final PathFormulaManager pfmgr;

  NativeCExpressionEncoder(
      Configuration config,
      LogManager logger,
      ShutdownNotifier shutdown,
      CFA pCfa,
      PathFormulaManager pPfmgr)
      throws InvalidConfigurationException {
    cfa = pCfa;
    pfmgr = pPfmgr;
    parser =
        CParser.Factory.getParser(
            logger, CParser.Factory.getOptions(config), cfa.getMachineModel(), shutdown);
    scope = new CProgramScope(cfa, logger);
  }

  BooleanFormula encode(String text, CFANode head, PathFormula context)
      throws CParserException, CPATransferException, InterruptedException {
    var relation = cfa.getAstCfaRelation();
    if (relation == null) {
      throw new IllegalArgumentException("native C scope unavailable");
    }
    var visible =
        relation
            .getVariablesAndParametersInScope(head)
            .orElseThrow(() -> new IllegalArgumentException("native C scope unavailable"));
    var expression =
        parser.parsePureExpression(text, scope.withFunctionScope(head.getFunctionName()));
    for (var id : CFAUtils.getIdExpressionsOfExpression(expression)) {
      var declaration = id.getDeclaration();
      if (declaration == null || !id.getName().equals(declaration.getName())) {
        throw new IllegalArgumentException("unresolved C identifier: " + id.getName());
      }
      List<AbstractSimpleDeclaration> matches =
          visible.stream().filter(d -> d.getOrigName().equals(declaration.getOrigName())).toList();
      var locals =
          matches.stream()
              .filter(d -> !(d instanceof CVariableDeclaration v && v.isGlobal()))
              .toList();
      if (!locals.isEmpty()) {
        matches = locals;
      }
      // ponytail: scope snapshots lack shadowing order; reject ambiguous locals rather than guess.
      if (matches.size() != 1 || !matches.getFirst().equals(declaration)) {
        throw new IllegalArgumentException(
            "C identifier is unavailable or ambiguous at head: " + id.getName());
      }
    }
    PathFormula encoded =
        pfmgr.makeAnd(pfmgr.makeEmptyPathFormulaWithContextFrom(context), expression);
    if (!encoded.getSsa().equals(context.getSsa())
        || !encoded.getPointerTargetSet().equals(context.getPointerTargetSet())) {
      throw new IllegalArgumentException(
          "C predicate requires state absent from the selected trace occurrence");
    }
    return encoded.getFormula();
  }
}
