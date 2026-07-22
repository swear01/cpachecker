// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-FileCopyrightText: 2026 SSU-WEI HUANG <https://github.com/swear01>
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableMap;
import com.google.common.collect.ImmutableSet;
import java.io.IOException;
import java.math.BigInteger;
import java.util.ArrayDeque;
import java.util.Comparator;
import java.util.Deque;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.sosy_lab.cpachecker.cfa.CFA;
import org.sosy_lab.cpachecker.cfa.ast.c.CSimpleDeclaration;
import org.sosy_lab.cpachecker.cfa.ast.c.CVariableDeclaration;
import org.sosy_lab.cpachecker.cfa.model.CFAEdge;
import org.sosy_lab.cpachecker.cfa.model.CFANode;
import org.sosy_lab.cpachecker.cfa.model.c.CDeclarationEdge;
import org.sosy_lab.cpachecker.cfa.types.c.CBitFieldType;
import org.sosy_lab.cpachecker.cfa.types.c.CEnumType;
import org.sosy_lab.cpachecker.cfa.types.c.CPointerType;
import org.sosy_lab.cpachecker.cfa.types.c.CSimpleType;
import org.sosy_lab.cpachecker.cfa.types.c.CType;
import org.sosy_lab.cpachecker.core.interfaces.AbstractState;
import org.sosy_lab.cpachecker.core.interfaces.Precision;
import org.sosy_lab.cpachecker.cpa.arg.ARGReachedSet;
import org.sosy_lab.cpachecker.cpa.arg.ARGState;
import org.sosy_lab.cpachecker.cpa.arg.path.ARGPath;
import org.sosy_lab.cpachecker.cpa.predicate.PredicatePrecision;
import org.sosy_lab.cpachecker.util.LoopStructure;
import org.sosy_lab.cpachecker.util.Precisions;
import org.sosy_lab.cpachecker.util.predicates.AbstractionManager;
import org.sosy_lab.cpachecker.util.predicates.AbstractionPredicate;
import org.sosy_lab.cpachecker.util.predicates.smt.FormulaManagerView;
import org.sosy_lab.java_smt.api.BooleanFormula;
import org.sosy_lab.java_smt.api.Formula;
import org.sosy_lab.java_smt.api.FormulaType;

final class VGuideAugmentor {

  private static final int MAX_CE_STEPS = 120;
  private static final int MAX_NATIVE_PREDICATES = 200;

  private final AgentPortfolio portfolio;
  private final ImmutableMap<String, CFANode> loopHeads;
  private final ImmutableList<ContextPack.LoopHeadContext> loopHeadContexts;
  private final ImmutableList<ContextPack.VariableContext> allowedVariables;
  private final ImmutableMap<String, Integer> allowedVariableWidths;
  private final AbstractionManager abstractionManager;
  private final FormulaManagerView formulaManager;
  private final int historyLimit;
  private final VGuideStatistics statistics;
  private final PredicateLifecycle lifecycle = new PredicateLifecycle();
  private final Deque<ImmutableList<ContextPack.CounterexampleStep>> history = new ArrayDeque<>();

  VGuideAugmentor(
      AgentPortfolio pPortfolio,
      CFA cfa,
      LoopStructure loopStructure,
      AbstractionManager pAbstractionManager,
      FormulaManagerView pFormulaManager,
      int pHistoryLimit,
      VGuideStatistics pStatistics) {
    portfolio = pPortfolio;
    abstractionManager = pAbstractionManager;
    formulaManager = pFormulaManager;
    historyLimit = pHistoryLimit;
    statistics = pStatistics;
    Map<String, CFANode> heads = new LinkedHashMap<>();
    ImmutableList.Builder<ContextPack.LoopHeadContext> contexts = ImmutableList.builder();
    for (CFANode head : loopStructure.getAllLoopHeads().stream().sorted().toList()) {
      String id = "N" + head.getNodeNumber();
      heads.put(id, head);
      contexts.add(
          new ContextPack.LoopHeadContext(
              id, head.getNodeNumber(), head.getFunctionName(), describeLoop(loopStructure, head)));
    }
    loopHeads = ImmutableMap.copyOf(heads);
    loopHeadContexts = contexts.build();
    allowedVariableWidths = collectVariables(cfa);
    allowedVariables =
        allowedVariableWidths.entrySet().stream()
            .map(
                entry ->
                    new ContextPack.VariableContext(
                        entry.getKey(), "(_ BitVec " + entry.getValue() + ")"))
            .collect(ImmutableList.toImmutableList());
  }

  void augment(
      int refinement,
      ARGReachedSet reached,
      ARGPath path,
      PredicatePrecision precisionBeforeNative,
      PredicatePrecision precisionAfterNative)
      throws IOException, InterruptedException {
    PredicatePrecision nativeBefore = lifecycle.nativeOnly(precisionBeforeNative);
    PredicatePrecision nativeAfter = lifecycle.nativeOnly(precisionAfterNative);
    ImmutableList<ContextPack.CounterexampleStep> currentCounterexample = counterexample(path);
    ContextPack context =
        new ContextPack(
            ContextPack.SCHEMA_VERSION,
            refinement,
            loopHeadContexts,
            currentCounterexample,
            ImmutableList.copyOf(history),
            nativePredicates(nativeAfter),
            new ContextPack.NativeRefinementOutcome(
                true, nativeAfter.calculateDifferenceTo(nativeBefore)),
            allowedVariables);
    AgentPortfolio.PortfolioResult result = portfolio.propose(context);
    ImmutableList<ValidatedCandidate> validated = validate(result.candidates());
    int rejected = result.candidates().size() - validated.size();
    apply(reached, validated);
    statistics.record(refinement, result, validated, rejected);
    if (historyLimit > 0) {
      history.addLast(currentCounterexample);
      while (history.size() > historyLimit) {
        history.removeFirst();
      }
    }
  }

  private ImmutableList<ValidatedCandidate> validate(Iterable<CandidateProposal> candidates) {
    ImmutableList.Builder<ValidatedCandidate> validated = ImmutableList.builder();
    for (CandidateProposal candidate : candidates) {
      CFANode head = loopHeads.get(candidate.loopHeadId());
      if (head == null) {
        continue;
      }
      try {
        AbstractionPredicate predicate = abstractionManager.parsePredicate(candidate.predicate());
        BooleanFormula formula = predicate.getSymbolicAtom();
        if (formulaManager.getBooleanFormulaManager().isTrue(formula)
            || formulaManager.getBooleanFormulaManager().isFalse(formula)
            || !variablesHaveExpectedTypes(formulaManager, allowedVariableWidths, formula)) {
          continue;
        }
        validated.add(new ValidatedCandidate(candidate, head, predicate));
      } catch (IllegalArgumentException e) {
        // Rejection is the verification gate, not a provider fallback.
      }
    }
    return validated.build();
  }

  static boolean variablesHaveExpectedTypes(
      FormulaManagerView formulaManager,
      Map<String, Integer> allowedVariableWidths,
      BooleanFormula formula) {
    Map<String, Formula> variables = formulaManager.extractVariables(formula);
    if (variables.isEmpty()
        || !formulaManager.extractFunctionNames(formula).equals(variables.keySet())
        || !allowedVariableWidths.keySet().containsAll(variables.keySet())) {
      return false;
    }
    for (Map.Entry<String, Formula> variable : variables.entrySet()) {
      FormulaType<?> type = formulaManager.getFormulaType(variable.getValue());
      if (!type.isBitvectorType()
          || ((FormulaType.BitvectorType) type).getSize()
              != allowedVariableWidths.get(variable.getKey())) {
        return false;
      }
    }
    return true;
  }

  private void apply(ARGReachedSet reached, ImmutableList<ValidatedCandidate> validated) {
    List<Map.Entry<CFANode, AbstractionPredicate>> replacements =
        validated.stream()
            .map(candidate -> Map.entry(candidate.loopHead(), candidate.abstractionPredicate()))
            .toList();
    PredicateLifecycle.Replacement replacement = lifecycle.beginReplacement(replacements);
    for (AbstractState state : ImmutableList.copyOf(reached.asReachedSet().asCollection())) {
      Precision compositePrecision = reached.asReachedSet().getPrecision(state);
      PredicatePrecision predicatePrecision =
          Precisions.extractPrecisionByType(compositePrecision, PredicatePrecision.class);
      if (predicatePrecision != null) {
        reached.updatePrecisionForState(
            (ARGState) state,
            replacement.apply(predicatePrecision),
            precision -> precision instanceof PredicatePrecision);
      }
    }
  }

  private ImmutableList<ContextPack.CounterexampleStep> counterexample(ARGPath path) {
    List<CFAEdge> edges = path.getFullPath();
    int start = Math.max(0, edges.size() - MAX_CE_STEPS);
    ImmutableList.Builder<ContextPack.CounterexampleStep> steps = ImmutableList.builder();
    for (CFAEdge edge : edges.subList(start, edges.size())) {
      String loopHeadId = "N" + edge.getSuccessor().getNodeNumber();
      steps.add(
          new ContextPack.CounterexampleStep(
              edge.getPredecessor().getNodeNumber(),
              edge.getSuccessor().getNodeNumber(),
              edge.getEdgeType().name(),
              edge.getCode(),
              loopHeads.containsKey(loopHeadId) ? loopHeadId : ""));
    }
    return steps.build();
  }

  private static String describeLoop(LoopStructure structure, CFANode head) {
    return structure.getLoopsForLoopHead(head).stream()
        .flatMap(loop -> loop.getInnerLoopEdges().stream())
        .sorted(Comparator.comparing(CFAEdge::getDescription))
        .limit(24)
        .map(CFAEdge::getCode)
        .reduce((left, right) -> left + "\n" + right)
        .orElse("");
  }

  static ImmutableMap<String, Integer> collectVariables(CFA cfa) {
    Set<String> relevant =
        cfa.getVarClassification()
            .map(classification -> classification.getRelevantVariables())
            .orElse(ImmutableSet.of());
    Map<String, Integer> variables = new java.util.TreeMap<>();
    for (CFANode node : cfa.nodes()) {
      for (CFAEdge edge : node.getLeavingEdges()) {
        if (edge instanceof CDeclarationEdge declarationEdge
            && declarationEdge.getDeclaration() instanceof CVariableDeclaration variable) {
          addVariable(cfa, relevant, variables, variable);
        }
      }
    }
    cfa.getAllFunctions().values().stream()
        .flatMap(function -> function.getFunctionParameters().stream())
        .filter(CSimpleDeclaration.class::isInstance)
        .map(CSimpleDeclaration.class::cast)
        .forEach(variable -> addVariable(cfa, relevant, variables, variable));
    cfa.getAllFunctions().values().stream()
        .flatMap(function -> function.getReturnVariable().stream())
        .filter(CSimpleDeclaration.class::isInstance)
        .map(CSimpleDeclaration.class::cast)
        .forEach(variable -> addVariable(cfa, relevant, variables, variable));
    return ImmutableMap.copyOf(variables);
  }

  private static void addVariable(
      CFA cfa, Set<String> relevant, Map<String, Integer> variables, CSimpleDeclaration variable) {
    if (!relevant.contains(variable.getQualifiedName())) {
      return;
    }
    CType type = variable.getType().getCanonicalType();
    if (!(type instanceof CSimpleType
        || type instanceof CPointerType
        || type instanceof CEnumType
        || type instanceof CBitFieldType)) {
      return;
    }
    BigInteger width = cfa.getMachineModel().getSizeofInBits(type);
    variables.put(variable.getQualifiedName(), width.intValueExact());
  }

  private static ImmutableList<ContextPack.NativePredicateContext> nativePredicates(
      PredicatePrecision precision) {
    Map<String, ContextPack.NativePredicateContext> unique = new LinkedHashMap<>();
    precision.getGlobalPredicates().stream()
        .limit(MAX_NATIVE_PREDICATES)
        .forEach(
            predicate -> addNative(unique, "global", "*", predicate.getSymbolicAtom().toString()));
    precision.getFunctionPredicates().entries().stream()
        .limit(MAX_NATIVE_PREDICATES)
        .forEach(
            entry ->
                addNative(
                    unique,
                    "function",
                    entry.getKey(),
                    entry.getValue().getSymbolicAtom().toString()));
    precision.getLocalPredicates().entries().stream()
        .limit(MAX_NATIVE_PREDICATES)
        .forEach(
            entry ->
                addNative(
                    unique,
                    "location",
                    "N" + entry.getKey().getNodeNumber(),
                    entry.getValue().getSymbolicAtom().toString()));
    return unique.values().stream()
        .limit(MAX_NATIVE_PREDICATES)
        .collect(ImmutableList.toImmutableList());
  }

  private static void addNative(
      Map<String, ContextPack.NativePredicateContext> contexts,
      String scope,
      String location,
      String predicate) {
    contexts.putIfAbsent(
        scope + "\u0000" + location + "\u0000" + predicate,
        new ContextPack.NativePredicateContext(scope, location, predicate));
  }
}
