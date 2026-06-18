// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-FileCopyrightText: 2026 Dirk Beyer <https://www.sosy-lab.org>
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.core.algorithm.termination.lasso_analysis.vguide;

import static com.google.common.base.Preconditions.checkNotNull;

import java.util.function.Supplier;
import org.sosy_lab.cpachecker.util.predicates.pathformula.SSAMap;
import org.sosy_lab.cpachecker.util.predicates.smt.BooleanFormulaManagerView;
import org.sosy_lab.cpachecker.util.predicates.smt.FormulaManagerView;
import org.sosy_lab.cpachecker.util.predicates.smt.IntegerFormulaManagerView;
import org.sosy_lab.java_smt.api.BooleanFormula;
import org.sosy_lab.java_smt.api.NumeralFormula.IntegerFormula;
import org.sosy_lab.java_smt.api.ProverEnvironment;
import org.sosy_lab.java_smt.api.SolverException;

/**
 * Soundness core of the termination ranking-function hook. Given a candidate ranking function
 * {@code f} and an optional supporting invariant {@code I} (both as <em>uninstantiated</em>
 * formulas over the program variables), checks whether {@code (I, f)} proves termination of the
 * loop transition relation {@code T(x, x')} by discharging four verification conditions as
 * unsatisfiability queries:
 *
 * <ul>
 *   <li><b>initiation</b>: {@code Stem ==> I(x_entry)}
 *   <li><b>consecution</b>: {@code I(x) & T(x, x') ==> I(x')} ({@code I} is inductive)
 *   <li><b>bounded</b>: {@code I(x) & T(x, x') ==> f(x) >= 0}
 *   <li><b>decrease</b>: {@code I(x) & T(x, x') ==> f(x') < f(x)}
 * </ul>
 *
 * <p>When {@code I} is {@code true} the first two checks pass trivially and this degenerates to the
 * pure-ranking-function case. Because acceptance requires all four queries to be UNSAT (verified by
 * the SMT solver, not the LLM), an incorrect candidate is simply rejected and can never produce a
 * wrong verdict.
 */
public final class RankingFunctionVerifier {

  private final FormulaManagerView fmgr;
  private final BooleanFormulaManagerView bfmgr;
  private final IntegerFormulaManagerView ifmgr;
  private final Supplier<ProverEnvironment> proverSupplier;

  public RankingFunctionVerifier(
      FormulaManagerView pFmgr, Supplier<ProverEnvironment> pProverSupplier) {
    fmgr = checkNotNull(pFmgr);
    bfmgr = pFmgr.getBooleanFormulaManager();
    ifmgr = pFmgr.getIntegerFormulaManager();
    proverSupplier = checkNotNull(pProverSupplier);
  }

  /**
   * A candidate termination argument: a measure {@code f} and a supporting invariant {@code
   * supportingInvariant} ({@code true} if none needed), both uninstantiated.
   */
  public record Candidate(IntegerFormula f, BooleanFormula supportingInvariant) {}

  /** Result of checking a candidate: VALID, or the first verification condition that failed. */
  public enum Outcome {
    VALID,
    INITIATION_FAILED,
    CONSECUTION_FAILED,
    BOUNDED_FAILED,
    DECREASE_FAILED
  }

  /**
   * Returns {@code true} iff {@code (I, f)} soundly proves termination of the given lasso.
   *
   * @param candidate the uninstantiated {@code (f, I)} pair
   * @param stem the stem transition formula (initial state to loop entry)
   * @param loop the loop transition formula {@code T(x, x')}
   * @param loopInVars SSA indices of the loop-entry (unprimed {@code x}) variables
   * @param loopOutVars SSA indices of the loop-exit (primed {@code x'}) variables
   */
  public boolean isValid(
      Candidate candidate,
      BooleanFormula stem,
      BooleanFormula loop,
      SSAMap loopInVars,
      SSAMap loopOutVars)
      throws SolverException, InterruptedException {
    return verify(candidate, stem, loop, loopInVars, loopOutVars) == Outcome.VALID;
  }

  /** Like {@link #isValid} but reports the first verification condition that failed. */
  public Outcome verify(
      Candidate candidate,
      BooleanFormula stem,
      BooleanFormula loop,
      SSAMap loopInVars,
      SSAMap loopOutVars)
      throws SolverException, InterruptedException {

    IntegerFormula fIn = fmgr.instantiate(candidate.f(), loopInVars);
    IntegerFormula fOut = fmgr.instantiate(candidate.f(), loopOutVars);
    BooleanFormula invIn = fmgr.instantiate(candidate.supportingInvariant(), loopInVars);
    BooleanFormula invOut = fmgr.instantiate(candidate.supportingInvariant(), loopOutVars);
    IntegerFormula zero = ifmgr.makeNumber(0);

    // initiation: Stem ==> I(x_entry).  Stem's out-vars are at the loop-in indices.
    if (!isUnsat(bfmgr.and(stem, bfmgr.not(invIn)))) {
      return Outcome.INITIATION_FAILED;
    }
    // consecution: I(x) & T ==> I(x').
    if (!isUnsat(bfmgr.and(invIn, bfmgr.and(loop, bfmgr.not(invOut))))) {
      return Outcome.CONSECUTION_FAILED;
    }
    // bounded: I(x) & T ==> f(x) >= 0.
    if (!isUnsat(bfmgr.and(invIn, bfmgr.and(loop, ifmgr.lessThan(fIn, zero))))) {
      return Outcome.BOUNDED_FAILED;
    }
    // decrease: I(x) & T ==> f(x') < f(x).
    if (!isUnsat(bfmgr.and(invIn, bfmgr.and(loop, bfmgr.not(ifmgr.lessThan(fOut, fIn)))))) {
      return Outcome.DECREASE_FAILED;
    }
    return Outcome.VALID;
  }

  private boolean isUnsat(BooleanFormula formula) throws SolverException, InterruptedException {
    try (ProverEnvironment prover = proverSupplier.get()) {
      prover.push(formula);
      return prover.isUnsat();
    }
  }
}
