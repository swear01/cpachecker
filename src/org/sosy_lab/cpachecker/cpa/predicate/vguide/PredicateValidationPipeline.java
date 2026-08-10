// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import com.google.common.collect.ImmutableList;
import java.util.ArrayList;
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
 * L1 contract + L2 parse + L3 SMT entailment per named loop head.
 *
 * <p>Mapping policy: a candidate is validated only at the loop heads it names; no implicit
 * broadcast. A named head that does not exist or is not on the spurious trace is recorded as an
 * observable rejection.
 */
public final class PredicateValidationPipeline {

  public static final String REASON_UNKNOWN_LOOP_HEAD = "unknown_loop_head";
  public static final String REASON_HEAD_NOT_ON_TRACE = "head_not_on_trace";
  public static final String REASON_PARSE_ERROR = "parse_error";
  public static final String REASON_CONTRACT_VIOLATION = "contract_violation";

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
          "VGuide L3 entailment disabled; all parsed predicates use PRECISION_ONLY");
    }
  }

  public record CandidateValidationOutcome(
      ValidationResult validation, ImmutableList<CandidateRejection> rejections) {}

  public CandidateValidationOutcome validateCandidates(
      ContextPack pack, List<LoopHeadCandidate> candidates, List<? extends AbstractState> absTrace) {
    BooleanFormulaManager bfmgr = fmgr.getBooleanFormulaManager();
    Map<CFANode, BooleanFormula> blockByNode =
        LoopHeadBlockFormulaIndex.fromTrace(pack.blockFormulas(), absTrace);
    List<ValidatedPredicate> out = new ArrayList<>();
    List<CandidateRejection> rejections = new ArrayList<>();
    Set<String> validatedPairs = new HashSet<>();
    for (LoopHeadCandidate candidate : candidates) {
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
      String formulaText = fmgr.dumpFormula(parsed).toString().replace('\n', ' ');
      StringBuilder perHead = new StringBuilder();
      for (LoopHeadInfo head : heads) {
        String pairKey = head.node().getNodeNumber() + "#" + formulaText;
        if (!validatedPairs.add(pairKey)) {
          continue;
        }
        BooleanFormula block = blockByNode.get(head.node());
        ValidatedPredicate.Classification cls =
            enableL3Entailment
                ? classify(block, parsed, bfmgr)
                : ValidatedPredicate.Classification.PRECISION_ONLY;
        out.add(new ValidatedPredicate(parsed, head.node(), cls, candidate.role(), candidate.variables()));
        if (!perHead.isEmpty()) {
          perHead.append(' ');
        }
        perHead.append(head.label()).append('=').append(cls);
      }
      logger.log(Level.INFO, "VGuide predicate ", formulaText, " [", perHead, "]");
    }
    return new CandidateValidationOutcome(
        new ValidationResult(ImmutableList.copyOf(out)), ImmutableList.copyOf(rejections));
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
