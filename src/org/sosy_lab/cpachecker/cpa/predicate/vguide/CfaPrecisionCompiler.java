// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

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
import java.util.List;
import java.util.Map;
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
import org.sosy_lab.cpachecker.cfa.types.c.CPointerType;
import org.sosy_lab.cpachecker.cfa.types.c.CTypes;
import org.sosy_lab.cpachecker.cpa.arg.path.ARGPath;
import org.sosy_lab.cpachecker.exceptions.CPATransferException;
import org.sosy_lab.cpachecker.util.CFAUtils;
import org.sosy_lab.cpachecker.util.dependencegraph.EdgeDefUseData;
import org.sosy_lab.cpachecker.util.predicates.pathformula.PathFormulaManager;
import org.sosy_lab.cpachecker.util.predicates.smt.FormulaManagerView;
import org.sosy_lab.cpachecker.util.states.MemoryLocation;
import org.sosy_lab.java_smt.api.BooleanFormula;

/** Compiles taken scalar guards on one ARG path into local predicate-precision entries. */
final class CfaPrecisionCompiler {

  static final String SCHEMA_VERSION = "cfa-precision-compiler-v1";
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
    REFERENCED_VARIABLE_KILLED
  }

  record Origin(
      int sourceEdgeOccurrence,
      int targetNodeOccurrence,
      int transportStartEdgeOccurrence,
      int transportEndEdgeOccurrence) {}

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
          "CFA_NATIVE_FRAME_TRANSPORT",
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
          Comparator.comparingInt(Origin::sourceEdgeOccurrence)
              .thenComparingInt(Origin::targetNodeOccurrence));
      return new Candidate(
          formula,
          head,
          canonicalFormula,
          variables,
          new Certificate("PATH_PRESERVATION_BY_SCALAR_FRAME", ImmutableList.copyOf(origins)));
    }
  }

  private record Guard(BooleanFormula formula, ImmutableSet<MemoryLocation> support) {}

  private final PathFormulaManager pfmgr;
  private final FormulaManagerView fmgr;
  private final ImmutableSet<CFANode> loopHeads;
  private final EdgeDefUseData.CachingExtractor defUseExtractor =
      new EdgeDefUseData.CachingExtractor(EdgeDefUseData.createExtractor(true));

  CfaPrecisionCompiler(
      PathFormulaManager pPfmgr, FormulaManagerView pFormulaManager, LoopHeadIndex pLoopHeadIndex) {
    pfmgr = pPfmgr;
    fmgr = pFormulaManager;
    loopHeads =
        pLoopHeadIndex.getLoopHeads().stream()
            .map(LoopHeadInfo::node)
            .collect(ImmutableSet.toImmutableSet());
  }

  Result compile(ARGPath path) throws InterruptedException {
    List<CFAEdge> edges = path.getFullPath();
    List<Rejection> rejections = new ArrayList<>();
    if (edges.isEmpty() && !path.getInnerEdges().isEmpty()) {
      rejections.add(
          new Rejection(
              -1, -1, RejectionReason.UNRESOLVED_ARGPATH_HOLE, "ARGPath.getFullPath() is empty"));
      return result(ImmutableMap.of(), rejections);
    }

    Map<CandidateKey, CandidateAccumulator> candidates = new LinkedHashMap<>();
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

      for (int targetOccurrence = sourceIndex + 1;
          targetOccurrence <= edges.size();
          targetOccurrence++) {
        int transportEdgeIndex = targetOccurrence - 1;
        if (transportEdgeIndex > sourceIndex) {
          CFAEdge transportEdge = edges.get(transportEdgeIndex);
          RejectionReason barrier = barrier(transportEdge, sourceFunction, guard.support());
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
            new Origin(sourceIndex, targetOccurrence, sourceIndex + 1, targetOccurrence));
      }
    }
    return result(candidates, rejections);
  }

  private Guard convertGuard(CAssumeEdge assume, int sourceIndex, List<Rejection> rejections)
      throws InterruptedException {
    Set<MemoryLocation> support = new TreeSet<>();
    for (CIdExpression id : CFAUtils.getCIdExpressionsOfExpression(assume.getExpression())) {
      CSimpleDeclaration declaration = id.getDeclaration();
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
      CFAEdge edge, String sourceFunction, ImmutableSet<MemoryLocation> support) {
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
    payload.put("mode", "CONSERVATIVE_SAME_FUNCTION_SCALAR_FRAME");
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
      item.put("origin", "TAKEN_ASSUME_EDGE");
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
      item.put("transport_relation", "IDENTITY_FRAME");
      ObjectNode certificate = item.putObject("certificate");
      certificate.put("semantics", candidate.certificate().semantics());
      ArrayNode origins = certificate.putArray("origins");
      for (Origin origin : candidate.certificate().origins()) {
        ObjectNode row = origins.addObject();
        row.put("source_edge_occurrence", origin.sourceEdgeOccurrence());
        row.put("target_node_occurrence", origin.targetNodeOccurrence());
        row.put("transport_start_edge_occurrence", origin.transportStartEdgeOccurrence());
        row.put("transport_end_edge_occurrence", origin.transportEndEdgeOccurrence());
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
