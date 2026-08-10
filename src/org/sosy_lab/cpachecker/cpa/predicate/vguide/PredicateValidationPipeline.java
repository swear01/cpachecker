// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import com.google.common.collect.ImmutableList;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.logging.Level;
import org.sosy_lab.common.log.LogManager;

import org.sosy_lab.cpachecker.cfa.model.CFANode;
import org.sosy_lab.cpachecker.core.interfaces.AbstractState;
import org.sosy_lab.cpachecker.cpa.predicate.VocabularyGuide;
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
  public static final String REASON_CONTRACT_VIOLATION = "contract_violation";
  public static final String REASON_VARIABLE_NOT_IN_SCOPE = "variable_not_in_scope";

  private static final String ROLE_INITIATION = "initiation";
  private static final String ROLE_SUPPORTING = "supporting";

  private final LogManager logger;
  private final Solver solver;
  private final FormulaManagerView fmgr;
  private final boolean enableL3Entailment;

  public PredicateValidationPipeline(
      LogManager logger, Solver solver, FormulaManagerView fmgr, boolean enableL3Entailment) {
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
      ValidationResult validation, ImmutableList<CandidateRejection> rejections) {}

  public CandidateValidationOutcome validateCandidates(
      ContextPack pack, List<LoopHeadCandidate> candidates, List<? extends AbstractState> absTrace) {
    BooleanFormulaManager bfmgr = fmgr.getBooleanFormulaManager();
    Map<CFANode, BooleanFormula> blockByNode =
        LoopHeadBlockFormulaIndex.fromTrace(pack.blockFormulas(), absTrace);
    Map<CFANode, Set<String>> blockVarsCache = new HashMap<>();
    Map<CFANode, List<BooleanFormula>> validatedAtHead = new HashMap<>();
    List<ValidatedPredicate> out = new ArrayList<>();
    List<CandidateRejection> rejections = new ArrayList<>();
    Set<String> validatedPairs = new HashSet<>();
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
      BooleanFormula parsed =
          VocabularyGuide.parsePredicate(candidate.predicate(), fmgr, pack.encodedVars());
      if (parsed == null) {
        rejections.add(
            new CandidateRejection(
                candidate.toString(),
                heads.get(0).label(),
                candidate.predicate(),
                REASON_PARSE_ERROR,
                "SMT-LIB parse failed"));
        continue;
      }
      if (bfmgr.isTrue(parsed) || bfmgr.isFalse(parsed)) {
        rejections.add(
            new CandidateRejection(
                candidate.toString(),
                heads.get(0).label(),
                candidate.predicate(),
                REASON_CONTRACT_VIOLATION,
                "trivially true or false"));
        continue;
      }
      Set<String> freeVars = fmgr.extractVariableNames(parsed);
      crossCheckDeclaredVariables(candidate, freeVars);
      String formulaText = fmgr.dumpFormula(parsed).toString().replace('\n', ' ');
      StringBuilder perHead = new StringBuilder();
      for (LoopHeadInfo head : heads) {
        String pairKey = head.node().getNodeNumber() + "#" + formulaText;
        if (!validatedPairs.add(pairKey)) {
          continue;
        }
        List<String> outOfScope = new ArrayList<>();
        for (String v : freeVars) {
          if (!isVisibleAt(v, head, pack.encodedVars())) {
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
            !freeVars.isEmpty()
                && freeVars.stream()
                    .anyMatch(v -> pack.encodedVars().contains(v) && !blockVars.contains(v));
        ValidatedPredicate.Classification cls =
            enableL3Entailment
                ? classify(block, parsed, bfmgr)
                : ValidatedPredicate.Classification.PRECISION_ONLY;
        boolean groupConflict = false;
        if (enableL3Entailment) {
          List<BooleanFormula> previous = validatedAtHead.get(head.node());
          if (previous != null && !previous.isEmpty()) {
            groupConflict = !consistentWithGroup(block, previous, parsed);
          }
          if (!groupConflict) {
            // Keep the accumulated set consistent so one conflict does not poison
            // the group check for every later candidate at this head.
            validatedAtHead.computeIfAbsent(head.node(), node -> new ArrayList<>()).add(parsed);
          }
        }
        out.add(
            new ValidatedPredicate(
                parsed,
                head.node(),
                cls,
                candidate.role(),
                candidate.variables(),
                overSpecific,
                groupConflict));
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
      logger.log(Level.INFO, "VGuide predicate ", formulaText, " [", perHead, "]");
    }
    return new CandidateValidationOutcome(
        new ValidationResult(ImmutableList.copyOf(out)), ImmutableList.copyOf(rejections));
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
  private static boolean isVisibleAt(String varName, LoopHeadInfo head, Set<String> encodedVars) {
    if (!encodedVars.contains(varName)) {
      return false;
    }
    int scope = varName.indexOf("::");
    if (scope < 0) {
      return true;
    }
    int start = varName.startsWith("|") ? 1 : 0;
    return varName.substring(start, scope).equals(head.functionName());
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
