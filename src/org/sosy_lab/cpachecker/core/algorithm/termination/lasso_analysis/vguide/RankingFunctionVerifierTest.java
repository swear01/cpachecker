// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-FileCopyrightText: 2026 Dirk Beyer <https://www.sosy-lab.org>
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.core.algorithm.termination.lasso_analysis.vguide;

import static com.google.common.truth.Truth.assertThat;

import org.junit.Before;
import org.junit.Test;
import org.sosy_lab.cpachecker.cfa.types.c.CNumericTypes;
import org.sosy_lab.cpachecker.core.algorithm.termination.lasso_analysis.vguide.RankingFunctionVerifier.Candidate;
import org.sosy_lab.cpachecker.util.predicates.pathformula.SSAMap;
import org.sosy_lab.cpachecker.util.predicates.pathformula.SSAMap.SSAMapBuilder;
import org.sosy_lab.cpachecker.util.predicates.smt.SolverViewBasedTest0;
import org.sosy_lab.java_smt.SolverContextFactory.Solvers;
import org.sosy_lab.java_smt.api.BooleanFormula;
import org.sosy_lab.java_smt.api.NumeralFormula.IntegerFormula;

/**
 * Unit tests for {@link RankingFunctionVerifier}: hand-written {@code (I, f)} candidates against
 * known loop transitions, including the {@code I = true} degenerate case and a case where the
 * supporting invariant is necessary for the decrease check to hold.
 */
public class RankingFunctionVerifierTest extends SolverViewBasedTest0 {

  @Override
  protected Solvers solverToUse() {
    // Matches the solver the lasso/termination analysis actually uses (linear integer arithmetic).
    return Solvers.SMTINTERPOL;
  }

  private RankingFunctionVerifier verifier;

  @Before
  public void setUpVerifier() {
    verifier = new RankingFunctionVerifier(mgrv, () -> context.newProverEnvironment());
  }

  // ---- helpers ----------------------------------------------------------------

  private IntegerFormula var(String name, int idx) {
    return imgrv.makeVariable(name, idx);
  }

  private IntegerFormula var(String name) {
    return imgrv.makeVariable(name);
  }

  private IntegerFormula num(long value) {
    return imgrv.makeNumber(value);
  }

  /** Builds an SSAMap from (name, index) pairs. */
  private SSAMap ssa(Object... pairs) {
    SSAMapBuilder b = SSAMap.emptySSAMap().builder();
    for (int i = 0; i < pairs.length; i += 2) {
      b = b.setIndex((String) pairs[i], CNumericTypes.INT, (Integer) pairs[i + 1]);
    }
    return b.build();
  }

  private Candidate cand(IntegerFormula f) {
    return new Candidate(f, bmgrv.makeTrue());
  }

  private Candidate cand(IntegerFormula f, BooleanFormula inv) {
    return new Candidate(f, inv);
  }

  // ---- loop: while (i < n) i++;  (terminating, ranking f = n - i) -------------

  /** T(x,x') = i_in < n_in & i_out = i_in + 1 & n_out = n_in. */
  private BooleanFormula incrementingLoop() {
    return bmgrv.and(
        imgrv.lessThan(var("i", 1), var("n", 1)),
        imgrv.equal(var("i", 2), imgrv.add(var("i", 1), num(1))),
        imgrv.equal(var("n", 2), var("n", 1)));
  }

  @Test
  public void rankingFunction_nMinusI_isValid() throws Exception {
    // f = n - i decreases and is bounded below by 0 over the loop transition.
    Candidate c = cand(imgrv.subtract(var("n"), var("i")));
    assertThat(
            verifier.isValid(
                c, bmgrv.makeTrue(), incrementingLoop(), ssa("i", 1, "n", 1), ssa("i", 2, "n", 2)))
        .isTrue();
  }

  @Test
  public void increasingMeasure_isRejected() throws Exception {
    // f = i increases each iteration, so the decrease check must fail.
    Candidate c = cand(var("i"));
    assertThat(
            verifier.isValid(
                c, bmgrv.makeTrue(), incrementingLoop(), ssa("i", 1, "n", 1), ssa("i", 2, "n", 2)))
        .isFalse();
  }

  @Test
  public void nonInductiveSupportingInvariant_isRejected() throws Exception {
    // I = (i == 0) is not preserved by i++, so consecution fails even though f = n - i is fine.
    Candidate c = cand(imgrv.subtract(var("n"), var("i")), imgrv.equal(var("i"), num(0)));
    assertThat(
            verifier.isValid(
                c, bmgrv.makeTrue(), incrementingLoop(), ssa("i", 1, "n", 1), ssa("i", 2, "n", 2)))
        .isFalse();
  }

  // ---- loop: while (x > 0) x -= y;  with stem establishing y >= 1 -------------

  /** T(x,x') = x_in > 0 & x_out = x_in - y_in & y_out = y_in. */
  private BooleanFormula decrementByYLoop() {
    return bmgrv.and(
        imgrv.greaterThan(var("x", 1), num(0)),
        imgrv.equal(var("x", 2), imgrv.subtract(var("x", 1), var("y", 1))),
        imgrv.equal(var("y", 2), var("y", 1)));
  }

  @Test
  public void supportingInvariant_isNecessary_andSufficient() throws Exception {
    // f = x. Decrease (x' < x) holds only when y >= 1, which must come from the supporting
    // invariant I = (y >= 1)  [encoded as y > 0 over integers]. Stem establishes y >= 1.
    BooleanFormula stem = imgrv.greaterThan(var("y", 1), num(0));
    BooleanFormula loop = decrementByYLoop();
    SSAMap in = ssa("x", 1, "y", 1);
    SSAMap out = ssa("x", 2, "y", 2);

    BooleanFormula invYpos = imgrv.greaterThan(var("y"), num(0)); // y >= 1
    Candidate withInvariant = cand(var("x"), invYpos);
    Candidate withoutInvariant = cand(var("x")); // I = true

    // With the supporting invariant: all four checks pass.
    assertThat(verifier.isValid(withInvariant, stem, loop, in, out)).isTrue();
    // Without it: the decrease check is not provable from T alone -> rejected.
    assertThat(verifier.isValid(withoutInvariant, stem, loop, in, out)).isFalse();
  }
}
