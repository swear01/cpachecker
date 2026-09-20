// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.collect.Iterables.getOnlyElement;
import static com.google.common.truth.Truth.assertThat;
import static org.junit.Assert.assertThrows;

import org.junit.Test;
import org.sosy_lab.common.ShutdownNotifier;
import org.sosy_lab.common.configuration.ConfigurationBuilder;
import org.sosy_lab.cpachecker.cfa.CFACreator;
import org.sosy_lab.cpachecker.cfa.CParser;
import org.sosy_lab.cpachecker.cfa.CProgramScope;
import org.sosy_lab.cpachecker.cfa.ast.AExpression;
import org.sosy_lab.cpachecker.cfa.ast.c.CExpression;
import org.sosy_lab.cpachecker.cfa.ast.c.CExpressionStatement;
import org.sosy_lab.cpachecker.cfa.model.c.CAssumeEdge;
import org.sosy_lab.cpachecker.core.AnalysisDirection;
import org.sosy_lab.cpachecker.cpa.automaton.InvalidAutomatonException;
import org.sosy_lab.cpachecker.util.CFAUtils;
import org.sosy_lab.cpachecker.util.CParserUtils;
import org.sosy_lab.cpachecker.util.expressions.ExpressionTree;
import org.sosy_lab.cpachecker.util.expressions.LeafExpression;
import org.sosy_lab.cpachecker.util.expressions.ToFormulaVisitor;
import org.sosy_lab.cpachecker.util.predicates.pathformula.PathFormula;
import org.sosy_lab.cpachecker.util.predicates.pathformula.PathFormulaManager;
import org.sosy_lab.cpachecker.util.predicates.pathformula.PathFormulaManagerImpl;
import org.sosy_lab.cpachecker.util.predicates.smt.SolverViewBasedTest0;
import org.sosy_lab.java_smt.SolverContextFactory.Solvers;
import org.sosy_lab.java_smt.api.BooleanFormula;
import org.sosy_lab.java_smt.api.FormulaType;

/** Native encoding qualification, not an alternative production VGuide input contract. */
public final class NativePredicateEncodingQualificationTest extends SolverViewBasedTest0 {

  private record Fixture(
      CParser parser,
      CProgramScope scope,
      PathFormulaManager pfmgr,
      PathFormula prefix,
      CAssumeEdge condition) {}

  @Override
  protected Solvers solverToUse() {
    return Solvers.MATHSAT5;
  }

  @Override
  protected ConfigurationBuilder createTestConfigBuilder() {
    return super.createTestConfigBuilder()
        .setOption("analysis.machineModel", "Linux32")
        .setOption("cfa.export", "false")
        .setOption("cfa.exportPerFunction", "false")
        .setOption("cfa.callgraph.export", "false");
  }

  private Fixture fixture(String program) throws Exception {
    var shutdown = ShutdownNotifier.createDummy();
    var cfa = new CFACreator(config, logger, shutdown).parseSourceAndCreateCFA(program);
    var parser =
        CParser.Factory.getParser(
            logger, CParser.Factory.getDefaultOptions(), cfa.getMachineModel(), shutdown);
    var scope = new CProgramScope(cfa, logger).withFunctionScope("main");
    PathFormulaManager pfmgr =
        new PathFormulaManagerImpl(mgrv, config, logger, shutdown, cfa, AnalysisDirection.FORWARD);
    CAssumeEdge condition =
        cfa.edges().stream()
            .filter(e -> e instanceof CAssumeEdge a && a.getTruthAssumption())
            .map(e -> (CAssumeEdge) e)
            .findFirst()
            .orElseThrow();
    PathFormula prefix = pfmgr.makeEmptyPathFormula();
    var node = cfa.getMainFunction();
    org.sosy_lab.cpachecker.cfa.model.CFANode current = node;
    int steps = 0;
    while (current != condition.getPredecessor()) {
      assertThat(++steps).isAtMost(32);
      assertThat(current.getNumLeavingEdges()).isEqualTo(1);
      var edge = current.getLeavingEdge(0);
      prefix = pfmgr.makeAnd(prefix, edge);
      current = edge.getSuccessor();
    }
    return new Fixture(parser, scope, pfmgr, prefix, condition);
  }

  private CExpression parseExpression(Fixture f, String text) throws Exception {
    var statement = CParserUtils.parseSingleStatement(text, f.parser(), f.scope());
    assertThat(statement).isInstanceOf(CExpressionStatement.class);
    return ((CExpressionStatement) statement).getExpression();
  }

  private BooleanFormula encode(Fixture f, String text) throws Exception {
    ExpressionTree<AExpression> tree = LeafExpression.of(parseExpression(f, text));
    return tree.accept(new ToFormulaVisitor(mgrv, f.pfmgr(), f.prefix()));
  }

  private void assertMatchesCfa(Fixture f, BooleanFormula candidate) throws Exception {
    var clear = f.pfmgr().makeEmptyPathFormulaWithContextFrom(f.prefix());
    BooleanFormula nativeFormula =
        mgrv.uninstantiate(f.pfmgr().makeAnd(clear, f.condition()).getFormula());
    assertThat(solver.isUnsat(bmgrv.xor(candidate, nativeFormula))).isTrue();
    assertThat(solver.isUnsat(candidate)).isFalse();
    assertThat(solver.isUnsat(bmgrv.not(candidate))).isFalse();
  }

  @Test
  public void arrayReadRetainsActualHeapBaseAndNonDefaultSsa() throws Exception {
    Fixture f =
        fixture(
            """
            int main(void) {
              int a[4]; int x = 0;
              x = x + 1; a[x] = 7;
              if (a[x] <= a[x + 1]) return 0;
              return 1;
            }
            """);
    assertThat(f.prefix().getSsa().getIndex("main::x")).isGreaterThan(1);
    assertThat(f.prefix().getPointerTargetSet().getBases()).isNotEmpty();
    BooleanFormula candidate = encode(f, "a[x] <= a[x + 1]");
    assertMatchesCfa(f, candidate);
    assertThat(mgrv.extractVariableNames(candidate))
        .containsExactly("main::x", "__ADDRESS_OF_main::a@", "*int");
    var instantiated = mgrv.instantiate(candidate, f.prefix().getSsa());
    assertThat(mgrv.extractVariableNames(instantiated))
        .containsExactly(
            "main::x@" + f.prefix().getSsa().getIndex("main::x"),
            "__ADDRESS_OF_main::a@",
            "*int@" + f.prefix().getSsa().getIndex("*int"));
    BooleanFormula roundTrip = mgrv.parse(mgrv.dumpFormula(instantiated).toString());
    assertThat(solver.isUnsat(bmgrv.xor(instantiated, roundTrip))).isTrue();
  }

  @Test
  public void sourcePromotionsAndLocalShadowingUseActualDeclarations() throws Exception {
    Fixture f =
        fixture(
            """
            int s;
            int main(void) {
              int s = -1; unsigned int u = 1;
              if (s < u) return 0;
              return 1;
            }
            """);
    var expression = parseExpression(f, "s < u");
    var declaration = f.scope().lookupVariable("s");
    assertThat(declaration).isNotNull();
    String localName = declaration.getQualifiedName();
    assertThat(localName).startsWith("main::s");
    for (var id : CFAUtils.getIdExpressionsOfExpression(expression)) {
      assertThat(id.getDeclaration()).isNotNull();
    }
    assertThat(
            CFAUtils.getIdExpressionsOfExpression(expression)
                .transform(id -> id.getDeclaration().getQualifiedName()))
        .containsExactly(localName, "main::u");
    BooleanFormula candidate = encode(f, "s < u");
    assertMatchesCfa(f, candidate);
    var bitvectors = mgrv.getBitvectorFormulaManager();
    var s = bitvectors.makeVariable(32, localName);
    var u = bitvectors.makeVariable(32, "main::u");
    BooleanFormula values =
        bmgrv.and(
            bitvectors.equal(s, bitvectors.makeBitvector(32, -1)),
            bitvectors.equal(u, bitvectors.makeBitvector(32, 1)));
    assertThat(solver.isUnsat(bmgrv.and(values, candidate))).isTrue();
    assertThat(solver.isUnsat(bmgrv.and(values, bitvectors.lessThan(s, u, true)))).isFalse();
  }

  @Test
  public void narrowCarrierPromotesWithoutInventingThirtyTwoBitVariable() throws Exception {
    Fixture f =
        fixture(
            """
            int main(void) {
              unsigned char c = 0;
              if (c < 255) return 0;
              return 1;
            }
            """);
    BooleanFormula candidate = encode(f, "c < 255");
    assertMatchesCfa(f, candidate);
    var variables = mgrv.extractVariables(candidate);
    assertThat(variables).containsKey("main::c");
    assertThat(mgrv.getFormulaType(variables.get("main::c")))
        .isEqualTo(FormulaType.getBitvectorTypeWithSize(8));
    var bitvectors = mgrv.getBitvectorFormulaManager();
    var c = bitvectors.makeVariable(8, "main::c");
    assertThat(
            solver.isUnsat(
                bmgrv.and(candidate, bitvectors.equal(c, bitvectors.makeBitvector(8, 255)))))
        .isTrue();
    assertThat(
            solver.isUnsat(
                bmgrv.and(candidate, bitvectors.equal(c, bitvectors.makeBitvector(8, 128)))))
        .isFalse();
  }

  @Test
  public void parsingDoesNotReplaceProposalBoundaryValidation() throws Exception {
    Fixture f = fixture("int main(void) { int x = 0; if (x < 3) return 0; return 1; }");
    assertThrows(
        InvalidAutomatonException.class,
        () ->
            CParserUtils.parseSingleStatement(
                "(bvsle a[x] a[(bvadd x (_ bv1 32))])", f.parser(), f.scope()));
    assertThat(CParserUtils.parseSingleStatement("x = x + 1", f.parser(), f.scope()))
        .isNotInstanceOf(CExpressionStatement.class);
    // A statement-kind check alone cannot certify a side-effect-free, declared predicate.
    assertThat(parseExpression(f, "x++").toASTString()).contains("__CPAchecker_TMP_");
    var unknown = parseExpression(f, "unknown_name < 1");
    assertThat(getOnlyElement(CFAUtils.getIdExpressionsOfExpression(unknown)).getDeclaration())
        .isNull();
    assertThrows(
        IllegalArgumentException.class,
        () ->
            mgrv.parse(
                "(declare-fun badwidth () (_ BitVec 8))" + " (assert (= badwidth (_ bv0 32)))"));
  }
}
