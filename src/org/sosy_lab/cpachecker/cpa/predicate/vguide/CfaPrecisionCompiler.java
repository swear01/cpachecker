// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static org.sosy_lab.cpachecker.util.AbstractStates.extractLocation;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableMap;
import com.google.common.collect.ImmutableSet;
import com.google.common.hash.Hashing;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.TreeSet;
import org.sosy_lab.cpachecker.cfa.ast.AAstNode;
import org.sosy_lab.cpachecker.cfa.ast.c.CAstNode;
import org.sosy_lab.cpachecker.cfa.ast.c.CFunctionCall;
import org.sosy_lab.cpachecker.cfa.ast.c.CFunctionCallExpression;
import org.sosy_lab.cpachecker.cfa.ast.c.CIdExpression;
import org.sosy_lab.cpachecker.cfa.ast.c.CParameterDeclaration;
import org.sosy_lab.cpachecker.cfa.ast.c.CSimpleDeclaration;
import org.sosy_lab.cpachecker.cfa.ast.c.CVariableDeclaration;
import org.sosy_lab.cpachecker.cfa.model.CFAEdge;
import org.sosy_lab.cpachecker.cfa.model.CFANode;
import org.sosy_lab.cpachecker.cfa.model.FunctionCallEdge;
import org.sosy_lab.cpachecker.cfa.model.FunctionReturnEdge;
import org.sosy_lab.cpachecker.cfa.model.FunctionSummaryEdge;
import org.sosy_lab.cpachecker.cfa.model.c.CAssumeEdge;
import org.sosy_lab.cpachecker.cfa.types.MachineModel;
import org.sosy_lab.cpachecker.cfa.types.c.CPointerType;
import org.sosy_lab.cpachecker.cfa.types.c.CSimpleType;
import org.sosy_lab.cpachecker.cfa.types.c.CType;
import org.sosy_lab.cpachecker.cfa.types.c.CTypes;
import org.sosy_lab.cpachecker.cpa.arg.ARGState;
import org.sosy_lab.cpachecker.cpa.arg.path.ARGPath;
import org.sosy_lab.cpachecker.cpa.predicate.BlockFormulaStrategy.BlockFormulas;
import org.sosy_lab.cpachecker.exceptions.CPATransferException;
import org.sosy_lab.cpachecker.util.CFAEdgeUtils;
import org.sosy_lab.cpachecker.util.CFAUtils;
import org.sosy_lab.cpachecker.util.dependencegraph.EdgeDefUseData;
import org.sosy_lab.cpachecker.util.predicates.pathformula.PathFormula;
import org.sosy_lab.cpachecker.util.predicates.pathformula.PathFormulaManager;
import org.sosy_lab.cpachecker.util.predicates.smt.FormulaManagerView;
import org.sosy_lab.cpachecker.util.predicates.smt.Solver;
import org.sosy_lab.cpachecker.util.states.MemoryLocation;
import org.sosy_lab.java_smt.api.BooleanFormula;
import org.sosy_lab.java_smt.api.Formula;
import org.sosy_lab.java_smt.api.FormulaType;
import org.sosy_lab.java_smt.api.FunctionDeclaration;
import org.sosy_lab.java_smt.api.FunctionDeclarationKind;
import org.sosy_lab.java_smt.api.SolverException;
import org.sosy_lab.java_smt.api.visitors.DefaultFormulaVisitor;

/** Compiles native path evidence into local predicate-precision entries. */
final class CfaPrecisionCompiler {

  static final String SCHEMA_VERSION = "cfa-precision-compiler-v2";
  private static final ObjectMapper JSON = new ObjectMapper();

  enum RejectionReason {
    UNRESOLVED_ARGPATH_HOLE,
    ASSUME_FORMULA_CONVERSION_FAILED,
    NO_SCALAR_SUPPORT,
    UNSUPPORTED_DECLARATION,
    UNSUPPORTED_TYPE,
    FORMULA_SUPPORT_MISMATCH,
    CROSS_FUNCTION_SEGMENT,
    UNKNOWN_CALL_EFFECT,
    POINTER_OR_POINTEE_WRITE,
    PARTIAL_DEFINITION,
    REFERENCED_VARIABLE_KILLED,
    PROOF_TRACE_ALIGNMENT_MISMATCH,
    PROOF_ATOM_NOT_NUMERAL_EQUALITY,
    UNRESOLVED_PROOF_VARIABLE,
    AMBIGUOUS_PROOF_VARIABLE,
    NO_REACHING_DEFINITION,
    REACHING_DEFINITION_NOT_EXACT_ASSIGNMENT,
    ASSIGNMENT_RELATION_CONVERSION_FAILED,
    ASSIGNMENT_EQUALITY_NOT_PROJECTABLE,
    ASSIGNMENT_TYPE_WIDTH_MISMATCH,
    ASSIGNMENT_PROOF_NOT_EQUIVALENT,
    PROJECTION_NOT_IMPLIED,
    SOLVER_CHECK_FAILED
  }

  record Origin(
      String sourceKind,
      int sourceEdgeOccurrence,
      int sourceProofIndex,
      int sourceNodeOccurrence,
      int sourcePredecessorNode,
      int sourceSuccessorNode,
      int targetNodeOccurrence,
      int targetNode,
      int transportStartEdgeOccurrenceInclusive,
      int transportEndEdgeOccurrenceExclusive,
      ImmutableList<String> directMayDefs,
      String derivation,
      String sourceAssignmentEquality,
      String proofEquality,
      String projectedAssignmentEquality,
      String projectedProofEquality,
      String comparisonDirection,
      boolean signed,
      int bitWidth,
      boolean assignmentProofEquivalent,
      boolean proofImpliesCandidate) {}

  record Certificate(String semantics, ImmutableList<Origin> origins) {}

  record Candidate(
      BooleanFormula formula,
      CFANode loopHead,
      String canonicalFormula,
      ImmutableList<String> preservedVariables,
      Certificate certificate) {

    ValidatedPredicate validated() {
      return new ValidatedPredicate(
          formula,
          loopHead,
          ValidatedPredicate.Classification.PRECISION_ONLY,
          "CFA_NATIVE_PRECISION_COMPILER",
          preservedVariables,
          false,
          false);
    }
  }

  record Rejection(
      int sourceEdgeOccurrence, int edgeOccurrence, RejectionReason reason, String detail) {}

  record Result(
      ImmutableList<Candidate> candidates,
      ImmutableList<Rejection> rejections,
      String canonicalDump,
      String sha256,
      ObjectNode dump) {

    ImmutableList<ValidatedPredicate> validatedPredicates() {
      return candidates.stream().map(Candidate::validated).collect(ImmutableList.toImmutableList());
    }
  }

  private record CandidateKey(CFANode node, String formula) {}

  private static final class CandidateAccumulator {
    private final BooleanFormula formula;
    private final CFANode head;
    private final String canonicalFormula;
    private final ImmutableList<String> variables;
    private final List<Origin> origins = new ArrayList<>();

    CandidateAccumulator(
        BooleanFormula pFormula,
        CFANode pHead,
        String pCanonicalFormula,
        ImmutableList<String> pVariables) {
      formula = pFormula;
      head = pHead;
      canonicalFormula = pCanonicalFormula;
      variables = pVariables;
    }

    Candidate build() {
      origins.sort(
          Comparator.comparing(Origin::sourceKind)
              .thenComparingInt(Origin::sourceEdgeOccurrence)
              .thenComparingInt(Origin::sourceProofIndex)
              .thenComparingInt(Origin::targetNodeOccurrence));
      boolean hasProjection =
          origins.stream().anyMatch(origin -> origin.sourceKind().equals("PROOF_EQUALITY"));
      return new Candidate(
          formula,
          head,
          canonicalFormula,
          variables,
          new Certificate(
              hasProjection
                  ? "PROOF_GUIDED_EQUALITY_PROJECTION_WITH_SCALAR_FRAME"
                  : "PATH_PRESERVATION_BY_SCALAR_FRAME",
              ImmutableList.copyOf(origins)));
    }
  }

  private record Guard(BooleanFormula formula, ImmutableSet<MemoryLocation> support) {}

  private record EqualityOperands(Formula lhs, Formula rhs) {}

  private record AssignmentProjection(
      int proofIndex,
      int proofNodeOccurrence,
      int assignmentEdgeOccurrence,
      CFAEdge assignmentEdge,
      BooleanFormula sourceAssignmentEquality,
      BooleanFormula proofEquality,
      BooleanFormula projectedAssignmentEquality,
      BooleanFormula projectedProofEquality,
      Formula lhs,
      Formula rhs,
      ImmutableSet<MemoryLocation> support,
      boolean signed,
      int bitWidth) {}

  private final PathFormulaManager pfmgr;
  private final FormulaManagerView fmgr;
  private final Solver solver;
  private final MachineModel machineModel;
  private final ImmutableSet<CFANode> loopHeads;
  private final EdgeDefUseData.CachingExtractor defUseExtractor =
      new EdgeDefUseData.CachingExtractor(EdgeDefUseData.createExtractor(true));

  CfaPrecisionCompiler(
      PathFormulaManager pPfmgr,
      FormulaManagerView pFormulaManager,
      LoopHeadIndex pLoopHeadIndex,
      Solver pSolver,
      MachineModel pMachineModel) {
    pfmgr = pPfmgr;
    fmgr = pFormulaManager;
    solver = pSolver;
    machineModel = pMachineModel;
    loopHeads =
        pLoopHeadIndex.getLoopHeads().stream()
            .map(LoopHeadInfo::node)
            .collect(ImmutableSet.toImmutableSet());
  }

  Result compile(ARGPath path) throws InterruptedException {
    return compile(path, ImmutableList.of(), ImmutableList.of(), -1);
  }

  Result compile(ARGPath path, List<ARGState> abstractionStates, List<BooleanFormula> interpolants)
      throws InterruptedException {
    return compile(path, abstractionStates, interpolants, -1);
  }

  Result compile(
      ARGPath path,
      List<ARGState> abstractionStates,
      BlockFormulas blockFormulas,
      List<BooleanFormula> interpolants)
      throws InterruptedException {
    return compile(path, abstractionStates, interpolants, blockFormulas.getSize());
  }

  private Result compile(
      ARGPath path,
      List<ARGState> abstractionStates,
      List<BooleanFormula> interpolants,
      int blockFormulaCount)
      throws InterruptedException {
    List<CFAEdge> edges = path.getFullPath();
    List<Rejection> rejections = new ArrayList<>();
    if (edges.isEmpty() && !path.getInnerEdges().isEmpty()) {
      rejections.add(
          new Rejection(
              -1, -1, RejectionReason.UNRESOLVED_ARGPATH_HOLE, "ARGPath.getFullPath() is empty"));
      return result(ImmutableMap.of(), rejections);
    }

    Map<CandidateKey, CandidateAccumulator> candidates = new LinkedHashMap<>();
    compileTakenGuards(edges, candidates, rejections);
    compileProofEqualities(
        edges, abstractionStates, interpolants, blockFormulaCount, candidates, rejections);
    return result(candidates, rejections);
  }

  private void compileTakenGuards(
      List<CFAEdge> edges,
      Map<CandidateKey, CandidateAccumulator> candidates,
      List<Rejection> rejections)
      throws InterruptedException {
    for (int sourceIndex = 0; sourceIndex < edges.size(); sourceIndex++) {
      if (!(edges.get(sourceIndex) instanceof CAssumeEdge assume)) {
        continue;
      }
      Guard guard = convertGuard(assume, sourceIndex, rejections);
      if (guard == null) {
        continue;
      }
      String sourceFunction = assume.getPredecessor().getFunctionName();
      String canonicalFormula = canonicalFormula(guard.formula());
      ImmutableList<String> variables =
          guard.support().stream()
              .map(MemoryLocation::getExtendedQualifiedName)
              .sorted()
              .collect(ImmutableList.toImmutableList());
      Set<MemoryLocation> accumulatedMayDefs = new TreeSet<>();

      for (int targetOccurrence = sourceIndex + 1;
          targetOccurrence <= edges.size();
          targetOccurrence++) {
        int transportEdgeIndex = targetOccurrence - 1;
        if (transportEdgeIndex > sourceIndex) {
          CFAEdge transportEdge = edges.get(transportEdgeIndex);
          RejectionReason barrier =
              barrier(transportEdge, sourceFunction, guard.support(), accumulatedMayDefs);
          if (barrier != null) {
            rejections.add(
                new Rejection(
                    sourceIndex,
                    transportEdgeIndex,
                    barrier,
                    "transport stopped at e[" + transportEdgeIndex + "]"));
            break;
          }
        }
        CFANode target = edges.get(targetOccurrence - 1).getSuccessor();
        if (!loopHeads.contains(target)) {
          continue;
        }
        CandidateKey key = new CandidateKey(target, canonicalFormula);
        CandidateAccumulator candidate =
            candidates.computeIfAbsent(
                key,
                unused ->
                    new CandidateAccumulator(guard.formula(), target, canonicalFormula, variables));
        candidate.origins.add(
            new Origin(
                "TAKEN_ASSUME_EDGE",
                sourceIndex,
                -1,
                sourceIndex + 1,
                assume.getPredecessor().getNodeNumber(),
                assume.getSuccessor().getNodeNumber(),
                targetOccurrence,
                target.getNodeNumber(),
                sourceIndex + 1,
                targetOccurrence,
                accumulatedMayDefs.stream()
                    .map(MemoryLocation::getExtendedQualifiedName)
                    .sorted()
                    .collect(ImmutableList.toImmutableList()),
                "IDENTITY_FRAME",
                "",
                canonicalFormula,
                "",
                "",
                "IDENTITY",
                false,
                -1,
                true,
                true));
      }
    }
  }

  private void compileProofEqualities(
      List<CFAEdge> edges,
      List<ARGState> abstractionStates,
      List<BooleanFormula> interpolants,
      int blockFormulaCount,
      Map<CandidateKey, CandidateAccumulator> candidates,
      List<Rejection> rejections)
      throws InterruptedException {
    if (abstractionStates.isEmpty() && interpolants.isEmpty()) {
      return;
    }
    if (abstractionStates.size() < interpolants.size()
        || abstractionStates.size() > interpolants.size() + 1
        || (blockFormulaCount >= 0 && abstractionStates.size() != blockFormulaCount)) {
      rejections.add(
          new Rejection(
              -1,
              -1,
              RejectionReason.PROOF_TRACE_ALIGNMENT_MISMATCH,
              "states="
                  + abstractionStates.size()
                  + ", blocks="
                  + blockFormulaCount
                  + ", interpolants="
                  + interpolants.size()));
      return;
    }

    Map<String, Set<CSimpleDeclaration>> declarations = declarationsOnPath(edges);
    int nextOccurrence = 0;
    List<Integer> proofOccurrences = new ArrayList<>(interpolants.size());
    for (int proofIndex = 0; proofIndex < interpolants.size(); proofIndex++) {
      CFANode proofNode = extractLocation(abstractionStates.get(proofIndex));
      int proofOccurrence = findNodeOccurrence(edges, proofNode, nextOccurrence);
      if (proofOccurrence < 0) {
        rejections.add(
            new Rejection(
                -1,
                -1,
                RejectionReason.PROOF_TRACE_ALIGNMENT_MISMATCH,
                "interpolant["
                    + proofIndex
                    + "] node="
                    + (proofNode == null ? "null" : "N" + proofNode.getNodeNumber())));
        return;
      }
      proofOccurrences.add(proofOccurrence);
      nextOccurrence = proofOccurrence + 1;
    }
    for (int proofIndex = 0; proofIndex < interpolants.size(); proofIndex++) {
      int proofOccurrence = proofOccurrences.get(proofIndex);
      List<BooleanFormula> atoms =
          fmgr.extractAtoms(interpolants.get(proofIndex), false).stream()
              .sorted(Comparator.comparing(this::canonicalFormula))
              .toList();
      for (BooleanFormula atom : atoms) {
        Optional<EqualityOperands> equality = numeralEquality(atom);
        if (equality.isEmpty()) {
          rejections.add(
              new Rejection(
                  -1,
                  proofOccurrence,
                  RejectionReason.PROOF_ATOM_NOT_NUMERAL_EQUALITY,
                  "interpolant[" + proofIndex + "]: " + canonicalFormula(atom)));
          continue;
        }
        AssignmentProjection projection =
            assignmentProjection(
                edges, proofIndex, proofOccurrence, atom, declarations, rejections);
        if (projection != null) {
          transportProjection(edges, projection, candidates, rejections);
        }
      }
    }
  }

  private AssignmentProjection assignmentProjection(
      List<CFAEdge> edges,
      int proofIndex,
      int proofOccurrence,
      BooleanFormula proofEquality,
      Map<String, Set<CSimpleDeclaration>> declarations,
      List<Rejection> rejections)
      throws InterruptedException {
    BooleanFormula uninstantiatedProof = fmgr.uninstantiate(proofEquality);
    Set<String> proofVariables = new TreeSet<>(fmgr.extractVariableNames(uninstantiatedProof));
    if (proofVariables.isEmpty()) {
      rejections.add(
          proofRejection(
              proofOccurrence,
              RejectionReason.NO_SCALAR_SUPPORT,
              proofIndex,
              canonicalFormula(proofEquality)));
      return null;
    }
    ImmutableSet.Builder<MemoryLocation> supportBuilder = ImmutableSet.builder();
    for (String variable : proofVariables) {
      Set<CSimpleDeclaration> matches = declarations.get(variable);
      if (matches == null || matches.isEmpty()) {
        rejections.add(
            proofRejection(
                proofOccurrence, RejectionReason.UNRESOLVED_PROOF_VARIABLE, proofIndex, variable));
        return null;
      }
      if (matches.size() != 1) {
        rejections.add(
            proofRejection(
                proofOccurrence, RejectionReason.AMBIGUOUS_PROOF_VARIABLE, proofIndex, variable));
        return null;
      }
      CSimpleDeclaration declaration = matches.iterator().next();
      if (!CTypes.isIntegerType(declaration.getType())) {
        rejections.add(
            proofRejection(
                proofOccurrence, RejectionReason.UNSUPPORTED_TYPE, proofIndex, variable));
        return null;
      }
      supportBuilder.add(MemoryLocation.forDeclaration(declaration));
    }
    ImmutableSet<MemoryLocation> support = supportBuilder.build();
    String proofFunction = nodeAt(edges, proofOccurrence).getFunctionName();

    for (int edgeIndex = proofOccurrence - 1; edgeIndex >= 0; edgeIndex--) {
      CFAEdge edge = edges.get(edgeIndex);
      EdgeDefUseData defUse = defUseExtractor.extract(edge);
      if (!edge.getPredecessor().getFunctionName().equals(proofFunction)
          || !edge.getSuccessor().getFunctionName().equals(proofFunction)
          || edge instanceof FunctionCallEdge
          || edge instanceof FunctionReturnEdge
          || edge instanceof FunctionSummaryEdge
          || hasFunctionCall(edge)
          || !defUse.getPointeeDefs().isEmpty()
          || hasPointerDefinition(edge, defUse)
          || defUse.hasPartialDefs()) {
        rejections.add(
            new Rejection(
                edgeIndex,
                edgeIndex,
                RejectionReason.REACHING_DEFINITION_NOT_EXACT_ASSIGNMENT,
                "interpolant[" + proofIndex + "]: unsafe edge before reaching definition"));
        return null;
      }
      if (defUse.getDefs().stream().noneMatch(support::contains)) {
        continue;
      }
      return projectFromAssignment(
          edgeIndex,
          edge,
          proofIndex,
          proofOccurrence,
          proofEquality,
          uninstantiatedProof,
          support,
          defUse,
          rejections);
    }
    rejections.add(
        proofRejection(
            proofOccurrence,
            RejectionReason.NO_REACHING_DEFINITION,
            proofIndex,
            canonicalFormula(proofEquality)));
    return null;
  }

  private AssignmentProjection projectFromAssignment(
      int edgeIndex,
      CFAEdge edge,
      int proofIndex,
      int proofOccurrence,
      BooleanFormula proofEquality,
      BooleanFormula uninstantiatedProof,
      ImmutableSet<MemoryLocation> support,
      EdgeDefUseData defUse,
      List<Rejection> rejections)
      throws InterruptedException {
    String lhsName = CFAEdgeUtils.getLeftHandVariable(edge);
    if (defUse.getDefs().size() != 1
        || lhsName == null
        || CFAEdgeUtils.getRightHandSide(edge) == null
        || !support.contains(MemoryLocation.fromQualifiedName(lhsName))) {
      rejections.add(
          assignmentRejection(
              edgeIndex,
              proofIndex,
              RejectionReason.REACHING_DEFINITION_NOT_EXACT_ASSIGNMENT,
              edge.getRawStatement()));
      return null;
    }
    if (!(CFAEdgeUtils.getLeftHandType(edge) instanceof CType lhsType)
        || !(lhsType.getCanonicalType() instanceof CSimpleType simpleType)
        || !CTypes.isIntegerType(simpleType)) {
      rejections.add(
          assignmentRejection(
              edgeIndex, proofIndex, RejectionReason.UNSUPPORTED_TYPE, edge.getRawStatement()));
      return null;
    }

    PathFormula relation;
    try {
      relation = pfmgr.makeAnd(pfmgr.makeEmptyPathFormula(), edge);
    } catch (CPATransferException e) {
      rejections.add(
          assignmentRejection(
              edgeIndex,
              proofIndex,
              RejectionReason.ASSIGNMENT_RELATION_CONVERSION_FAILED,
              e.getClass().getSimpleName()));
      return null;
    }
    String postLhs = FormulaManagerView.instantiateVariableName(lhsName, relation.getSsa());
    Set<String> postVariables = new TreeSet<>();
    relation
        .getSsa()
        .allVariables()
        .forEach(
            variable ->
                postVariables.add(
                    FormulaManagerView.instantiateVariableName(variable, relation.getSsa())));
    List<BooleanFormula> matchingEqualities =
        fmgr.extractAtoms(relation.getFormula(), false).stream()
            .filter(atom -> numeralEquality(atom).isPresent())
            .filter(atom -> fmgr.extractVariableNames(atom).contains(postLhs))
            .filter(atom -> postVariables.containsAll(fmgr.extractVariableNames(atom)))
            .toList();
    if (matchingEqualities.size() != 1) {
      rejections.add(
          assignmentRejection(
              edgeIndex,
              proofIndex,
              RejectionReason.ASSIGNMENT_EQUALITY_NOT_PROJECTABLE,
              "matching_equalities=" + matchingEqualities.size()));
      return null;
    }
    BooleanFormula assignmentEquality = matchingEqualities.getFirst();
    EqualityOperands assignmentOperands = numeralEquality(assignmentEquality).orElseThrow();
    Formula assignmentLhs;
    Formula assignmentRhs;
    if (isVariableNamed(assignmentOperands.lhs(), postLhs)) {
      assignmentLhs = assignmentOperands.lhs();
      assignmentRhs = assignmentOperands.rhs();
    } else if (isVariableNamed(assignmentOperands.rhs(), postLhs)) {
      assignmentLhs = assignmentOperands.rhs();
      assignmentRhs = assignmentOperands.lhs();
    } else {
      rejections.add(
          assignmentRejection(
              edgeIndex,
              proofIndex,
              RejectionReason.ASSIGNMENT_EQUALITY_NOT_PROJECTABLE,
              "post-state lhs is not an equality operand"));
      return null;
    }
    Formula lhs = fmgr.uninstantiate(assignmentLhs);
    Formula rhs = fmgr.uninstantiate(assignmentRhs);
    FormulaType<?> formulaType = fmgr.getFormulaType(lhs);
    int bitWidth = machineModel.getSizeofInBits(simpleType);
    if (!formulaType.isIntegerType()
        && (!(formulaType instanceof FormulaType.BitvectorType bitvectorType)
            || bitvectorType.getSize() != bitWidth)) {
      rejections.add(
          assignmentRejection(
              edgeIndex,
              proofIndex,
              RejectionReason.ASSIGNMENT_TYPE_WIDTH_MISMATCH,
              "formula_type=" + formulaType + ", c_width=" + bitWidth));
      return null;
    }

    BooleanFormula uninstantiatedAssignment = fmgr.uninstantiate(assignmentEquality);
    boolean equivalent;
    try {
      equivalent =
          solver.implies(uninstantiatedAssignment, uninstantiatedProof)
              && solver.implies(uninstantiatedProof, uninstantiatedAssignment);
    } catch (SolverException e) {
      rejections.add(
          assignmentRejection(
              edgeIndex,
              proofIndex,
              RejectionReason.SOLVER_CHECK_FAILED,
              e.getClass().getSimpleName()));
      return null;
    }
    if (!equivalent) {
      rejections.add(
          assignmentRejection(
              edgeIndex,
              proofIndex,
              RejectionReason.ASSIGNMENT_PROOF_NOT_EQUIVALENT,
              canonicalFormula(uninstantiatedAssignment)
                  + " != "
                  + canonicalFormula(uninstantiatedProof)));
      return null;
    }

    boolean signed = machineModel.isSigned(simpleType);
    BooleanFormula lessOrEqual = fmgr.makeLessOrEqual(lhs, rhs, signed);
    BooleanFormula greaterOrEqual = fmgr.makeGreaterOrEqual(lhs, rhs, signed);
    try {
      if (!solver.implies(uninstantiatedProof, lessOrEqual)
          || !solver.implies(uninstantiatedProof, greaterOrEqual)) {
        rejections.add(
            assignmentRejection(
                edgeIndex,
                proofIndex,
                RejectionReason.PROJECTION_NOT_IMPLIED,
                canonicalFormula(uninstantiatedProof)));
        return null;
      }
    } catch (SolverException e) {
      rejections.add(
          assignmentRejection(
              edgeIndex,
              proofIndex,
              RejectionReason.SOLVER_CHECK_FAILED,
              e.getClass().getSimpleName()));
      return null;
    }
    return new AssignmentProjection(
        proofIndex,
        proofOccurrence,
        edgeIndex,
        edge,
        assignmentEquality,
        proofEquality,
        uninstantiatedAssignment,
        uninstantiatedProof,
        lhs,
        rhs,
        support,
        signed,
        bitWidth);
  }

  private void transportProjection(
      List<CFAEdge> edges,
      AssignmentProjection projection,
      Map<CandidateKey, CandidateAccumulator> candidates,
      List<Rejection> rejections) {
    String sourceFunction = nodeAt(edges, projection.proofNodeOccurrence()).getFunctionName();
    Set<MemoryLocation> accumulatedMayDefs = new TreeSet<>();
    for (int targetOccurrence = projection.proofNodeOccurrence();
        targetOccurrence <= edges.size();
        targetOccurrence++) {
      if (targetOccurrence > projection.proofNodeOccurrence()) {
        int transportEdgeIndex = targetOccurrence - 1;
        RejectionReason barrier =
            barrier(
                edges.get(transportEdgeIndex),
                sourceFunction,
                projection.support(),
                accumulatedMayDefs);
        if (barrier != null) {
          rejections.add(
              new Rejection(
                  projection.assignmentEdgeOccurrence(),
                  transportEdgeIndex,
                  barrier,
                  "proof equality transport stopped at e[" + transportEdgeIndex + "]"));
          break;
        }
      }
      CFANode target = nodeAt(edges, targetOccurrence);
      if (!loopHeads.contains(target)) {
        continue;
      }
      addProjectionCandidate(
          projection,
          fmgr.makeLessOrEqual(projection.lhs(), projection.rhs(), projection.signed()),
          "LESS_OR_EQUAL",
          targetOccurrence,
          target,
          accumulatedMayDefs,
          candidates);
      addProjectionCandidate(
          projection,
          fmgr.makeGreaterOrEqual(projection.lhs(), projection.rhs(), projection.signed()),
          "GREATER_OR_EQUAL",
          targetOccurrence,
          target,
          accumulatedMayDefs,
          candidates);
    }
  }

  private void addProjectionCandidate(
      AssignmentProjection projection,
      BooleanFormula formula,
      String direction,
      int targetOccurrence,
      CFANode target,
      Set<MemoryLocation> accumulatedMayDefs,
      Map<CandidateKey, CandidateAccumulator> candidates) {
    String canonical = canonicalFormula(formula);
    ImmutableList<String> variables =
        projection.support().stream()
            .map(MemoryLocation::getExtendedQualifiedName)
            .sorted()
            .collect(ImmutableList.toImmutableList());
    CandidateAccumulator candidate =
        candidates.computeIfAbsent(
            new CandidateKey(target, canonical),
            unused -> new CandidateAccumulator(formula, target, canonical, variables));
    candidate.origins.add(
        new Origin(
            "PROOF_EQUALITY",
            projection.assignmentEdgeOccurrence(),
            projection.proofIndex(),
            projection.proofNodeOccurrence(),
            projection.assignmentEdge().getPredecessor().getNodeNumber(),
            projection.assignmentEdge().getSuccessor().getNodeNumber(),
            targetOccurrence,
            target.getNodeNumber(),
            projection.proofNodeOccurrence(),
            targetOccurrence,
            accumulatedMayDefs.stream()
                .map(MemoryLocation::getExtendedQualifiedName)
                .sorted()
                .collect(ImmutableList.toImmutableList()),
            "EQUALITY_ORDER_PROJECTION_THEN_IDENTITY_FRAME",
            canonicalFormula(projection.sourceAssignmentEquality()),
            canonicalFormula(projection.proofEquality()),
            canonicalFormula(projection.projectedAssignmentEquality()),
            canonicalFormula(projection.projectedProofEquality()),
            direction,
            projection.signed(),
            projection.bitWidth(),
            true,
            true));
  }

  private Optional<EqualityOperands> numeralEquality(BooleanFormula formula) {
    return fmgr.visit(
        formula,
        new DefaultFormulaVisitor<>() {
          @Override
          protected Optional<EqualityOperands> visitDefault(Formula f) {
            return Optional.empty();
          }

          @Override
          public Optional<EqualityOperands> visitFunction(
              Formula f, List<Formula> args, FunctionDeclaration<?> declaration) {
            if ((declaration.getKind() == FunctionDeclarationKind.EQ
                    || declaration.getKind() == FunctionDeclarationKind.BV_EQ)
                && args.size() == 2
                && isSupportedEqualityType(fmgr.getFormulaType(args.getFirst()))) {
              return Optional.of(new EqualityOperands(args.getFirst(), args.get(1)));
            }
            if (declaration.getKind() == FunctionDeclarationKind.EQ_ZERO
                && args.size() == 1
                && isSupportedEqualityType(fmgr.getFormulaType(args.getFirst()))) {
              return Optional.of(
                  new EqualityOperands(
                      args.getFirst(), fmgr.makeNumber(fmgr.getFormulaType(args.getFirst()), 0)));
            }
            return Optional.empty();
          }
        });
  }

  private static boolean isSupportedEqualityType(FormulaType<?> type) {
    return type.isIntegerType() || type.isBitvectorType();
  }

  private boolean isVariableNamed(Formula formula, String expectedName) {
    return fmgr.visit(
        formula,
        new DefaultFormulaVisitor<>() {
          @Override
          protected Boolean visitDefault(Formula f) {
            return false;
          }

          @Override
          public Boolean visitFreeVariable(Formula f, String name) {
            return name.equals(expectedName);
          }
        });
  }

  private static Rejection proofRejection(
      int proofOccurrence, RejectionReason reason, int proofIndex, String detail) {
    return new Rejection(-1, proofOccurrence, reason, "interpolant[" + proofIndex + "]: " + detail);
  }

  private static Rejection assignmentRejection(
      int edgeIndex, int proofIndex, RejectionReason reason, String detail) {
    return new Rejection(
        edgeIndex, edgeIndex, reason, "interpolant[" + proofIndex + "]: " + detail);
  }

  private static int findNodeOccurrence(List<CFAEdge> edges, CFANode target, int startOccurrence) {
    if (target == null || edges.isEmpty()) {
      return -1;
    }
    for (int occurrence = startOccurrence; occurrence <= edges.size(); occurrence++) {
      if (nodeAt(edges, occurrence).equals(target)) {
        return occurrence;
      }
    }
    return -1;
  }

  private static CFANode nodeAt(List<CFAEdge> edges, int occurrence) {
    return occurrence == 0
        ? edges.getFirst().getPredecessor()
        : edges.get(occurrence - 1).getSuccessor();
  }

  private static Map<String, Set<CSimpleDeclaration>> declarationsOnPath(List<CFAEdge> edges) {
    Map<String, Set<CSimpleDeclaration>> declarations = new LinkedHashMap<>();
    for (CFAEdge edge : edges) {
      for (AAstNode root : CFAUtils.getAstNodesFromCfaEdge(edge)) {
        if (root instanceof CSimpleDeclaration declaration
            && (declaration instanceof CVariableDeclaration
                || declaration instanceof CParameterDeclaration)) {
          declarations
              .computeIfAbsent(declaration.getQualifiedName(), unused -> new LinkedHashSet<>())
              .add(declaration);
        }
        if (root instanceof CAstNode cRoot) {
          for (CIdExpression id : CFAUtils.traverseRecursively(cRoot).filter(CIdExpression.class)) {
            CSimpleDeclaration declaration = id.getDeclaration();
            if (declaration instanceof CVariableDeclaration
                || declaration instanceof CParameterDeclaration) {
              declarations
                  .computeIfAbsent(declaration.getQualifiedName(), unused -> new LinkedHashSet<>())
                  .add(declaration);
            }
          }
        }
      }
    }
    return declarations;
  }

  private Guard convertGuard(CAssumeEdge assume, int sourceIndex, List<Rejection> rejections)
      throws InterruptedException {
    Set<MemoryLocation> support = new TreeSet<>();
    for (CIdExpression id : CFAUtils.getCIdExpressionsOfExpression(assume.getExpression())) {
      CSimpleDeclaration declaration = id.getDeclaration();
      if (declaration == null) {
        rejections.add(
            new Rejection(
                sourceIndex,
                sourceIndex,
                RejectionReason.UNSUPPORTED_DECLARATION,
                id.toASTString()));
        return null;
      }
      if (!(declaration instanceof CVariableDeclaration)
          && !(declaration instanceof CParameterDeclaration)) {
        rejections.add(
            new Rejection(
                sourceIndex,
                sourceIndex,
                RejectionReason.UNSUPPORTED_DECLARATION,
                declaration.getQualifiedName()));
        return null;
      }
      if (!CTypes.isIntegerType(declaration.getType())) {
        rejections.add(
            new Rejection(
                sourceIndex,
                sourceIndex,
                RejectionReason.UNSUPPORTED_TYPE,
                declaration.getQualifiedName()));
        return null;
      }
      support.add(MemoryLocation.forDeclaration(declaration));
    }
    if (support.isEmpty()) {
      rejections.add(
          new Rejection(
              sourceIndex,
              sourceIndex,
              RejectionReason.NO_SCALAR_SUPPORT,
              "taken assume has no supported scalar declaration"));
      return null;
    }

    BooleanFormula formula;
    try {
      formula =
          fmgr.uninstantiate(pfmgr.makeAnd(pfmgr.makeEmptyPathFormula(), assume).getFormula());
    } catch (CPATransferException e) {
      rejections.add(
          new Rejection(
              sourceIndex,
              sourceIndex,
              RejectionReason.ASSUME_FORMULA_CONVERSION_FAILED,
              e.getClass().getSimpleName()));
      return null;
    }
    Set<String> formulaSupport = new TreeSet<>(fmgr.extractVariableNames(formula));
    Set<String> declarationSupport = new TreeSet<>();
    support.forEach(location -> declarationSupport.add(location.getExtendedQualifiedName()));
    if (!formulaSupport.equals(declarationSupport)) {
      rejections.add(
          new Rejection(
              sourceIndex,
              sourceIndex,
              RejectionReason.FORMULA_SUPPORT_MISMATCH,
              "formula=" + formulaSupport + ", declarations=" + declarationSupport));
      return null;
    }
    return new Guard(formula, ImmutableSet.copyOf(support));
  }

  private RejectionReason barrier(
      CFAEdge edge,
      String sourceFunction,
      ImmutableSet<MemoryLocation> support,
      Set<MemoryLocation> accumulatedMayDefs) {
    if (!edge.getPredecessor().getFunctionName().equals(sourceFunction)
        || !edge.getSuccessor().getFunctionName().equals(sourceFunction)
        || edge instanceof FunctionCallEdge
        || edge instanceof FunctionReturnEdge
        || edge instanceof FunctionSummaryEdge) {
      return RejectionReason.CROSS_FUNCTION_SEGMENT;
    }
    if (hasFunctionCall(edge)) {
      return RejectionReason.UNKNOWN_CALL_EFFECT;
    }
    EdgeDefUseData defUse = defUseExtractor.extract(edge);
    if (!defUse.getPointeeDefs().isEmpty() || hasPointerDefinition(edge, defUse)) {
      return RejectionReason.POINTER_OR_POINTEE_WRITE;
    }
    if (defUse.hasPartialDefs()) {
      return RejectionReason.PARTIAL_DEFINITION;
    }
    if (defUse.getDefs().stream().anyMatch(support::contains)) {
      return RejectionReason.REFERENCED_VARIABLE_KILLED;
    }
    accumulatedMayDefs.addAll(defUse.getDefs());
    return null;
  }

  private static boolean hasFunctionCall(CFAEdge edge) {
    for (AAstNode root : CFAUtils.getAstNodesFromCfaEdge(edge)) {
      if (root instanceof CFunctionCall
          || (root instanceof CAstNode cRoot
              && !CFAUtils.traverseRecursively(cRoot)
                  .filter(CFunctionCallExpression.class)
                  .isEmpty())) {
        return true;
      }
    }
    return false;
  }

  private static boolean hasPointerDefinition(CFAEdge edge, EdgeDefUseData defUse) {
    for (AAstNode root : CFAUtils.getAstNodesFromCfaEdge(edge)) {
      if (root instanceof CVariableDeclaration declaration
          && declaration.getType().getCanonicalType() instanceof CPointerType
          && defUse.getDefs().contains(MemoryLocation.forDeclaration(declaration))) {
        return true;
      }
      if (!(root instanceof CAstNode cRoot)) {
        continue;
      }
      for (CIdExpression id : CFAUtils.traverseRecursively(cRoot).filter(CIdExpression.class)) {
        CSimpleDeclaration declaration = id.getDeclaration();
        if ((declaration instanceof CVariableDeclaration
                || declaration instanceof CParameterDeclaration)
            && declaration.getType().getCanonicalType() instanceof CPointerType
            && defUse.getDefs().contains(MemoryLocation.forDeclaration(declaration))) {
          return true;
        }
      }
    }
    return false;
  }

  private Result result(
      Map<CandidateKey, CandidateAccumulator> candidateMap, List<Rejection> rejectionList) {
    ImmutableList<Candidate> candidates =
        candidateMap.values().stream()
            .map(CandidateAccumulator::build)
            .sorted(
                Comparator.comparingInt((Candidate c) -> c.loopHead().getNodeNumber())
                    .thenComparing(Candidate::canonicalFormula))
            .collect(ImmutableList.toImmutableList());
    ImmutableList<Rejection> rejections =
        rejectionList.stream()
            .sorted(
                Comparator.comparingInt(Rejection::sourceEdgeOccurrence)
                    .thenComparingInt(Rejection::edgeOccurrence)
                    .thenComparing(r -> r.reason().name())
                    .thenComparing(Rejection::detail))
            .collect(ImmutableList.toImmutableList());
    ObjectNode payload = JSON.createObjectNode();
    payload.put("schema_version", SCHEMA_VERSION);
    payload.put("mode", "CONSERVATIVE_SCALAR_FRAME_WITH_PROOF_EQUALITY_PROJECTION");
    payload.set("candidates", candidatesJson(candidates));
    payload.set("rejections", rejectionsJson(rejections));
    try {
      String hash =
          Hashing.sha256()
              .hashString(JSON.writeValueAsString(payload), StandardCharsets.UTF_8)
              .toString();
      payload.put("sha256", hash);
      return new Result(
          candidates, rejections, JSON.writeValueAsString(payload), hash, payload.deepCopy());
    } catch (JsonProcessingException e) {
      throw new AssertionError("Jackson failed to serialize in-memory compiler data", e);
    }
  }

  private static ArrayNode candidatesJson(List<Candidate> candidates) {
    ArrayNode array = JSON.createArrayNode();
    for (Candidate candidate : candidates) {
      ObjectNode item = array.addObject();
      Set<String> sourceKinds =
          candidate.certificate().origins().stream()
              .map(Origin::sourceKind)
              .collect(java.util.stream.Collectors.toCollection(TreeSet::new));
      item.put("origin", sourceKinds.size() == 1 ? sourceKinds.iterator().next() : "MULTIPLE");
      ObjectNode path = item.putObject("path_or_region");
      path.put("kind", "ARGPATH_FULL");
      ArrayNode occurrences = path.putArray("target_node_occurrences");
      candidate.certificate().origins().stream()
          .map(Origin::targetNodeOccurrence)
          .distinct()
          .sorted()
          .forEach(occurrences::add);
      item.put("antecedent_formula", candidate.canonicalFormula());
      item.put("consequent_head", "N" + candidate.loopHead().getNodeNumber());
      ArrayNode variables = item.putArray("preserved_variables");
      candidate.preservedVariables().forEach(variables::add);
      item.put(
          "transport_relation",
          sourceKinds.contains("PROOF_EQUALITY")
              ? "EQUALITY_ORDER_PROJECTION_THEN_IDENTITY_FRAME"
              : "IDENTITY_FRAME");
      ObjectNode certificate = item.putObject("certificate");
      certificate.put("semantics", candidate.certificate().semantics());
      certificate.put("rule", "SUPPORT_INTERSECT_MAY_DEF_EMPTY");
      ArrayNode origins = certificate.putArray("origins");
      for (Origin origin : candidate.certificate().origins()) {
        ObjectNode row = origins.addObject();
        row.put("source_kind", origin.sourceKind());
        row.put("source_edge_occurrence", origin.sourceEdgeOccurrence());
        row.put("source_proof_index", origin.sourceProofIndex());
        row.put("source_node_occurrence", origin.sourceNodeOccurrence());
        row.put("source_predecessor_node", origin.sourcePredecessorNode());
        row.put("source_successor_node", origin.sourceSuccessorNode());
        row.put("target_node_occurrence", origin.targetNodeOccurrence());
        row.put("target_node", origin.targetNode());
        row.put(
            "transport_start_edge_occurrence_inclusive",
            origin.transportStartEdgeOccurrenceInclusive());
        row.put(
            "transport_end_edge_occurrence_exclusive",
            origin.transportEndEdgeOccurrenceExclusive());
        ArrayNode mayDefs = row.putArray("direct_may_defs");
        origin.directMayDefs().forEach(mayDefs::add);
        row.put("derivation", origin.derivation());
        row.put("source_assignment_equality", origin.sourceAssignmentEquality());
        row.put("proof_equality", origin.proofEquality());
        row.put("projected_assignment_equality", origin.projectedAssignmentEquality());
        row.put("projected_proof_equality", origin.projectedProofEquality());
        row.put("comparison_direction", origin.comparisonDirection());
        row.put("signed", origin.signed());
        row.put("bit_width", origin.bitWidth());
        row.put("assignment_proof_equivalent", origin.assignmentProofEquivalent());
        row.put("proof_implies_candidate", origin.proofImpliesCandidate());
      }
      item.put("abstraction_role", ValidatedPredicate.Classification.PRECISION_ONLY.name());
      item.putNull("estimated_cost");
    }
    return array;
  }

  private static ArrayNode rejectionsJson(List<Rejection> rejections) {
    ArrayNode array = JSON.createArrayNode();
    for (Rejection rejection : rejections) {
      ObjectNode row = array.addObject();
      row.put("source_edge_occurrence", rejection.sourceEdgeOccurrence());
      row.put("edge_occurrence", rejection.edgeOccurrence());
      row.put("reason", rejection.reason().name());
      row.put("detail", rejection.detail());
    }
    return array;
  }

  private String canonicalFormula(BooleanFormula formula) {
    return fmgr.dumpFormula(formula)
        .toString()
        .lines()
        .map(String::strip)
        .filter(line -> !line.isEmpty())
        .collect(java.util.stream.Collectors.joining(" "));
  }
}
