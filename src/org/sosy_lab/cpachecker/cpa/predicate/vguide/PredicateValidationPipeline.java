// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import com.google.common.collect.ImmutableList;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
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

/** L1 contract + L2 parse + L3 SMT entailment per loop head. */
public final class PredicateValidationPipeline {

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

  public ValidationResult validate(
      ContextPack pack, List<String> rawPredicates, List<? extends AbstractState> absTrace) {
    BooleanFormulaManager bfmgr = fmgr.getBooleanFormulaManager();
    Map<CFANode, BooleanFormula> blockByNode =
        LoopHeadBlockFormulaIndex.fromTrace(pack.blockFormulas(), absTrace);
    List<ValidatedPredicate> out = new ArrayList<>();
    for (String raw : rawPredicates) {
      if (!PredicateContractValidator.isValid(raw)) {
        logger.log(Level.FINE, "VGuide reject L1: ", raw);
        continue;
      }
      BooleanFormula parsed =
          VocabularyGuide.parsePredicate(raw, fmgr, pack.encodedVars());
      if (parsed == null) {
        logger.log(Level.FINE, "VGuide reject L2 parse: ", raw);
        continue;
      }
      if (bfmgr.isTrue(parsed) || bfmgr.isFalse(parsed)) {
        continue;
      }
      String formulaText = fmgr.dumpFormula(parsed).toString().replace('\n', ' ');
      StringBuilder perHead = new StringBuilder();
      boolean classified = false;
      for (LoopHeadInfo head : pack.loopHeads()) {
        BooleanFormula block = blockByNode.get(head.node());
        if (block == null) {
          logger.log(
              Level.FINE,
              "VGuide: loop head ",
              head.label(),
              " not on spurious trace; skip SMT for this head");
          continue;
        }
        ValidatedPredicate.Classification cls =
            enableL3Entailment
                ? classify(block, parsed, bfmgr)
                : ValidatedPredicate.Classification.PRECISION_ONLY;
        out.add(new ValidatedPredicate(parsed, head.node(), cls));
        classified = true;
        if (!perHead.isEmpty()) {
          perHead.append(' ');
        }
        perHead.append(head.label()).append('=').append(cls);
      }
      if (classified) {
        logger.log(Level.INFO, "VGuide predicate ", formulaText, " [", perHead, "]");
      }
    }
    return new ValidationResult(ImmutableList.copyOf(out));
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
