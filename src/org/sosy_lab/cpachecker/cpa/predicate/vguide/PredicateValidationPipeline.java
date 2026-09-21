// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static org.sosy_lab.cpachecker.util.AbstractStates.extractLocation;
import static org.sosy_lab.cpachecker.util.AbstractStates.extractStateByType;

import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableMap;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.logging.Level;
import org.checkerframework.checker.nullness.qual.Nullable;
import org.sosy_lab.common.log.LogManager;
import org.sosy_lab.cpachecker.cfa.model.CFANode;
import org.sosy_lab.cpachecker.core.interfaces.AbstractState;
import org.sosy_lab.cpachecker.cpa.predicate.PredicateAbstractState;
import org.sosy_lab.cpachecker.cpa.predicate.VocabularyGuide;
import org.sosy_lab.cpachecker.exceptions.CPATransferException;
import org.sosy_lab.cpachecker.exceptions.CParserException;
import org.sosy_lab.cpachecker.util.predicates.pathformula.PathFormula;
import org.sosy_lab.cpachecker.util.predicates.pathformula.SSAMap;
import org.sosy_lab.cpachecker.util.predicates.smt.FormulaManagerView;
import org.sosy_lab.cpachecker.util.predicates.smt.Solver;
import org.sosy_lab.java_smt.api.BooleanFormula;
import org.sosy_lab.java_smt.api.BooleanFormulaManager;
import org.sosy_lab.java_smt.api.ProverEnvironment;
import org.sosy_lab.java_smt.api.SolverContext.ProverOptions;
import org.sosy_lab.java_smt.api.SolverException;

/**
 * L1 contract + L2 parse + scope check + L3 SMT entailment per named loop head.
 *
 * <p>Mapping policy: a candidate is validated only at the loop heads it names; no implicit
 * broadcast. A named head that does not exist or is not on the spurious trace is recorded as an
 * observable rejection. Every free variable of a candidate must be visible at the named head
 * (encoded vocabulary + function scope); otherwise the head is rejected with {@code
 * variable_not_in_scope}. Candidates with role {@code initiation} are processed before {@code
 * supporting} ones so group-consistency checks see the initiation set first.
 */
public final class PredicateValidationPipeline {

  public static final String REASON_UNKNOWN_LOOP_HEAD = "unknown_loop_head";
  public static final String REASON_HEAD_NOT_ON_TRACE = "head_not_on_trace";
  public static final String REASON_PARSE_ERROR = "parse_error";
  public static final String REASON_NO_SSA_MAP = "no_ssa_map";
  public static final String REASON_CONTRACT_VIOLATION = "contract_violation";
  public static final String REASON_VARIABLE_NOT_IN_SCOPE = "variable_not_in_scope";
  public static final String REASON_UNSUPPORTED_ARRAY_ACCESS = "unsupported_array_access";
  public static final String REASON_NATIVE_CONTEXT_UNAVAILABLE = "native_c_context_unavailable";
  public static final String REASON_NATIVE_REJECTED = "native_c_rejected";

  private static final String ROLE_INITIATION = "initiation";
  private static final String ROLE_SUPPORTING = "supporting";

  private final LogManager logger;
  private final Solver solver;
  private final FormulaManagerView fmgr;
  private final boolean enableL3Entailment;
  private final @Nullable NativeCExpressionEncoder nativeEncoder;

  public PredicateValidationPipeline(
      LogManager logger, Solver solver, FormulaManagerView fmgr, boolean enableL3Entailment) {
    this(logger, solver, fmgr, enableL3Entailment, null);
  }

  PredicateValidationPipeline(
      LogManager logger,
      Solver solver,
      FormulaManagerView fmgr,
      boolean enableL3Entailment,
      @Nullable NativeCExpressionEncoder nativeEncoder) {
    this.nativeEncoder = nativeEncoder;
    this.logger = logger;
    this.solver = solver;
    this.fmgr = fmgr;
    this.enableL3Entailment = enableL3Entailment;
    if (!enableL3Entailment) {
      logger.log(
          Level.INFO,
          "VGuide L3 entailment disabled; all parsed predicates use PRECISION_ONLY and"
              + " group-consistency diagnostics are skipped");
    }
  }

  public record CandidateValidationOutcome(
      ValidationResult validation,
      ImmutableList<CandidateRejection> rejections,
      ImmutableMap<ValidatedPredicate, String> rawStrings) {}

  public CandidateValidationOutcome validateCandidates(
      ContextPack pack,
      List<LoopHeadCandidate> candidates,
      List<? extends AbstractState> absTrace) {
    return validateCandidates(
        pack,
        candidates,
        absTrace,
        new CandidateValidationOutcome(
            new ValidationResult(ImmutableList.of()), ImmutableList.of(), ImmutableMap.of()));
  }

  /** Validate repair additions without reclassifying or discarding accepted primary bindings. */
  CandidateValidationOutcome validateCandidates(
      ContextPack pack,
      List<LoopHeadCandidate> candidates,
      List<? extends AbstractState> absTrace,
      CandidateValidationOutcome primary) {
    BooleanFormulaManager bfmgr = fmgr.getBooleanFormulaManager();
    Map<CFANode, BooleanFormula> blockByNode =
        LoopHeadBlockFormulaIndex.fromTrace(pack.blockFormulas(), absTrace);
    ArrayTermTranslator arrayTranslator =
        candidates.stream()
                .anyMatch(
                    candidate ->
                        !candidate
                            .predicate()
                            .stripLeading()
                            .startsWith(NativeCExpressionEncoder.PREFIX))
            ? ArrayTermTranslator.extract(pack.blockFormulas(), fmgr)
            : new ArrayTermTranslator(ImmutableMap.of());
    Set<String> unversionedEncodedVars = new HashSet<>();
    for (String encoded : pack.encodedVars()) {
      String bare = encoded;
      if (bare.length() >= 2 && bare.startsWith("|") && bare.endsWith("|")) {
        bare = bare.substring(1, bare.length() - 1);
      }
      int at = bare.lastIndexOf('@');
      if (at >= 0 && at < bare.length() - 1) {
        bare = bare.substring(0, at);
      }
      unversionedEncodedVars.add(bare);
    }
    // Match the same last aligned occurrence as blockByNode, including missing contexts.
    Map<CFANode, PathFormula> contextsByNode = new HashMap<>();
    for (int i = 0; i < Math.min(pack.blockFormulas().getSize(), absTrace.size()); i++) {
      AbstractState state = absTrace.get(i);
      CFANode node = extractLocation(state);
      if (node != null) {
        PredicateAbstractState pas = extractStateByType(state, PredicateAbstractState.class);
        contextsByNode.remove(node);
        if (pas != null) {
          contextsByNode.put(node, pas.getPathFormula());
        }
      }
    }
    Map<CFANode, Set<String>> blockVarsCache = new HashMap<>();
    Map<CFANode, List<BooleanFormula>> validatedAtHead = new HashMap<>();
    List<ValidatedPredicate> out = new ArrayList<>(primary.validation().validated());
    Map<ValidatedPredicate, String> rawStrings = new HashMap<>(primary.rawStrings());
    List<CandidateRejection> rejections = new ArrayList<>(primary.rejections());
    Set<String> validatedPairs = new HashSet<>();
    for (ValidatedPredicate predicate : primary.validation().validated()) {
      String formulaText = fmgr.dumpFormula(predicate.formula()).toString().replace('\n', ' ');
      validatedPairs.add(validatedPairKey(predicate.loopHeadNode(), formulaText));
      if (!predicate.groupConflict()) {
        validatedAtHead
            .computeIfAbsent(predicate.loopHeadNode(), node -> new ArrayList<>())
            .add(predicate.formula());
      }
    }
    for (LoopHeadCandidate candidate : orderedByRole(candidates)) {
      if (Thread.currentThread().isInterrupted()) {
        // Do not keep issuing solver queries after interruption; the CEGAR loop
        // observes the interrupt on its next check.
        break;
      }
      List<LoopHeadInfo> heads = new ArrayList<>();
      for (String label : candidate.loopHeads()) {
        LoopHeadInfo head = findHead(pack, label);
        if (head == null) {
          rejections.add(
              new CandidateRejection(
                  candidate.toString(),
                  label,
                  candidate.predicate(),
                  REASON_UNKNOWN_LOOP_HEAD,
                  "no loop head labeled " + label));
          continue;
        }
        if (!blockByNode.containsKey(head.node())) {
          rejections.add(
              new CandidateRejection(
                  candidate.toString(),
                  label,
                  candidate.predicate(),
                  REASON_HEAD_NOT_ON_TRACE,
                  "loop head not on spurious trace"));
          continue;
        }
        heads.add(head);
      }
      if (heads.isEmpty()) {
        continue;
      }
      boolean nativeCandidate =
          candidate.predicate().stripLeading().startsWith(NativeCExpressionEncoder.PREFIX);
      boolean arrayCandidate =
          !nativeCandidate && arrayTranslator.hasArrayAccess(candidate.predicate());
      if (!nativeCandidate
          && !arrayCandidate
          && arrayTranslator.hasCStyleArrayAccess(candidate.predicate())) {
        rejections.add(
            new CandidateRejection(
                candidate.toString(),
                heads.get(0).label(),
                candidate.predicate(),
                REASON_UNSUPPORTED_ARRAY_ACCESS,
                "C-style array access has no proven trace translation template"));
        continue;
      }
      StringBuilder perHead = new StringBuilder();
      String lastFormulaText = null;
      for (LoopHeadInfo head : heads) {
        BooleanFormula headParsed = null;
        Set<String> headFreeVars = null;
        String headFormulaText = null;
        if (!nativeCandidate && !arrayCandidate) {
          PathFormula context = contextsByNode.get(head.node());
          Set<String> parseVars = new LinkedHashSet<>();
          if (context == null) {
            parseVars.addAll(
                blockVarsCache.computeIfAbsent(
                    head.node(), node -> fmgr.extractVariableNames(blockByNode.get(node))));
            parseVars.addAll(pack.encodedVars());
          } else {
            parseVars.addAll(unversionedEncodedVars);
          }
          parseVars.removeIf(
              v -> !isVisibleAt(v, head, pack.encodedVars(), unversionedEncodedVars));
          headParsed =
              VocabularyGuide.parsePredicate(
                  candidate.predicate(),
                  fmgr,
                  parseVars,
                  ImmutableMap.of(),
                  arrayTranslator.varBits());
          if (headParsed == null) {
            rejections.add(
                new CandidateRejection(
                    candidate.toString(),
                    head.label(),
                    candidate.predicate(),
                    REASON_PARSE_ERROR,
                    "SMT-LIB parse failed against head variables"));
            continue;
          }
          if (context != null) {
            try {
              headParsed = fmgr.instantiate(fmgr.uninstantiate(headParsed), context.getSsa());
            } catch (RuntimeException e) {
              rejections.add(
                  new CandidateRejection(
                      candidate.toString(),
                      head.label(),
                      candidate.predicate(),
                      REASON_PARSE_ERROR,
                      "SSA instantiate failed at " + head.label() + ": " + e.getMessage()));
              continue;
            }
          }
          if (bfmgr.isTrue(headParsed) || bfmgr.isFalse(headParsed)) {
            rejections.add(
                new CandidateRejection(
                    candidate.toString(),
                    head.label(),
                    candidate.predicate(),
                    REASON_CONTRACT_VIOLATION,
                    "trivially true or false"));
            continue;
          }
          headFreeVars = fmgr.extractVariableNames(headParsed);
          crossCheckDeclaredVariables(candidate, headFreeVars);
          headFormulaText = fmgr.dumpFormula(headParsed).toString().replace('\n', ' ');
        }
        if (arrayCandidate) {
          // Translate source-level array reads (c i) to the heap-select encoding, then
          // instantiate with the head's SSAMap (issue #60); per-head because versions differ.
          String translated =
              arrayTranslator.translate(candidate.predicate(), head.node().getFunctionName());
          if (translated == null) {
            rejections.add(
                new CandidateRejection(
                    candidate.toString(),
                    head.label(),
                    candidate.predicate(),
                    REASON_PARSE_ERROR,
                    "array index expression not translatable"));
            continue;
          }
          headParsed =
              VocabularyGuide.parsePredicate(
                  translated,
                  fmgr,
                  unversionedEncodedVars,
                  arrayTranslator.arrayTypes(),
                  arrayTranslator.varBits());
          if (headParsed == null) {
            rejections.add(
                new CandidateRejection(
                    candidate.toString(),
                    head.label(),
                    candidate.predicate(),
                    REASON_PARSE_ERROR,
                    "array-translated SMT-LIB parse failed"));
            continue;
          }
          if (bfmgr.isTrue(headParsed) || bfmgr.isFalse(headParsed)) {
            rejections.add(
                new CandidateRejection(
                    candidate.toString(),
                    head.label(),
                    candidate.predicate(),
                    REASON_CONTRACT_VIOLATION,
                    "trivially true or false"));
            continue;
          }
          // Scope check on the unversioned formula BEFORE instantiation: versioned
          // names from the SSAMap would not match the encoded vocabulary exactly.
          List<String> preOutOfScope = new ArrayList<>();
          for (String v : fmgr.extractVariableNames(headParsed)) {
            if (!arrayTranslator.isEncodingVariable(v, head.functionName())
                && !isVisibleAt(v, head, pack.encodedVars(), unversionedEncodedVars)) {
              preOutOfScope.add(v);
            }
          }
          if (!preOutOfScope.isEmpty()) {
            rejections.add(
                new CandidateRejection(
                    candidate.toString(),
                    head.label(),
                    candidate.predicate(),
                    REASON_VARIABLE_NOT_IN_SCOPE,
                    "variables not visible at " + head.label() + ": " + preOutOfScope));
            continue;
          }
          PathFormula context = contextsByNode.get(head.node());
          SSAMap headSsa = context == null ? null : context.getSsa();
          if (headSsa == null) {
            rejections.add(
                new CandidateRejection(
                    candidate.toString(),
                    head.label(),
                    candidate.predicate(),
                    REASON_NO_SSA_MAP,
                    "no SSA map at " + head.label() + " for array candidate"));
            continue;
          }
          try {
            headParsed = fmgr.instantiate(headParsed, headSsa);
          } catch (RuntimeException e) {
            rejections.add(
                new CandidateRejection(
                    candidate.toString(),
                    head.label(),
                    candidate.predicate(),
                    REASON_PARSE_ERROR,
                    "SSA instantiate failed at " + head.label() + ": " + e.getMessage()));
            continue;
          }
          headFreeVars = fmgr.extractVariableNames(headParsed);
          crossCheckDeclaredVariables(candidate, headFreeVars);
          headFormulaText = fmgr.dumpFormula(headParsed).toString().replace('\n', ' ');
        }
        if (nativeCandidate) {
          PathFormula context = contextsByNode.get(head.node());
          if (nativeEncoder == null || context == null) {
            rejections.add(
                new CandidateRejection(
                    candidate.toString(),
                    head.label(),
                    candidate.predicate(),
                    REASON_NATIVE_CONTEXT_UNAVAILABLE,
                    "native C requires the selected head occurrence's path formula and CFA scope"));
            continue;
          }
          try {
            headParsed =
                nativeEncoder.encode(
                    candidate
                        .predicate()
                        .stripLeading()
                        .substring(NativeCExpressionEncoder.PREFIX.length()),
                    head.node(),
                    context);
          } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            break;
          } catch (CParserException | CPATransferException | IllegalArgumentException e) {
            rejections.add(
                new CandidateRejection(
                    candidate.toString(),
                    head.label(),
                    candidate.predicate(),
                    REASON_NATIVE_REJECTED,
                    e.toString()));
            continue;
          }
          if (bfmgr.isTrue(headParsed) || bfmgr.isFalse(headParsed)) {
            rejections.add(
                new CandidateRejection(
                    candidate.toString(),
                    head.label(),
                    candidate.predicate(),
                    REASON_CONTRACT_VIOLATION,
                    "trivially true or false"));
            continue;
          }
          headFreeVars = fmgr.extractVariableNames(headParsed);
          crossCheckDeclaredVariables(candidate, headFreeVars);
          headFormulaText = fmgr.dumpFormula(headParsed).toString().replace('\n', ' ');
        }
        String pairKey = validatedPairKey(head.node(), headFormulaText);
        if (!validatedPairs.add(pairKey)) {
          continue;
        }
        lastFormulaText = headFormulaText;
        List<String> outOfScope = new ArrayList<>();
        for (String v : headFreeVars) {
          if (!nativeCandidate
              && !(arrayCandidate && arrayTranslator.isEncodingVariable(v, head.functionName()))
              && !isVisibleAt(v, head, pack.encodedVars(), unversionedEncodedVars)) {
            outOfScope.add(v);
          }
        }
        if (!outOfScope.isEmpty()) {
          rejections.add(
              new CandidateRejection(
                  candidate.toString(),
                  head.label(),
                  candidate.predicate(),
                  REASON_VARIABLE_NOT_IN_SCOPE,
                  "variables not visible at " + head.label() + ": " + outOfScope));
          continue;
        }
        BooleanFormula block = blockByNode.get(head.node());
        Set<String> blockVars =
            blockVarsCache.computeIfAbsent(head.node(), node -> fmgr.extractVariableNames(block));
        boolean overSpecific =
            !headFreeVars.isEmpty()
                && headFreeVars.stream()
                    .anyMatch(v -> pack.encodedVars().contains(v) && !blockVars.contains(v));
        ValidatedPredicate.Classification cls =
            enableL3Entailment
                ? classify(block, headParsed, bfmgr)
                : ValidatedPredicate.Classification.PRECISION_ONLY;
        boolean groupConflict = false;
        if (enableL3Entailment) {
          List<BooleanFormula> previous = validatedAtHead.get(head.node());
          if (previous != null && !previous.isEmpty()) {
            groupConflict = !consistentWithGroup(block, previous, headParsed);
          }
          if (!groupConflict) {
            // Keep the accumulated set consistent so one conflict does not poison
            // the group check for every later candidate at this head.
            validatedAtHead.computeIfAbsent(head.node(), node -> new ArrayList<>()).add(headParsed);
          }
        }
        ValidatedPredicate validated =
            new ValidatedPredicate(
                headParsed,
                head.node(),
                cls,
                candidate.role(),
                candidate.variables(),
                overSpecific,
                groupConflict);
        out.add(validated);
        rawStrings.put(validated, candidate.predicate());
        if (!perHead.isEmpty()) {
          perHead.append(' ');
        }
        perHead.append(head.label()).append('=').append(cls);
        if (overSpecific) {
          perHead.append("(over_specific)");
        }
        if (groupConflict) {
          perHead.append("(group_conflict)");
        }
      }
      logger.log(Level.INFO, "VGuide predicate ", lastFormulaText, " [", perHead, "]");
    }
    return new CandidateValidationOutcome(
        new ValidationResult(ImmutableList.copyOf(out)),
        ImmutableList.copyOf(rejections),
        ImmutableMap.copyOf(rawStrings));
  }

  private static String validatedPairKey(CFANode head, String formulaText) {
    return head.getNodeNumber() + "#" + formulaText.replace('\n', ' ');
  }

  /** initiation first, then supporting, then the remaining roles in input order (stable). */
  private static List<LoopHeadCandidate> orderedByRole(List<LoopHeadCandidate> candidates) {
    List<LoopHeadCandidate> initiation = new ArrayList<>();
    List<LoopHeadCandidate> supporting = new ArrayList<>();
    List<LoopHeadCandidate> rest = new ArrayList<>();
    for (LoopHeadCandidate c : candidates) {
      if (c.role().strip().equalsIgnoreCase(ROLE_INITIATION)) {
        initiation.add(c);
      } else if (c.role().strip().equalsIgnoreCase(ROLE_SUPPORTING)) {
        supporting.add(c);
      } else {
        rest.add(c);
      }
    }
    List<LoopHeadCandidate> ordered = new ArrayList<>(initiation);
    ordered.addAll(supporting);
    ordered.addAll(rest);
    return ordered;
  }

  /**
   * A variable is visible at a loop head when it is part of the encoded trace vocabulary and, for
   * function-qualified names, its function matches the head's function. Unqualified names (e.g.
   * globals) are treated as visible everywhere.
   */
  private static boolean isVisibleAt(
      String varName,
      LoopHeadInfo head,
      Set<String> encodedVars,
      Set<String> unversionedEncodedVars) {
    // Accept both unversioned ("main::i") and versioned ("main::i@3" / "|main::i@3|") names.
    String bare = varName;
    if (bare.length() >= 2 && bare.startsWith("|") && bare.endsWith("|")) {
      bare = bare.substring(1, bare.length() - 1);
    }
    int at = bare.lastIndexOf('@');
    if (at >= 0) {
      bare = bare.substring(0, at);
    }
    if (bare.startsWith("*")) {
      // Heap arrays are global symbols of the encoding, not function-scoped.
      return true;
    }
    if (!encodedVars.contains(varName) && !unversionedEncodedVars.contains(bare)) {
      return false;
    }
    int scope = bare.indexOf("::");
    if (scope < 0) {
      return true;
    }
    return bare.substring(0, scope).equals(head.functionName());
  }

  private void crossCheckDeclaredVariables(LoopHeadCandidate candidate, Set<String> freeVars) {
    if (candidate.variables().isEmpty()) {
      return;
    }
    Set<String> declared = new HashSet<>(candidate.variables());
    for (String v : freeVars) {
      declared.remove(sourceNameOf(v));
    }
    if (!declared.isEmpty()) {
      logger.log(
          Level.FINE,
          "VGuide candidate declares variables not in parsed formula: ",
          declared,
          " for ",
          candidate.predicate());
    }
  }

  private static String sourceNameOf(String encoded) {
    String name = encoded;
    if (name.startsWith("|")) {
      name = name.substring(1);
    }
    int scope = name.indexOf("::");
    if (scope >= 0) {
      name = name.substring(scope + 2);
    }
    int at = name.indexOf('@');
    if (at >= 0) {
      name = name.substring(0, at);
    }
    if (name.endsWith("|")) {
      name = name.substring(0, name.length() - 1);
    }
    return name;
  }

  /** Advisory: is {@code pred} consistent with the block and all previously validated formulas? */
  private boolean consistentWithGroup(
      BooleanFormula block, List<BooleanFormula> previous, BooleanFormula pred) {
    try (ProverEnvironment pe = solver.newProverEnvironment(ProverOptions.GENERATE_MODELS)) {
      pe.push(block);
      for (BooleanFormula p : previous) {
        pe.push(p);
      }
      pe.push(pred);
      return !pe.isUnsat();
    } catch (SolverException e) {
      logger.logDebugException(e, "VGuide group consistency check failed");
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
    }
    return true;
  }

  static @org.checkerframework.checker.nullness.qual.Nullable LoopHeadInfo findHead(
      ContextPack pack, String label) {
    for (LoopHeadInfo head : pack.loopHeads()) {
      if (head.label().equals(label)) {
        return head;
      }
    }
    return null;
  }

  private ValidatedPredicate.Classification classify(
      BooleanFormula block, BooleanFormula pred, BooleanFormulaManager bfmgr) {
    try (ProverEnvironment pe = solver.newProverEnvironment(ProverOptions.GENERATE_MODELS)) {
      pe.push(block);
      pe.push(bfmgr.not(pred));
      if (pe.isUnsat()) {
        return ValidatedPredicate.Classification.ENTAILED;
      }
    } catch (SolverException e) {
      logger.logDebugException(e, "VGuide SMT check failed");
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
    }
    return ValidatedPredicate.Classification.PRECISION_ONLY;
  }
}
