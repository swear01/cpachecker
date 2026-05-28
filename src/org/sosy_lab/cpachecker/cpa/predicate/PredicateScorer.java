// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-FileCopyrightText: 2007-2020 Dirk Beyer <https://www.sosy-lab.org>
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.logging.Level;
import org.sosy_lab.common.log.LogManager;
import org.sosy_lab.cpachecker.util.predicates.smt.FormulaManagerView;
import org.sosy_lab.cpachecker.util.predicates.smt.Solver;
import org.sosy_lab.java_smt.api.BooleanFormula;
import org.sosy_lab.cpachecker.util.predicates.smt.BooleanFormulaManagerView;
import org.sosy_lab.java_smt.api.ProverEnvironment;
import org.sosy_lab.java_smt.api.SolverContext.ProverOptions;
import org.sosy_lab.java_smt.api.SolverException;

public class PredicateScorer {

  public static final int REJECT = -1;

  private static final int BASE_NON_CONSTANT = 5;
  private static final int BASE_ENTAILED = 1;
  private static final int BONUS_RELATIONAL = 3;
  private static final int BONUS_ACCUMULATOR = 3;
  private static final int BONUS_MODULO = 2;
  private static final int BONUS_CONCISE = 1;
  private static final int BONUS_LOOP_HEAD = 1;

  private static final int CONCISE_THRESHOLD = 400;

  private final Solver solver;
  private final FormulaManagerView fmgr;
  private final LogManager logger;

  public PredicateScorer(Solver pSolver, FormulaManagerView pFmgr, LogManager pLogger) {
    solver = pSolver;
    fmgr = pFmgr;
    logger = pLogger;
  }

  public int scorePredicate(
      BooleanFormula blockFormula,
      BooleanFormula predicate,
      FormulaManagerView pFmgr,
      boolean isLoopHead) {
    BooleanFormulaManagerView bfmgr = pFmgr.getBooleanFormulaManager();

    if (bfmgr.isTrue(predicate) || bfmgr.isFalse(predicate)) {
      logger.logf(Level.FINE, "V4 score: REJECT (trivial)");
      return REJECT;
    }

    int base;
    try (ProverEnvironment pe = solver.newProverEnvironment(ProverOptions.GENERATE_MODELS)) {
      pe.push(blockFormula);
      pe.push(predicate);
      if (pe.isUnsat()) {
        logger.logf(Level.FINE, "V4 score: REJECT (contradictory with block)");
        return REJECT;
      }
    } catch (SolverException | InterruptedException e) {
      logger.logUserException(Level.FINE, e, "V4 score: REJECT (Solver error)");
      return REJECT;
    }

    try (ProverEnvironment pe = solver.newProverEnvironment(ProverOptions.GENERATE_MODELS)) {
      pe.push(blockFormula);
      pe.push(bfmgr.not(predicate));
      if (pe.isUnsat()) {
        base = BASE_ENTAILED;
      } else {
        base = BASE_NON_CONSTANT;
      }
    } catch (SolverException | InterruptedException e) {
      logger.logUserException(Level.FINE, e, "V4 score: REJECT (Solver error on negation)");
      return REJECT;
    }

    String text = pFmgr.dumpFormula(predicate).toString();
    Set<String> vars = pFmgr.extractVariableNames(predicate);

    int score = base;
    if (vars.size() >= 2) {
      score += BONUS_RELATIONAL;
    }
    if (text.contains("bvurem") || text.contains("mod")) {
      score += BONUS_MODULO;
    }
    if (text.contains("bvmul") || text.contains("*")) {
      score += BONUS_ACCUMULATOR;
    }
    if (text.length() < CONCISE_THRESHOLD) {
      score += BONUS_CONCISE;
    }
    if (isLoopHead) {
      score += BONUS_LOOP_HEAD;
    }

    String kind = base == BASE_NON_CONSTANT ? "NON-CONSTANT" : "ENTAILED";
    logger.logf(Level.FINE, "V4 score: %s score=%d vars=%d text_length=%d loop=%b",
        kind, score, vars.size(), text.length(), isLoopHead);
    return score;
  }

  public RankedPredicates scoreAndRank(
      BooleanFormula blockFormula,
      List<BooleanFormula> candidates,
      FormulaManagerView pFmgr,
      boolean isLoopHead,
      int topK) {
    Map<BooleanFormula, Integer> scored = new LinkedHashMap<>();
    List<BooleanFormula> rejected = new ArrayList<>();

    for (BooleanFormula c : candidates) {
      int s = scorePredicate(blockFormula, c, pFmgr, isLoopHead);
      if (s == REJECT) {
        rejected.add(c);
      } else {
        scored.put(c, s);
      }
    }

    List<Map.Entry<BooleanFormula, Integer>> sorted = new ArrayList<>(scored.entrySet());
    sorted.sort((a, b) -> Integer.compare(b.getValue(), a.getValue()));

    List<BooleanFormula> selected = new ArrayList<>();
    for (int i = 0; i < Math.min(topK, sorted.size()); i++) {
      selected.add(sorted.get(i).getKey());
    }

    logger.logf(
        Level.INFO,
        "V4 scoreAndRank: scored=%d rejected=%d selected=%d topK=%d",
        scored.size(),
        rejected.size(),
        selected.size(),
        topK);

    return new RankedPredicates(selected, scored, rejected);
  }

  public record RankedPredicates(
      List<BooleanFormula> predicates,
      Map<BooleanFormula, Integer> allScores,
      List<BooleanFormula> rejected) {}
}
