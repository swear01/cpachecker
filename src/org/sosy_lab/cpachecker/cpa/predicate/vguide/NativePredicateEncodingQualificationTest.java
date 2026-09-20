// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.collect.Iterables.getOnlyElement;
import static com.google.common.truth.Truth.assertThat;
import static org.junit.Assert.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableMap;
import com.google.common.collect.ImmutableSet;
import java.util.List;
import org.junit.Test;
import org.mockito.ArgumentCaptor;
import org.sosy_lab.common.ShutdownNotifier;
import org.sosy_lab.common.collect.PathCopyingPersistentTreeMap;
import org.sosy_lab.common.configuration.ConfigurationBuilder;
import org.sosy_lab.cpachecker.cfa.CFA;
import org.sosy_lab.cpachecker.cfa.CFACreator;
import org.sosy_lab.cpachecker.cfa.CParser;
import org.sosy_lab.cpachecker.cfa.CProgramScope;
import org.sosy_lab.cpachecker.cfa.ast.AExpression;
import org.sosy_lab.cpachecker.cfa.ast.c.CExpression;
import org.sosy_lab.cpachecker.cfa.ast.c.CExpressionStatement;
import org.sosy_lab.cpachecker.cfa.model.CFANode;
import org.sosy_lab.cpachecker.cfa.model.c.CAssumeEdge;
import org.sosy_lab.cpachecker.core.AnalysisDirection;
import org.sosy_lab.cpachecker.core.algorithm.invariants.InvariantSupplier.TrivialInvariantSupplier;
import org.sosy_lab.cpachecker.core.interfaces.AbstractState;
import org.sosy_lab.cpachecker.core.interfaces.AbstractStateWithLocation;
import org.sosy_lab.cpachecker.core.interfaces.Precision;
import org.sosy_lab.cpachecker.core.reachedset.UnmodifiableReachedSet;
import org.sosy_lab.cpachecker.cpa.arg.ARGReachedSet;
import org.sosy_lab.cpachecker.cpa.automaton.InvalidAutomatonException;
import org.sosy_lab.cpachecker.cpa.composite.CompositeState;
import org.sosy_lab.cpachecker.cpa.predicate.BlockFormulaStrategy.BlockFormulas;
import org.sosy_lab.cpachecker.cpa.predicate.PredicateAbstractState;
import org.sosy_lab.cpachecker.cpa.predicate.PredicateAbstractionManager;
import org.sosy_lab.cpachecker.cpa.predicate.PredicatePrecision;
import org.sosy_lab.cpachecker.exceptions.CParserException;
import org.sosy_lab.cpachecker.util.CFAUtils;
import org.sosy_lab.cpachecker.util.CParserUtils;
import org.sosy_lab.cpachecker.util.expressions.ExpressionTree;
import org.sosy_lab.cpachecker.util.expressions.LeafExpression;
import org.sosy_lab.cpachecker.util.expressions.ToFormulaVisitor;
import org.sosy_lab.cpachecker.util.predicates.AbstractionFormula;
import org.sosy_lab.cpachecker.util.predicates.AbstractionManager;
import org.sosy_lab.cpachecker.util.predicates.pathformula.PathFormula;
import org.sosy_lab.cpachecker.util.predicates.pathformula.PathFormulaManager;
import org.sosy_lab.cpachecker.util.predicates.pathformula.PathFormulaManagerImpl;
import org.sosy_lab.cpachecker.util.predicates.regions.SymbolicRegionManager;
import org.sosy_lab.cpachecker.util.predicates.smt.SolverViewBasedTest0;
import org.sosy_lab.java_smt.SolverContextFactory.Solvers;
import org.sosy_lab.java_smt.api.BooleanFormula;
import org.sosy_lab.java_smt.api.FormulaType;

/** Native C semantics and the production tagged-candidate validation/injection boundary. */
public final class NativePredicateEncodingQualificationTest extends SolverViewBasedTest0 {

  private record Fixture(
      CFA cfa,
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
    return new Fixture(cfa, parser, scope, pfmgr, prefix, condition);
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

  private NativeCExpressionEncoder nativeEncoder(Fixture f) throws Exception {
    return new NativeCExpressionEncoder(
        config, logger, ShutdownNotifier.createDummy(), f.cfa(), f.pfmgr());
  }

  private record LocState(CFANode getLocationNode) implements AbstractStateWithLocation {}

  private AbstractState state(Fixture f, PathFormula path) {
    return new CompositeState(
        ImmutableList.of(
            new LocState(f.condition().getPredecessor()),
            PredicateAbstractState.mkAbstractionState(
                path, mock(AbstractionFormula.class), PathCopyingPersistentTreeMap.of())));
  }

  private ContextPack pack(Fixture f, PathFormula... paths) {
    var head = f.condition().getPredecessor();
    return new ContextPack(
        1,
        "",
        "",
        ImmutableList.of(new LoopHeadInfo(head, "", head.getFunctionName())),
        ImmutableMap.of(),
        ImmutableSet.copyOf(mgrv.extractVariableNames(paths[paths.length - 1].getFormula())),
        new BlockFormulas(
            java.util.Arrays.stream(paths)
                .map(PathFormula::getFormula)
                .collect(ImmutableList.toImmutableList())),
        ImmutableList.of(),
        "",
        "");
  }

  private List<LoopHeadCandidate> response(Fixture f, String predicate) {
    var parsed =
        LoopHeadCandidateParser.parseWithRejects(
            "{\"schema_version\":\"loop-head-candidate-v1\",\"candidates\":[{\"loop_head\":\"N"
                + f.condition().getPredecessor().getNodeNumber()
                + "\",\"predicate\":\""
                + predicate
                + "\"}]}");
    assertThat(parsed.rejected()).isEmpty();
    return parsed.accepted();
  }

  @Test
  public void strictParserRejectsEffectsAndPreprocessingBeforeConversion() throws Exception {
    Fixture f = fixture("int main(void) { int x=0; if(x<3) return 0; return 1; }");
    assertThat(f.parser().parsePureExpression("x < 3", f.scope())).isNotNull();
    for (String text :
        List.of(
            "x++",
            "++x",
            "x = 2",
            "x += 1",
            "0 && ++x",
            "x<3 && x>0",
            "x<3 || x>0",
            "x ? 1 : 2",
            "f(x)",
            "({ x; })",
            "x); x++; (x",
            "x; x",
            "",
            "x\n#define BAD 1\n",
            "x\n%:include \"/dev/null\"\n")) {
      assertThrows(
          text, CParserException.class, () -> f.parser().parsePureExpression(text, f.scope()));
    }
  }

  @Test
  public void nativeFailuresAreObservableAndDoNotDiscardAcceptedPrimary() throws Exception {
    Fixture f = fixture("int main(void){int a[4]; int x=0; a[x]=7; while(x<3){x++;}return 0;}");
    var pipeline = new PredicateValidationPipeline(logger, solver, mgrv, false, nativeEncoder(f));
    var trace = List.of(state(f, f.prefix()));
    var context = pack(f, f.prefix());
    var primary = pipeline.validateCandidates(context, response(f, "c: x<3"), trace);
    assertThat(primary.rejections()).isEmpty();
    assertThat(primary.validation().validated()).hasSize(1);
    for (String text : List.of("c: x++", "c: f(x)", "c: (bvsle x (_ bv3 32))", "c: missing<3")) {
      var outcome = pipeline.validateCandidates(context, response(f, text), trace, primary);
      assertThat(outcome.validation().validated())
          .containsExactlyElementsIn(primary.validation().validated());
      assertThat(getOnlyElement(outcome.rejections()).reason()).isEqualTo("native_c_rejected");
      assertThat(getOnlyElement(outcome.rejections()).predicate()).isEqualTo(text);
    }
    var encoder = nativeEncoder(f);
    var head = f.condition().getPredecessor();
    var empty = f.pfmgr().makeEmptyPathFormula();
    assertThrows(IllegalArgumentException.class, () -> encoder.encode("a[x] < 3", head, empty));
  }

  @Test
  public void taggedArrayResponseReachesNativePrecisionWithoutTraceTemplate() throws Exception {
    Fixture f =
        fixture(
            "int main(void) { int a[4]; int x=0; x=x+1; a[x]=7; while(a[x]<=a[x+1]) { x=x+1; }"
                + " return 0; }");
    var pipeline = new PredicateValidationPipeline(logger, solver, mgrv, false, nativeEncoder(f));
    var outcome =
        pipeline.validateCandidates(
            pack(f, f.prefix()), response(f, "c: a[x] <= a[x+1]"), List.of(state(f, f.prefix())));
    assertThat(outcome.rejections()).isEmpty();
    var validated = getOnlyElement(outcome.validation().validated());
    assertMatchesCfa(f, mgrv.uninstantiate(validated.formula()));
    assertThat(outcome.rawStrings().get(validated)).isEqualTo("c: a[x] <= a[x+1]");
    assertThat(validated.classification())
        .isEqualTo(ValidatedPredicate.Classification.PRECISION_ONLY);

    var amgr = new AbstractionManager(new SymbolicRegionManager(solver), config, logger, solver);
    var predmgr =
        new PredicateAbstractionManager(
            amgr,
            f.pfmgr(),
            solver,
            config,
            logger,
            ShutdownNotifier.createDummy(),
            TrivialInvariantSupplier.INSTANCE);
    var reached = mock(ARGReachedSet.class);
    var view = mock(UnmodifiableReachedSet.class);
    when(reached.asReachedSet()).thenReturn(view);
    when(view.getPrecisions()).thenReturn(ImmutableList.of());
    assertThat(
            new LoopHeadPrecisionInjector(logger, predmgr)
                .inject(reached, outcome.validation().validated(), false))
        .isTrue();
    ArgumentCaptor<Precision> precision = ArgumentCaptor.forClass(Precision.class);
    verify(reached).updatePrecisionGlobally(precision.capture(), any());
    var inserted =
        getOnlyElement(
            ((PredicatePrecision) precision.getValue())
                .getLocalPredicates()
                .get(validated.loopHeadNode()));
    assertThat(inserted.getSymbolicAtom()).isEqualTo(mgrv.uninstantiate(validated.formula()));
  }

  @Test
  public void taggedCandidatesRejectUnknownExpiredForeignAndAmbiguousDeclarations()
      throws Exception {
    Fixture f =
        fixture(
            "int other(void){int y=1;return y;} int main(void){{int gone=1;} int x=0; if(x<3)return"
                + " 0;return 1;}");
    var encoder = nativeEncoder(f);
    for (String text : List.of("missing < 1", "gone < 1", "y < 1")) {
      assertThrows(
          text,
          IllegalArgumentException.class,
          () -> encoder.encode(text, f.condition().getPredecessor(), f.prefix()));
    }
    Fixture shadow = fixture("int main(void){int x=1; {int x=2; if(x<3)return 0;} return 1;}");
    var shadowEncoder = nativeEncoder(shadow);
    var shadowHead = shadow.condition().getPredecessor();
    var shadowContext = shadow.prefix();
    assertThrows(
        IllegalArgumentException.class,
        () -> shadowEncoder.encode("x<3", shadowHead, shadowContext));
    Fixture global =
        fixture("int s; int main(void){int s=-1; unsigned int u=1; if(s<u)return 0;return 1;}");
    assertMatchesCfa(
        global,
        mgrv.uninstantiate(
            nativeEncoder(global)
                .encode("s<u", global.condition().getPredecessor(), global.prefix())));
  }

  @Test
  public void nativeContextUsesLastAlignedOccurrenceAndNeverEarlierFallback() throws Exception {
    Fixture f = fixture("int main(void){int x=0; while(x<3){x=x+1;}return 0;}");
    PathFormula next = f.pfmgr().makeAnd(f.prefix(), f.condition());
    var node = f.condition().getSuccessor();
    for (int steps = 0; node != f.condition().getPredecessor(); steps++) {
      assertThat(steps).isLessThan(20);
      assertThat(node.getNumLeavingEdges()).isEqualTo(1);
      var edge = node.getLeavingEdge(0);
      next = f.pfmgr().makeAnd(next, edge);
      node = edge.getSuccessor();
    }
    assertThat(next.getSsa().getIndex("main::x"))
        .isGreaterThan(f.prefix().getSsa().getIndex("main::x"));
    var pipeline = new PredicateValidationPipeline(logger, solver, mgrv, false, nativeEncoder(f));
    var response = response(f, "c: x < 3");
    var outcome =
        pipeline.validateCandidates(
            pack(f, f.prefix(), next), response, List.of(state(f, f.prefix()), state(f, next)));
    assertThat(outcome.rejections()).isEmpty();
    assertThat(
            mgrv.extractVariableNames(getOnlyElement(outcome.validation().validated()).formula()))
        .containsExactly("main::x@" + next.getSsa().getIndex("main::x"));
    var missing =
        pipeline.validateCandidates(
            pack(f, f.prefix(), next), response, List.of(state(f, f.prefix()), new LocState(node)));
    assertThat(missing.validation().validated()).isEmpty();
    assertThat(getOnlyElement(missing.rejections()).reason())
        .isEqualTo("native_c_context_unavailable");
  }
}
