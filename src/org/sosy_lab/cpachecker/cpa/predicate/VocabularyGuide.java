// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-FileCopyrightText: 2007-2020 Dirk Beyer <https://www.sosy-lab.org>
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate;

import com.google.common.collect.ImmutableList;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Level;
import org.checkerframework.checker.nullness.qual.Nullable;
import org.sosy_lab.common.log.LogManager;
import org.sosy_lab.cpachecker.util.Pair;
import org.sosy_lab.cpachecker.util.predicates.smt.BooleanFormulaManagerView;
import org.sosy_lab.cpachecker.util.predicates.smt.FormulaManagerView;
import org.sosy_lab.cpachecker.util.predicates.smt.Solver;
import org.sosy_lab.java_smt.api.BooleanFormula;
import org.sosy_lab.java_smt.api.ProverEnvironment;
import org.sosy_lab.java_smt.api.SolverContext.ProverOptions;
import org.sosy_lab.java_smt.api.SolverException;

/**
 * Dynamic Predicate Vocabulary V that guides interpolation strategy selection in CEGAR. V is
 * maintained by the LLM and used by the refiner to score candidate predicate sets.
 */
public class VocabularyGuide {

  static class VocabEntry {
    final BooleanFormula predicate;
    final AtomicInteger considered = new AtomicInteger();
    final AtomicInteger selected = new AtomicInteger();

    VocabEntry(BooleanFormula p) {
      this.predicate = p;
    }
  }

  static class ScoredResult {
    final ImmutableList<BooleanFormula> predicates;
    final double score;
    final String label;

    ScoredResult(List<BooleanFormula> p, double s, String l) {
      predicates = ImmutableList.copyOf(p);
      score = s;
      label = l;
    }
  }

  private final Solver solver;
  private final FormulaManagerView fmgr;
  private final BooleanFormulaManagerView bfmgr;
  private final LogManager logger;
  private final double alpha;
  private final double tau;

  private final CopyOnWriteArrayList<VocabEntry> vocab = new CopyOnWriteArrayList<>();

  public VocabularyGuide(Solver pSolver, LogManager pLogger, double pAlpha, double pTau) {
    solver = pSolver;
    fmgr = pSolver.getFormulaManager();
    bfmgr = fmgr.getBooleanFormulaManager();
    logger = pLogger;
    alpha = pAlpha;
    tau = pTau;
  }

  public boolean isEmpty() {
    return vocab.isEmpty();
  }

  public int size() {
    return vocab.size();
  }

  public double getTau() {
    return tau;
  }

  public void addPredicates(List<BooleanFormula> preds) {
    for (BooleanFormula p : preds) {
      if (bfmgr.isTrue(p) || bfmgr.isFalse(p)) {
        continue;
      }
      boolean exists = vocab.stream().anyMatch(e -> e.predicate.equals(p));
      if (!exists) {
        vocab.add(new VocabEntry(p));
        logger.log(Level.FINE, "VocabularyGuide: ADD", p);
      }
    }
  }

  public void removePredicates(List<BooleanFormula> preds) {
    Set<BooleanFormula> remove = new HashSet<>(preds);
    vocab.removeIf(e -> remove.contains(e.predicate));
  }

  public List<BooleanFormula> getAllPredicates() {
    return vocab.stream().map(e -> e.predicate).toList();
  }

  public void recordConsidered(List<BooleanFormula> preds) {
    for (BooleanFormula p : preds) {
      for (VocabEntry e : vocab) {
        if (e.predicate.equals(p)) {
          e.considered.incrementAndGet();
        }
      }
    }
  }

  public void recordSelected(List<BooleanFormula> preds) {
    for (BooleanFormula p : preds) {
      for (VocabEntry e : vocab) {
        if (e.predicate.equals(p)) {
          e.selected.incrementAndGet();
        }
      }
    }
  }

  public Map<String, Map<String, Integer>> getUsageStats() {
    Map<String, Map<String, Integer>> stats = new LinkedHashMap<>();
    for (VocabEntry e : vocab) {
      stats.put(
          e.predicate.toString(),
          Map.of("considered", e.considered.get(), "selected", e.selected.get()));
    }
    return stats;
  }

  public double score(List<BooleanFormula> preds) {
    if (vocab.isEmpty() || preds.isEmpty()) {
      return 0.0;
    }
    return alpha * subsumptionScore(preds) + (1.0 - alpha) * varOverlapScore(preds);
  }

  public @Nullable ScoredResult selectBest(
      List<Pair<List<BooleanFormula>, String>> candidates) {
    if (candidates.isEmpty()) {
      return null;
    }
    ScoredResult best = null;
    for (Pair<List<BooleanFormula>, String> c : candidates) {
      double s = score(c.getFirst());
      logger.log(Level.FINEST, "VG score: ", c.getSecond(), "=", s);
      if (best == null || s > best.score) {
        best = new ScoredResult(c.getFirst(), s, c.getSecond());
      }
    }
    return best;
  }

  private double subsumptionScore(List<BooleanFormula> preds) {
    int subsumed = 0;
    int nonTrivial = 0;
    for (BooleanFormula p : preds) {
      if (bfmgr.isTrue(p) || bfmgr.isFalse(p)) {
        continue;
      }
      nonTrivial++;
      BooleanFormula notP = bfmgr.not(p);
      for (VocabEntry e : vocab) {
        if (e.predicate.equals(p)) {
          subsumed++;
          break;
        }
        try (ProverEnvironment pe =
            solver.newProverEnvironment(ProverOptions.GENERATE_MODELS)) {
          pe.push(e.predicate);
          pe.push(notP);
          if (pe.isUnsat()) {
            subsumed++;
            break;
          }
        } catch (SolverException | InterruptedException ex) {
          logger.logDebugException(ex, "SMT subsumption check error");
        }
      }
    }
    return nonTrivial == 0 ? 0.0 : (double) subsumed / nonTrivial;
  }

  private double varOverlapScore(List<BooleanFormula> preds) {
    double sum = 0;
    int count = 0;
    for (BooleanFormula p : preds) {
      if (bfmgr.isTrue(p) || bfmgr.isFalse(p)) {
        continue;
      }
      Set<String> pVars = fmgr.extractVariableNames(p);
      if (pVars.isEmpty()) {
        continue;
      }
      double best = 0.0;
      for (VocabEntry e : vocab) {
        Set<String> eVars = fmgr.extractVariableNames(e.predicate);
        double j = jaccard(pVars, eVars);
        if (j > best) {
          best = j;
        }
      }
      sum += best;
      count++;
    }
    return count == 0 ? 0.0 : sum / count;
  }

  private static double jaccard(Set<String> a, Set<String> b) {
    if (a.isEmpty() && b.isEmpty()) {
      return 1.0;
    }
    if (a.isEmpty() || b.isEmpty()) {
      return 0.0;
    }
    Set<String> inter = new HashSet<>(a);
    inter.retainAll(b);
    Set<String> union = new HashSet<>(a);
    union.addAll(b);
    return (double) inter.size() / union.size();
  }
}
