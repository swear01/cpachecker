// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-FileCopyrightText: 2007-2020 Dirk Beyer <https://www.sosy-lab.org>
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate;

import static com.google.common.truth.Truth.assertThat;

import java.util.List;
import java.util.Set;
import org.junit.Test;
import org.sosy_lab.common.log.LogManager;
import org.sosy_lab.cpachecker.util.predicates.smt.FormulaManagerView;
import org.sosy_lab.cpachecker.util.predicates.smt.SolverViewBasedTest0;
import org.sosy_lab.java_smt.api.BooleanFormula;
import org.sosy_lab.java_smt.api.ProverEnvironment;
import org.sosy_lab.java_smt.api.SolverContext.ProverOptions;
import org.sosy_lab.java_smt.api.SolverException;

public class PredicateScorerTest extends SolverViewBasedTest0 {

  private PredicateScorer create() {
    return new PredicateScorer(solver, mgrv, LogManager.createTestLogManager());
  }

  private static BooleanFormula parse(String expr, FormulaManagerView fmgr) {
    return VocabularyGuide.parsePredicate(expr, fmgr, Set.of());
  }

  // --- Rejection tests ---

  @Test
  public void rejectsTrue() {
    PredicateScorer scorer = create();
    BooleanFormula block = parse("(= x 5)", mgrv);
    int score = scorer.scorePredicate(block, bmgrv.makeBoolean(true), mgrv, false);
    assertThat(score).isEqualTo(-1);
  }

  @Test
  public void rejectsFalse() {
    PredicateScorer scorer = create();
    BooleanFormula block = parse("(= x 5)", mgrv);
    int score = scorer.scorePredicate(block, bmgrv.makeBoolean(false), mgrv, false);
    assertThat(score).isEqualTo(-1);
  }

  @Test
  public void rejectsContradictory_predicateContradictsBlock() throws SolverException, InterruptedException {
    PredicateScorer scorer = create();
    BooleanFormula block = parse("(= x 0)", mgrv);
    BooleanFormula p = parse("(> x 0)", mgrv);
    try (ProverEnvironment pe = solver.newProverEnvironment(ProverOptions.GENERATE_MODELS)) {
      pe.push(block);
      pe.push(p);
      assertThat(pe.isUnsat()).isTrue();
    }
    int score = scorer.scorePredicate(block, p, mgrv, false);
    assertThat(score).isEqualTo(-1);
  }

  // --- Scoring tests ---

  @Test
  public void scoresNonConstantHigh_bothWaysSat() {
    PredicateScorer scorer = create();
    BooleanFormula block = parse("(= x 5)", mgrv);
    BooleanFormula p = parse("(= y x)", mgrv);
    int score = scorer.scorePredicate(block, p, mgrv, false);
    assertThat(score).isAtLeast(5);
  }

  @Test
  public void scoresEntailedLower_blockImpliesPredicate() {
    PredicateScorer scorer = create();
    BooleanFormula block = parse("(= x 5)", mgrv);
    BooleanFormula p = parse("(>= x 0)", mgrv);
    int score = scorer.scorePredicate(block, p, mgrv, false);
    assertThat(score).isAtLeast(0);
    assertThat(score).isLessThan(5);
  }

  @Test
  public void relationalBonus_2plusVariables() {
    PredicateScorer scorer = create();
    BooleanFormula block = parse("(= x 5)", mgrv);
    BooleanFormula p = parse("(= y x)", mgrv);
    int score = scorer.scorePredicate(block, p, mgrv, false);
    assertThat(score).isAtLeast(8);
  }

  @Test
  public void accumulatorBonus_containsBvmul() {
    PredicateScorer scorer = create();
    BooleanFormula block = parse("(= s 0)", mgrv);
    BooleanFormula p = parse("(= s (* i 255))", mgrv);
    int score = scorer.scorePredicate(block, p, mgrv, false);
    assertThat(score).isAtLeast(8);
  }

  @Test
  public void moduloBonus_containsBvurem() {
    PredicateScorer scorer = create();
    BooleanFormula block = parse("(= x 1)", mgrv);
    BooleanFormula p = parse("(= (mod x 2) (mod y 2))", mgrv);
    int score = scorer.scorePredicate(block, p, mgrv, false);
    assertThat(score).isAtLeast(9);
  }

  @Test
  public void loopHeadBonus_addsOneWhenTrue() {
    PredicateScorer scorer = create();
    BooleanFormula block = parse("(= x 5)", mgrv);
    BooleanFormula p = parse("(= y x)", mgrv);
    int noLoop = scorer.scorePredicate(block, p, mgrv, false);
    int withLoop = scorer.scorePredicate(block, p, mgrv, true);
    assertThat(withLoop).isEqualTo(noLoop + 1);
  }

  // --- Ranking test ---

  @Test
  public void ranking_prefersNonConstantRelational_overEntailed() {
    PredicateScorer scorer = create();
    BooleanFormula block = parse("(= x 5)", mgrv);
    BooleanFormula nonConstantRel = parse("(= y x)", mgrv);
    BooleanFormula entailed = parse("(>= x 0)", mgrv);
    BooleanFormula simpleNonConstant = parse("(>= y 0)", mgrv);

    int sRel = scorer.scorePredicate(block, nonConstantRel, mgrv, true);
    int sEnt = scorer.scorePredicate(block, entailed, mgrv, true);
    int sSimple = scorer.scorePredicate(block, simpleNonConstant, mgrv, true);

    assertThat(sRel).isGreaterThan(sEnt);
    assertThat(sRel).isGreaterThan(sSimple);
  }

  // --- Batch scoring ---

  @Test
  public void scoreAndRank_returnsTopK_sortedDescending() {
    PredicateScorer scorer = create();
    BooleanFormula block = parse("(= x 5)", mgrv);
    BooleanFormula p1 = parse("(>= x 0)", mgrv);
    BooleanFormula p2 = parse("(= y x)", mgrv);
    BooleanFormula p3 = parse("(>= y 0)", mgrv);

    List<BooleanFormula> candidates = List.of(p1, p2, p3);
    PredicateScorer.RankedPredicates result =
        scorer.scoreAndRank(block, candidates, mgrv, false, 2);

    assertThat(result.predicates()).hasSize(2);
    assertThat(result.allScores()).hasSize(3);
    assertThat(result.rejected()).isEmpty();
  }

  @Test
  public void scoreAndRank_filtersContradictory() {
    PredicateScorer scorer = create();
    BooleanFormula block = parse("(= x 0)", mgrv);
    BooleanFormula contra = parse("(> x 0)", mgrv);
    BooleanFormula ok = parse("(>= y 0)", mgrv);

    List<BooleanFormula> candidates = List.of(contra, ok);
    PredicateScorer.RankedPredicates result =
        scorer.scoreAndRank(block, candidates, mgrv, false, 3);

    assertThat(result.rejected()).hasSize(1);
    assertThat(result.predicates()).hasSize(1);
    assertThat(result.predicates().get(0)).isEqualTo(ok);
  }
}
