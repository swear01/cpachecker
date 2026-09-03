// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.truth.Truth.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.google.common.collect.ImmutableList;
import com.google.common.hash.Hashing;
import java.nio.charset.StandardCharsets;
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
import org.sosy_lab.cpachecker.cfa.ast.FileLocation;
import org.sosy_lab.cpachecker.cfa.ast.c.CIdExpression;
import org.sosy_lab.cpachecker.cfa.model.CFAEdge;
import org.sosy_lab.cpachecker.cfa.model.CFANode;
import org.sosy_lab.cpachecker.cfa.model.c.CAssumeEdge;
import org.sosy_lab.cpachecker.cfa.types.MachineModel;
import org.sosy_lab.cpachecker.cfa.types.c.CNumericTypes;
import org.sosy_lab.cpachecker.core.AnalysisDirection;
import org.sosy_lab.cpachecker.cpa.arg.ARGState;
import org.sosy_lab.cpachecker.cpa.arg.path.ARGPath;
import org.sosy_lab.cpachecker.cpa.location.LocationStateFactory;
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
  public void projectsAssignmentBackedEqualityAcrossNestedHeads() throws Exception {
    CFA cfa =
        parse(
            """
            int main() {
              int n = 4;
              int i;
              int j;
              int k;
              if (i >= 0) {}
              i = 0;
              while (i < n) {
                j = 2 * i;
                while (j < 3 * i) {
                  k = i;
                  while (k < j) { k++; }
                }
              }
              return 0;
            }
            """);
    CFAEdge initialization = edge(cfa, "i = 0");
    CFANode outer = headFor(cfa, "i < n");
    CFANode middle = headFor(cfa, "j < 3 * i");
    CFANode inner = headFor(cfa, "k < j");
    BooleanFormula equality = nativeFormula(initialization);
    BooleanFormula expected = nativeFormula(assume(cfa, "i >= 0", true));
    List<CFAEdge> fullPath = new ArrayList<>();
    fullPath.add(initialization);
    appendPath(fullPath, initialization.getSuccessor(), inner);
    CfaPrecisionCompiler compiler = compiler(cfa);

    CfaPrecisionCompiler.Result result =
        compiler.compile(
            path(fullPath),
            ImmutableList.of(locationState(cfa, outer)),
            ImmutableList.of(equality));

    assertThat(
            result.candidates().stream()
                .filter(candidate -> equivalent(candidate.formula(), expected))
                .map(CfaPrecisionCompiler.Candidate::loopHead))
        .containsExactly(outer, middle, inner);
    List<CfaPrecisionCompiler.Candidate> projections =
        result.candidates().stream()
            .filter(
                candidate ->
                    candidate.certificate().origins().stream()
                        .anyMatch(origin -> origin.sourceKind().equals("PROOF_EQUALITY")))
            .toList();
    assertThat(projections).hasSize(6);
    assertThat(
            projections.stream()
                .flatMap(candidate -> candidate.certificate().origins().stream())
                .map(CfaPrecisionCompiler.Origin::comparisonDirection))
        .containsExactly(
            "LESS_OR_EQUAL",
            "GREATER_OR_EQUAL",
            "LESS_OR_EQUAL",
            "GREATER_OR_EQUAL",
            "LESS_OR_EQUAL",
            "GREATER_OR_EQUAL");
    assertThat(result.dump().path("schema_version").asText())
        .isEqualTo(CfaPrecisionCompiler.SCHEMA_VERSION);
    assertThat(
            projections.stream()
                .map(CfaPrecisionCompiler.Candidate::validated)
                .map(ValidatedPredicate::classification))
        .containsExactlyElementsIn(
            java.util.Collections.nCopies(6, ValidatedPredicate.Classification.PRECISION_ONLY));
    assertThat(
            projections.stream()
                .flatMap(candidate -> candidate.certificate().origins().stream())
                .allMatch(
                    origin ->
                        !origin.sourceAssignmentEquality().isEmpty()
                            && !origin.proofEquality().isEmpty()
                            && origin.assignmentProofEquivalent()
                            && origin.proofImpliesCandidate()))
        .isTrue();
    assertThat(
            compiler
                .compile(
                    path(fullPath),
                    ImmutableList.of(locationState(cfa, outer)),
                    ImmutableList.of(equality))
                .canonicalDump())
        .isEqualTo(result.canonicalDump());
  }

  @Test
  public void usesNativeUnsignedComparisonAndWidth() throws Exception {
    CFA cfa =
        parse(
            """
            int main() {
              unsigned int x;
              int i = 0;
              if (x >= 0) {}
              x = 0;
              while (i < 2) { i++; }
              return 0;
            }
            """);
    CFAEdge assignment = edge(cfa, "x = 0");
    CFANode head = headFor(cfa, "i < 2");
    BooleanFormula expected = nativeFormula(assume(cfa, "x >= 0", true));
    List<CFAEdge> fullPath = new ArrayList<>();
    fullPath.add(assignment);
    appendPath(fullPath, assignment.getSuccessor(), head);

    CfaPrecisionCompiler.Result result =
        compiler(cfa)
            .compile(
                path(fullPath),
                ImmutableList.of(locationState(cfa, head)),
                ImmutableList.of(nativeFormula(assignment)));
    CfaPrecisionCompiler.Candidate candidate =
        result.candidates().stream()
            .filter(item -> equivalent(item.formula(), expected))
            .findFirst()
            .orElseThrow();
    CfaPrecisionCompiler.Origin origin = candidate.certificate().origins().getFirst();

    assertThat(origin.comparisonDirection()).isEqualTo("GREATER_OR_EQUAL");
    assertThat(origin.signed()).isFalse();
    assertThat(origin.bitWidth()).isEqualTo(32);
  }

  @Test
  public void rejectsSelfDependentAssignmentProjection() throws Exception {
    CFA cfa = parse("int main() { int i = 0; i++; while (i < 2) { i++; } return 0; }");
    CFAEdge initialization = edge(cfa, "int i = 0");
    CFAEdge increment = edge(cfa, "i++");
    CFANode head = headFor(cfa, "i < 2");
    List<CFAEdge> fullPath = new ArrayList<>();
    fullPath.add(increment);
    appendPath(fullPath, increment.getSuccessor(), head);

    CfaPrecisionCompiler.Result result =
        compiler(cfa)
            .compile(
                path(fullPath),
                ImmutableList.of(locationState(cfa, head)),
                ImmutableList.of(nativeFormula(initialization)));

    assertThat(
            result.candidates().stream()
                .flatMap(candidate -> candidate.certificate().origins().stream())
                .map(CfaPrecisionCompiler.Origin::sourceKind))
        .doesNotContain("PROOF_EQUALITY");
    assertThat(result.rejections().stream().map(CfaPrecisionCompiler.Rejection::reason))
        .contains(CfaPrecisionCompiler.RejectionReason.ASSIGNMENT_EQUALITY_NOT_PROJECTABLE);
  }

  @Test
  public void rejectsUnsafeEdgesBeforeReachingAssignment() throws Exception {
    assertBackwardBarrier(
        """
        extern void opaque(void);
        int main() { int x; int i=0; x=0; opaque(); while (i<2) { i++; } }
        """,
        "x=0");
    assertBackwardBarrier(
        """
        int main() { int x; int y=0; int *p=&y; int i=0; x=0; *p=1; while (i<2) { i++; } }
        """,
        "x=0");
    assertBackwardBarrier(
        """
        struct S { int field; };
        int main() { int x; struct S s; int i=0; x=0; s.field=1; while (i<2) { i++; } }
        """,
        "x=0");
  }

  @Test
  public void rejectsProofNodeOutsideFullPath() throws Exception {
    CFA cfa = parse("int main() { int x=0, i=0, j=0; while (i<2) { i++; } while (j<2) { j++; } }");
    CFAEdge assignment = edge(cfa, "int x=0");
    CFANode firstHead = headFor(cfa, "i<2");
    CFANode secondHead = headFor(cfa, "j<2");
    List<CFAEdge> fullPath = new ArrayList<>();
    fullPath.add(assignment);
    appendPath(fullPath, assignment.getSuccessor(), firstHead);

    CfaPrecisionCompiler.Result result =
        compiler(cfa)
            .compile(
                path(fullPath),
                ImmutableList.of(locationState(cfa, secondHead)),
                ImmutableList.of(nativeFormula(assignment)));

    assertThat(result.rejections().stream().map(CfaPrecisionCompiler.Rejection::reason))
        .contains(CfaPrecisionCompiler.RejectionReason.PROOF_TRACE_ALIGNMENT_MISMATCH);
  }

  @Test
  public void acceptsCastAndReversedProofEquality() throws Exception {
    CFA cfa =
        parse(
            """
            int main() {
              int x;
              int i=0;
              if (0 == x) {}
              if (x >= 0) {}
              x = (int)0;
              while (i<2) { i++; }
            }
            """);
    CFAEdge assignment = edge(cfa, "x = (int)0");
    CFANode head = headFor(cfa, "i<2");
    List<CFAEdge> fullPath = new ArrayList<>();
    fullPath.add(assignment);
    appendPath(fullPath, assignment.getSuccessor(), head);
    BooleanFormula expected = nativeFormula(assume(cfa, "x >= 0", true));

    CfaPrecisionCompiler.Result result =
        compiler(cfa)
            .compile(
                path(fullPath),
                ImmutableList.of(locationState(cfa, head)),
                ImmutableList.of(nativeFormula(assume(cfa, "0 == x", true))));

    assertThat(
            result.candidates().stream()
                .filter(candidate -> equivalent(candidate.formula(), expected))
                .map(CfaPrecisionCompiler.Candidate::loopHead))
        .containsExactly(head);
  }

  @Test
  public void restartsAfterSupportedAssignmentAtRepeatedHead() throws Exception {
    CFA cfa =
        parse(
            """
            int main() {
              int x;
              int i=0;
              if (x >= 0) {}
              if (x >= 1) {}
              x=0;
              while (i<2) { x=1; i++; }
            }
            """);
    CFAEdge zero = edge(cfa, "x=0");
    CFAEdge one = edge(cfa, "x=1");
    CAssumeEdge loopTaken = assume(cfa, "i<2", true);
    CFANode head = loopTaken.getPredecessor();
    List<CFAEdge> fullPath = new ArrayList<>();
    fullPath.add(zero);
    appendPath(fullPath, zero.getSuccessor(), head);
    int firstHeadOccurrence = fullPath.size();
    fullPath.add(loopTaken);
    appendPath(fullPath, loopTaken.getSuccessor(), one.getPredecessor());
    fullPath.add(one);
    appendPath(fullPath, one.getSuccessor(), head);
    int secondHeadOccurrence = fullPath.size();

    CfaPrecisionCompiler.Result result =
        compiler(cfa)
            .compile(
                path(fullPath),
                ImmutableList.of(locationState(cfa, head), locationState(cfa, head)),
                ImmutableList.of(nativeFormula(zero), nativeFormula(one)));
    CfaPrecisionCompiler.Candidate zeroCandidate =
        candidateEquivalentTo(result, nativeFormula(assume(cfa, "x >= 0", true)));
    CfaPrecisionCompiler.Candidate oneCandidate =
        candidateEquivalentTo(result, nativeFormula(assume(cfa, "x >= 1", true)));

    assertThat(
            zeroCandidate.certificate().origins().stream()
                .map(CfaPrecisionCompiler.Origin::targetNodeOccurrence))
        .containsExactly(firstHeadOccurrence);
    assertThat(
            oneCandidate.certificate().origins().stream()
                .map(CfaPrecisionCompiler.Origin::targetNodeOccurrence))
        .containsExactly(secondHeadOccurrence);
  }

  @Test
  public void handlesShadowedAndRejectsNonEquivalentProofSources() throws Exception {
    CFA shadowed =
        parse(
            """
            int main() {
              int x=0;
              int i=0;
              { int x=1; while (i<2) { i++; } }
            }
            """);
    CFAEdge outer = edge(shadowed, "int x=0");
    CFAEdge inner = edge(shadowed, "int x=1");
    CFANode shadowedHead = headFor(shadowed, "i<2");
    List<CFAEdge> shadowedPath = new ArrayList<>();
    shadowedPath.add(outer);
    appendPath(shadowedPath, outer.getSuccessor(), shadowedHead);
    CfaPrecisionCompiler.Result shadowedResult =
        compiler(shadowed)
            .compile(
                path(shadowedPath),
                ImmutableList.of(locationState(shadowed, shadowedHead)),
                ImmutableList.of(nativeFormula(inner)));
    assertThat(
            shadowedResult.candidates().stream()
                .flatMap(candidate -> candidate.preservedVariables().stream()))
        .contains("main::x__1");
    assertThat(
            shadowedResult.candidates().stream()
                .flatMap(candidate -> candidate.preservedVariables().stream()))
        .doesNotContain("main::x");

    CFA mismatch = parse("int main() { int x; int i=0; if (x==1) {} x=0; while (i<2) { i++; } }");
    CFAEdge assignment = edge(mismatch, "x=0");
    CFANode mismatchHead = headFor(mismatch, "i<2");
    List<CFAEdge> mismatchPath = new ArrayList<>();
    mismatchPath.add(assignment);
    appendPath(mismatchPath, assignment.getSuccessor(), mismatchHead);
    CfaPrecisionCompiler.Result mismatchResult =
        compiler(mismatch)
            .compile(
                path(mismatchPath),
                ImmutableList.of(locationState(mismatch, mismatchHead)),
                ImmutableList.of(nativeFormula(assume(mismatch, "x==1", true))));
    assertThat(mismatchResult.rejections().stream().map(CfaPrecisionCompiler.Rejection::reason))
        .contains(CfaPrecisionCompiler.RejectionReason.ASSIGNMENT_PROOF_NOT_EQUIVALENT);
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
    assertThat(
            guardCandidates.stream()
                .flatMap(candidate -> candidate.certificate().origins().stream())
                .flatMap(origin -> origin.directMayDefs().stream()))
        .contains("main::unrelated");
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
    assertThat(
            first.candidates().getFirst().certificate().origins().stream()
                .allMatch(
                    origin ->
                        origin.transportStartEdgeOccurrenceInclusive()
                                == origin.sourceEdgeOccurrence() + 1
                            && origin.transportEndEdgeOccurrenceExclusive()
                                == origin.targetNodeOccurrence()
                            && origin.targetNode()
                                == first.candidates().getFirst().loopHead().getNodeNumber()))
        .isTrue();
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
    assertThat(
            Hashing.sha256()
                .hashString(
                    new ObjectMapper()
                        .writeValueAsString(first.dump().deepCopy().without("sha256")),
                    StandardCharsets.UTF_8)
                .toString())
        .isEqualTo(first.sha256());
  }

  @Test
  public void rejectsPathHolePointerPartialCallAndCrossFunctionDeterministically()
      throws Exception {
    ARGPath hole =
        new ARGPath(
            ImmutableList.of(new ARGState(null, null), new ARGState(null, null)),
            java.util.Collections.singletonList(null));
    CfaPrecisionCompiler.Result holeResult =
        new CfaPrecisionCompiler(
                pfmgr, mgrv, new LoopHeadIndex(Optional.empty()), solver, MachineModel.LINUX32)
            .compile(hole);
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
        new CfaPrecisionCompiler(
                mismatching,
                mgrv,
                new LoopHeadIndex(cfa.getLoopStructure()),
                solver,
                cfa.getMachineModel())
            .compile(path(guard, headFor(cfa, "i < 2")));
    assertThat(result.rejections().stream().map(CfaPrecisionCompiler.Rejection::reason))
        .contains(CfaPrecisionCompiler.RejectionReason.FORMULA_SUPPORT_MISMATCH);
  }

  @Test
  public void rejectsMissingDeclaration() throws Exception {
    CAssumeEdge guard =
        new CAssumeEdge(
            "mystery",
            FileLocation.DUMMY,
            CFANode.newDummyCFANode("main"),
            CFANode.newDummyCFANode("main"),
            new CIdExpression(FileLocation.DUMMY, CNumericTypes.SIGNED_INT, "mystery", null),
            true);

    CfaPrecisionCompiler.Result result =
        new CfaPrecisionCompiler(
                pfmgr, mgrv, new LoopHeadIndex(Optional.empty()), solver, MachineModel.LINUX32)
            .compile(path(ImmutableList.of(guard)));

    assertThat(result.candidates()).isEmpty();
    assertThat(result.rejections().stream().map(CfaPrecisionCompiler.Rejection::reason))
        .contains(CfaPrecisionCompiler.RejectionReason.UNSUPPORTED_DECLARATION);
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

  private void assertBackwardBarrier(String source, String assignmentText) throws Exception {
    CFA cfa = parse(source);
    CFAEdge assignment = edge(cfa, assignmentText);
    CFANode head = headFor(cfa, "i<2");
    List<CFAEdge> fullPath = new ArrayList<>();
    fullPath.add(assignment);
    appendPath(fullPath, assignment.getSuccessor(), head);

    CfaPrecisionCompiler.Result result =
        compiler(cfa)
            .compile(
                path(fullPath),
                ImmutableList.of(locationState(cfa, head)),
                ImmutableList.of(nativeFormula(assignment)));

    assertThat(
            result.candidates().stream()
                .flatMap(candidate -> candidate.certificate().origins().stream())
                .map(CfaPrecisionCompiler.Origin::sourceKind))
        .doesNotContain("PROOF_EQUALITY");
    assertThat(result.rejections().stream().map(CfaPrecisionCompiler.Rejection::reason))
        .contains(CfaPrecisionCompiler.RejectionReason.REACHING_DEFINITION_NOT_EXACT_ASSIGNMENT);
  }

  private CfaPrecisionCompiler.Candidate candidateEquivalentTo(
      CfaPrecisionCompiler.Result result, BooleanFormula expected) {
    return result.candidates().stream()
        .filter(candidate -> equivalent(candidate.formula(), expected))
        .findFirst()
        .orElseThrow();
  }

  private CfaPrecisionCompiler compiler(CFA cfa) {
    return new CfaPrecisionCompiler(
        pfmgr, mgrv, new LoopHeadIndex(cfa.getLoopStructure()), solver, cfa.getMachineModel());
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

  private BooleanFormula nativeFormula(CFAEdge edge) throws Exception {
    return mgrv.uninstantiate(pfmgr.makeAnd(pfmgr.makeEmptyPathFormula(), edge).getFormula());
  }

  private boolean equivalent(BooleanFormula actual, BooleanFormula expected) {
    try {
      return solver.implies(actual, expected) && solver.implies(expected, actual);
    } catch (Exception e) {
      throw new AssertionError(e);
    }
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

  private ARGState locationState(CFA cfa, CFANode node) throws Exception {
    LocationStateFactory locationFactory =
        new LocationStateFactory(cfa, AnalysisDirection.FORWARD, config);
    return new ARGState(locationFactory.getState(node), null);
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
