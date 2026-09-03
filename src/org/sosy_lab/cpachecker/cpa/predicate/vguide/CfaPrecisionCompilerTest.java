// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.truth.Truth.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.google.common.collect.ImmutableList;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.Before;
import org.junit.Test;
import org.sosy_lab.common.ShutdownNotifier;
import org.sosy_lab.common.configuration.Configuration;
import org.sosy_lab.cpachecker.cfa.CFA;
import org.sosy_lab.cpachecker.cfa.Language;
import org.sosy_lab.cpachecker.cfa.model.CFAEdge;
import org.sosy_lab.cpachecker.cfa.model.CFANode;
import org.sosy_lab.cpachecker.cfa.model.c.CAssumeEdge;
import org.sosy_lab.cpachecker.cfa.types.MachineModel;
import org.sosy_lab.cpachecker.core.AnalysisDirection;
import org.sosy_lab.cpachecker.cpa.arg.ARGState;
import org.sosy_lab.cpachecker.cpa.arg.path.ARGPath;
import org.sosy_lab.cpachecker.util.CFAUtils;
import org.sosy_lab.cpachecker.util.predicates.pathformula.PathFormula;
import org.sosy_lab.cpachecker.util.predicates.pathformula.PathFormulaManager;
import org.sosy_lab.cpachecker.util.predicates.pathformula.PathFormulaManagerImpl;
import org.sosy_lab.cpachecker.util.predicates.smt.SolverViewBasedTest0;
import org.sosy_lab.cpachecker.util.test.TestDataTools;
import org.sosy_lab.java_smt.api.BooleanFormula;

public class CfaPrecisionCompilerTest extends SolverViewBasedTest0 {

  private PathFormulaManager pfmgr;

  @Before
  public void createPathFormulaManager() throws Exception {
    pfmgr =
        new PathFormulaManagerImpl(
            mgrv,
            config,
            logger,
            ShutdownNotifier.createDummy(),
            MachineModel.LINUX32,
            Optional.empty(),
            AnalysisDirection.FORWARD,
            Language.C);
  }

  @Test
  public void takenBranchesUseNativeSignedUnsignedAndScopedSemantics() throws Exception {
    CFA cfa =
        parse(
            """
            int main() {
              int signed_value = 1;
              unsigned int unsigned_value = 2;
              int work = 0;
              if (signed_value < unsigned_value) { work++; } else { work--; }
              while (work < 3) { work++; }
              return 0;
            }
            """);
    CFANode head = headFor(cfa, "work < 3");
    CAssumeEdge takenTrue = assume(cfa, "signed_value < unsigned_value", true);
    CAssumeEdge takenFalse = assume(cfa, "signed_value < unsigned_value", false);
    CfaPrecisionCompiler compiler = compiler(cfa);

    CfaPrecisionCompiler.Candidate trueCandidate =
        compiler.compile(path(takenTrue, head)).candidates().getFirst();
    CfaPrecisionCompiler.Candidate falseCandidate =
        compiler.compile(path(takenFalse, head)).candidates().getFirst();

    assertEquivalent(trueCandidate.formula(), nativeFormula(takenTrue));
    assertEquivalent(falseCandidate.formula(), nativeFormula(takenFalse));
    assertThat(solver.isUnsat(bmgrv.and(trueCandidate.formula(), falseCandidate.formula())))
        .isTrue();
    assertThat(trueCandidate.preservedVariables())
        .containsExactly("main::signed_value", "main::unsigned_value")
        .inOrder();
    assertThat(falseCandidate.preservedVariables())
        .containsExactly("main::signed_value", "main::unsigned_value")
        .inOrder();
    assertThat(falseCandidate.validated().classification())
        .isEqualTo(ValidatedPredicate.Classification.PRECISION_ONLY);
  }

  @Test
  public void transportsAcrossUnrelatedWriteAndNestedHeadsUntilReferencedKill() throws Exception {
    CFA cfa =
        parse(
            """
            int main() {
              int guard = 1;
              int unrelated = 0;
              int i = 0;
              if (guard < 10) { unrelated++; }
              unrelated = 7;
              while (i < 3) {
                while (i < 2) { i++; }
                guard = 11;
                i++;
              }
              return 0;
            }
            """);
    CAssumeEdge source = assume(cfa, "guard < 10", true);
    CFANode outer = headFor(cfa, "i < 3");
    CFANode inner = headFor(cfa, "i < 2");
    CFAEdge kill = edge(cfa, "guard = 11");
    List<CFAEdge> fullPath = new ArrayList<>();
    fullPath.add(source);
    appendPath(fullPath, source.getSuccessor(), inner);
    appendPath(fullPath, inner, kill.getPredecessor());
    fullPath.add(kill);
    appendPath(fullPath, kill.getSuccessor(), outer);

    CfaPrecisionCompiler.Result result = compiler(cfa).compile(path(fullPath));

    List<CfaPrecisionCompiler.Candidate> guardCandidates =
        result.candidates().stream()
            .filter(
                candidate -> candidate.preservedVariables().equals(ImmutableList.of("main::guard")))
            .toList();
    assertThat(guardCandidates.stream().map(CfaPrecisionCompiler.Candidate::loopHead))
        .containsExactly(outer, inner);
    assertThat(
            guardCandidates.stream()
                .flatMap(candidate -> candidate.certificate().origins().stream()))
        .hasSize(2);
    assertThat(result.rejections().stream().map(CfaPrecisionCompiler.Rejection::reason))
        .contains(CfaPrecisionCompiler.RejectionReason.REFERENCED_VARIABLE_KILLED);
  }

  @Test
  public void duplicateGuardsAndRepeatedHeadVisitsHaveStableDedupAndHash() throws Exception {
    CFA cfa =
        parse(
            """
            int main() {
              int x = 1;
              int i = 0;
              if (x < 10) { i += 0; }
              if (x < 10) { i += 0; }
              while (i < 2) { i++; }
              return 0;
            }
            """);
    List<CAssumeEdge> guards = assumes(cfa, "x < 10", true);
    CFANode head = headFor(cfa, "i < 2");
    CAssumeEdge loopTaken = assume(cfa, "i < 2", true);
    List<CFAEdge> fullPath = new ArrayList<>();
    fullPath.add(guards.get(0));
    appendPath(fullPath, guards.get(0).getSuccessor(), guards.get(1).getPredecessor());
    fullPath.add(guards.get(1));
    appendPath(fullPath, guards.get(1).getSuccessor(), head);
    fullPath.add(loopTaken);
    appendPath(fullPath, loopTaken.getSuccessor(), head);
    ARGPath path = path(fullPath);
    CfaPrecisionCompiler compiler = compiler(cfa);

    CfaPrecisionCompiler.Result first = compiler.compile(path);
    CfaPrecisionCompiler.Result second = compiler.compile(path);

    assertThat(first.candidates()).hasSize(1);
    assertThat(first.candidates().getFirst().certificate().origins()).hasSize(4);
    List<Integer> targetOccurrences = new ArrayList<>();
    first
        .dump()
        .path("candidates")
        .get(0)
        .path("path_or_region")
        .path("target_node_occurrences")
        .forEach(node -> targetOccurrences.add(node.asInt()));
    assertThat(targetOccurrences).isInOrder();
    assertThat(first.canonicalDump()).isEqualTo(second.canonicalDump());
    assertThat(first.sha256()).isEqualTo(second.sha256());
  }

  @Test
  public void rejectsPathHolePointerPartialCallAndCrossFunctionDeterministically()
      throws Exception {
    ARGPath hole =
        new ARGPath(
            ImmutableList.of(new ARGState(null, null), new ARGState(null, null)),
            java.util.Collections.singletonList(null));
    CfaPrecisionCompiler.Result holeResult =
        new CfaPrecisionCompiler(pfmgr, mgrv, new LoopHeadIndex(Optional.empty())).compile(hole);
    assertThat(holeResult.rejections().getFirst().reason())
        .isEqualTo(CfaPrecisionCompiler.RejectionReason.UNRESOLVED_ARGPATH_HOLE);

    assertBarrierReason(
        """
        extern void opaque(void);
        int main() { int x=1, i=0; if (x) {} opaque(); while (i < 2) { i++; } }
        """,
        "x",
        "i < 2",
        CfaPrecisionCompiler.RejectionReason.UNKNOWN_CALL_EFFECT);
    assertBarrierReason(
        """
        extern int opaque(void);
        int main() {
          int x=1, i=0;
          if (x) {}
          int from_call=opaque();
          while (i < 2) { i++; }
        }
        """,
        "x",
        "i < 2",
        CfaPrecisionCompiler.RejectionReason.UNKNOWN_CALL_EFFECT);
    assertBarrierReason(
        """
        struct S { int field; };
        int main() { int x=1, i=0; struct S s; if (x) {} s.field=1; while (i < 2) { i++; } }
        """,
        "x",
        "i < 2",
        CfaPrecisionCompiler.RejectionReason.PARTIAL_DEFINITION);
    assertBarrierReason(
        """
        int main() { int x=1, i=0, value=0; int *p=&value; if (x) {} *p=1; while (i < 2) { i++; } }
        """,
        "x",
        "i < 2",
        CfaPrecisionCompiler.RejectionReason.POINTER_OR_POINTEE_WRITE);
    assertBarrierReason(
        """
        int main() {
          int x=1, i=0, first=0, second=0;
          int *p=&first;
          if (x) {}
          p=&second;
          while (i < 2) { i++; }
        }
        """,
        "x",
        "i < 2",
        CfaPrecisionCompiler.RejectionReason.POINTER_OR_POINTEE_WRITE);
    assertBarrierReason(
        """
        void helper(void) {}
        int main() { int x=1, i=0; if (x) {} helper(); while (i < 2) { i++; } }
        """,
        "x",
        "i < 2",
        CfaPrecisionCompiler.RejectionReason.CROSS_FUNCTION_SEGMENT);
  }

  @Test
  public void rejectsUnsupportedDeclarationTypeAndFormulaSupportMismatch() throws Exception {
    assertSourceReason(
        "int main() { float f=1; int i=0; if (f > 0) {i=1;} else {i=2;} while (i < 2) { i++; } }",
        "f",
        CfaPrecisionCompiler.RejectionReason.UNSUPPORTED_TYPE);
    assertSourceReason(
        "int helper(void); int main() { int i=0; if (helper) {i=1;} else {i=2;} while (i < 2) {"
            + " i++; } }",
        "helper",
        CfaPrecisionCompiler.RejectionReason.UNSUPPORTED_DECLARATION);

    CFA cfa =
        parse("int main() { int x=1, i=0; if (x) {i=1;} else {i=2;} while (i < 2) { i++; } }");
    CAssumeEdge guard = assume(cfa, "x", true);
    PathFormulaManager mismatching = mock(PathFormulaManager.class);
    PathFormula empty = mock(PathFormula.class);
    PathFormula converted = mock(PathFormula.class);
    when(mismatching.makeEmptyPathFormula()).thenReturn(empty);
    when(mismatching.makeAnd(empty, guard)).thenReturn(converted);
    when(converted.getFormula()).thenReturn(bmgrv.makeVariable("main::other"));

    CfaPrecisionCompiler.Result result =
        new CfaPrecisionCompiler(mismatching, mgrv, new LoopHeadIndex(cfa.getLoopStructure()))
            .compile(path(guard, headFor(cfa, "i < 2")));
    assertThat(result.rejections().stream().map(CfaPrecisionCompiler.Rejection::reason))
        .contains(CfaPrecisionCompiler.RejectionReason.FORMULA_SUPPORT_MISMATCH);
  }

  private void assertSourceReason(
      String source, String guardText, CfaPrecisionCompiler.RejectionReason expected)
      throws Exception {
    CFA cfa = parse(source);
    CAssumeEdge guard = assume(cfa, guardText, true);
    CfaPrecisionCompiler.Result result = compiler(cfa).compile(path(guard, headFor(cfa, "i < 2")));
    assertThat(result.candidates()).isEmpty();
    assertThat(result.rejections().stream().map(CfaPrecisionCompiler.Rejection::reason))
        .contains(expected);
  }

  private void assertBarrierReason(
      String source,
      String guardText,
      String loopText,
      CfaPrecisionCompiler.RejectionReason expected)
      throws Exception {
    CFA cfa = parse(source);
    CAssumeEdge guard = assume(cfa, guardText, true);
    ARGPath path = path(guard, headFor(cfa, loopText));
    CfaPrecisionCompiler compiler = compiler(cfa);
    CfaPrecisionCompiler.Result result = compiler.compile(path);
    assertThat(result.candidates()).isEmpty();
    assertThat(result.rejections().stream().map(CfaPrecisionCompiler.Rejection::reason))
        .contains(expected);
    assertThat(compiler.compile(path).canonicalDump()).isEqualTo(result.canonicalDump());
  }

  private CfaPrecisionCompiler compiler(CFA cfa) {
    return new CfaPrecisionCompiler(pfmgr, mgrv, new LoopHeadIndex(cfa.getLoopStructure()));
  }

  private CFA parse(String source) throws Exception {
    Configuration parserConfig =
        Configuration.builder()
            .copyFrom(config)
            .setOption("cfa.export", "false")
            .setOption("cfa.exportPerFunction", "false")
            .build();
    return TestDataTools.makeCFA(parserConfig, source);
  }

  private BooleanFormula nativeFormula(CAssumeEdge edge) throws Exception {
    return mgrv.uninstantiate(pfmgr.makeAnd(pfmgr.makeEmptyPathFormula(), edge).getFormula());
  }

  private void assertEquivalent(BooleanFormula actual, BooleanFormula expected) throws Exception {
    assertThat(solver.implies(actual, expected)).isTrue();
    assertThat(solver.implies(expected, actual)).isTrue();
  }

  private static ARGPath path(CFAEdge first, CFANode target) {
    List<CFAEdge> edges = new ArrayList<>();
    edges.add(first);
    appendPath(edges, first.getSuccessor(), target);
    return path(edges);
  }

  private static ARGPath path(List<CFAEdge> edges) {
    List<ARGState> states = new ArrayList<>();
    for (int i = 0; i <= edges.size(); i++) {
      states.add(new ARGState(null, null));
    }
    return new ARGPath(states, edges, edges);
  }

  private static void appendPath(List<CFAEdge> out, CFANode source, CFANode target) {
    out.addAll(shortestPath(source, target));
  }

  private static List<CFAEdge> shortestPath(CFANode source, CFANode target) {
    if (source.equals(target)) {
      return new ArrayList<>();
    }
    ArrayDeque<CFANode> waitlist = new ArrayDeque<>();
    Map<CFANode, CFAEdge> incoming = new HashMap<>();
    waitlist.add(source);
    incoming.put(source, null);
    while (!waitlist.isEmpty() && !incoming.containsKey(target)) {
      CFANode node = waitlist.removeFirst();
      for (CFAEdge edge : node.getLeavingEdges()) {
        if (!incoming.containsKey(edge.getSuccessor())) {
          incoming.put(edge.getSuccessor(), edge);
          waitlist.addLast(edge.getSuccessor());
        }
      }
    }
    assertThat(incoming).containsKey(target);
    List<CFAEdge> reversed = new ArrayList<>();
    for (CFANode node = target; !node.equals(source); ) {
      CFAEdge edge = incoming.get(node);
      reversed.add(edge);
      node = edge.getPredecessor();
    }
    java.util.Collections.reverse(reversed);
    return reversed;
  }

  private static CFANode headFor(CFA cfa, String expression) {
    return assume(cfa, expression, true).getPredecessor();
  }

  private static CAssumeEdge assume(CFA cfa, String expression, boolean truth) {
    return assumes(cfa, expression, truth).getFirst();
  }

  private static List<CAssumeEdge> assumes(CFA cfa, String expression, boolean truth) {
    return CFAUtils.allEdges(cfa)
        .filter(CAssumeEdge.class)
        .filter(
            edge ->
                edge.getRawStatement().contains(expression)
                    || edge.getExpression().toASTString().contains(expression))
        .filter(edge -> edge.getTruthAssumption() == truth)
        .toList();
  }

  private static CFAEdge edge(CFA cfa, String code) {
    return CFAUtils.allEdges(cfa)
        .filter(candidate -> candidate.getRawStatement().contains(code))
        .first()
        .get();
  }
}
