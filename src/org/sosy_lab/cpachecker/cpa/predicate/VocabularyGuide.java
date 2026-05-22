// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-FileCopyrightText: 2007-2020 Dirk Beyer <https://www.sosy-lab.org>
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.logging.Level;
import org.checkerframework.checker.nullness.qual.Nullable;
import org.sosy_lab.common.log.LogManager;
import org.sosy_lab.cpachecker.util.predicates.smt.BooleanFormulaManagerView;
import org.sosy_lab.cpachecker.util.predicates.smt.FormulaManagerView;
import org.sosy_lab.cpachecker.util.predicates.smt.IntegerFormulaManagerView;
import org.sosy_lab.cpachecker.util.predicates.smt.Solver;
import org.sosy_lab.java_smt.api.BooleanFormula;
import org.sosy_lab.java_smt.api.NumeralFormula.IntegerFormula;

/**
 * Dynamic Predicate Vocabulary V maintained by the LLM. Stores per-location predicates as strings,
 * with lazy parsing to BooleanFormula. Supports variable-overlap filtering for predicate quality
 * control.
 */
public class VocabularyGuide {

  static class VocabEntry {
    final String locationKey;
    final String predicateText;
    final Set<String> variableNames;
    volatile @Nullable BooleanFormula parsedFormula;

    VocabEntry(String pLocationKey, String pPredicateText) {
      locationKey = pLocationKey;
      predicateText = pPredicateText;
      variableNames = extractVariableNamesFromText(pPredicateText);
    }

    @Override
    public boolean equals(Object o) {
      if (this == o) {
        return true;
      }
      if (!(o instanceof VocabEntry other)) {
        return false;
      }
      return locationKey.equals(other.locationKey) && predicateText.equals(other.predicateText);
    }

    @Override
    public int hashCode() {
      return 31 * locationKey.hashCode() + predicateText.hashCode();
    }
  }

  private final @Nullable Solver solver;
  private final LogManager logger;

  private final CopyOnWriteArrayList<VocabEntry> vocab = new CopyOnWriteArrayList<>();
  private volatile Set<String> cachedVariableNames;

  public VocabularyGuide(@Nullable Solver pSolver, LogManager pLogger) {
    solver = pSolver;
    logger = pLogger;
  }

  public boolean isEmpty() {
    return vocab.isEmpty();
  }

  public int size() {
    return vocab.size();
  }

  public void addPredicate(String locationKey, String predicateText, int unused) {
    addPredicate(locationKey, predicateText);
  }

  public void addPredicate(String locationKey, String predicateText) {
    if (predicateText == null || predicateText.isBlank()) {
      return;
    }
    VocabEntry entry = new VocabEntry(locationKey, predicateText.strip());
    if (!vocab.contains(entry)) {
      vocab.add(entry);
      cachedVariableNames = null;
      logger.log(Level.FINE, "VocabularyGuide: ADD [", locationKey, "] ", predicateText);
    }
  }

  public void addPredicates(String locationKey, List<String> predicateTexts) {
    for (String text : predicateTexts) {
      addPredicate(locationKey, text);
    }
  }

  public void removePredicate(String locationKey, String predicateText) {
    vocab.removeIf(e -> e.locationKey.equals(locationKey) && e.predicateText.equals(predicateText));
    cachedVariableNames = null;
  }

  public void removePredicates(List<BooleanFormula> preds) {
    vocab.removeIf(e -> {
      BooleanFormula pf = e.parsedFormula;
      return pf != null && preds.contains(pf);
    });
    cachedVariableNames = null;
  }

  public void addPredicates(List<BooleanFormula> preds) {
    if (solver == null) {
      return;
    }
    BooleanFormulaManagerView bfmgr = solver.getFormulaManager().getBooleanFormulaManager();
    for (BooleanFormula p : preds) {
      if (bfmgr.isTrue(p) || bfmgr.isFalse(p)) {
        continue;
      }
      String text = p.toString();
      boolean exists = vocab.stream().anyMatch(e -> e.predicateText.equals(text));
      if (!exists) {
        VocabEntry entry = new VocabEntry("", text);
        entry.parsedFormula = p;
        vocab.add(entry);
        cachedVariableNames = null;
        logger.log(Level.FINE, "VocabularyGuide: ADD (flat) ", p);
      }
    }
  }

  public List<String> getPredicateStringsForLocation(String locationKey) {
    List<String> result = new ArrayList<>();
    for (VocabEntry e : vocab) {
      if (e.locationKey.equals(locationKey)) {
        result.add(e.predicateText);
      }
    }
    return result;
  }

  public List<String> getAllLocations() {
    Set<String> locs = new LinkedHashSet<>();
    for (VocabEntry e : vocab) {
      locs.add(e.locationKey);
    }
    List<String> sorted = new ArrayList<>(locs);
    sorted.sort(Comparator.naturalOrder());
    return sorted;
  }

  public void clearAll() {
    vocab.clear();
    cachedVariableNames = null;
  }

  public List<BooleanFormula> getAllPredicates() {
    List<BooleanFormula> result = new ArrayList<>();
    for (VocabEntry e : vocab) {
      BooleanFormula f = e.parsedFormula;
      if (f != null) {
        result.add(f);
      }
    }
    return result;
  }

  public List<BooleanFormula> getFormulasForLocation(String locationKey) {
    if (solver == null) {
      return List.of();
    }
    FormulaManagerView fmgr = solver.getFormulaManager();
    BooleanFormulaManagerView bfmgr = fmgr.getBooleanFormulaManager();
    IntegerFormulaManagerView ifmgr = fmgr.getIntegerFormulaManager();
    List<BooleanFormula> result = new ArrayList<>();
    for (VocabEntry e : vocab) {
      if (!e.locationKey.equals(locationKey)) {
        continue;
      }
      BooleanFormula f = e.parsedFormula;
      if (f == null) {
        f = parseAndCache(e, bfmgr, ifmgr);
      }
      if (f != null) {
        result.add(f);
      }
    }
    return result;
  }

  public boolean hasVariableOverlap(BooleanFormula candidate) {
    if (solver == null) {
      return false;
    }
    Set<String> vVars = getVariableNames();
    if (vVars.isEmpty()) {
      return false;
    }
    Set<String> candVars = solver.getFormulaManager().extractVariableNames(candidate);
    for (String v : candVars) {
      if (vVars.contains(v)) {
        return true;
      }
    }
    return false;
  }

  public Set<String> getVariableNames() {
    if (cachedVariableNames != null) {
      return cachedVariableNames;
    }
    Set<String> allVars = new HashSet<>();
    for (VocabEntry e : vocab) {
      allVars.addAll(e.variableNames);
    }
    cachedVariableNames = allVars;
    return allVars;
  }

  private static @Nullable BooleanFormula parseAndCache(
      VocabEntry e,
      BooleanFormulaManagerView bfmgr,
      IntegerFormulaManagerView ifmgr) {
    BooleanFormula f = parsePredicate(e.predicateText, bfmgr, ifmgr);
    e.parsedFormula = f;
    return f;
  }

  private static Set<String> extractVariableNamesFromText(String predicateText) {
    Set<String> vars = new HashSet<>();
    String text = predicateText.strip();
    String[] ops = {" >= ", " <= ", " != ", " == ", " < ", " > "};
    String leftPart = null;
    String rightPart = null;
    for (String op : ops) {
      int idx = text.indexOf(op);
      if (idx >= 0) {
        leftPart = text.substring(0, idx).strip();
        rightPart = text.substring(idx + op.length()).strip();
        break;
      }
    }
    if (leftPart != null) {
      addIfVariable(vars, leftPart);
    }
    if (rightPart != null) {
      addIfVariable(vars, rightPart);
    }
    return vars;
  }

  private static void addIfVariable(Set<String> vars, String token) {
    if (token.isEmpty() || "NULL".equals(token)) {
      return;
    }
    if (token.matches("-?\\d+")) {
      return;
    }
    vars.add(token);
  }

  static @Nullable BooleanFormula parsePredicate(
      String expr,
      BooleanFormulaManagerView bfmgr,
      IntegerFormulaManagerView ifmgr) {
    expr = expr.strip();
    try {
      String[] parts;
      String op;
      if (expr.contains(" >= ")) {
        parts = expr.split(" >= ");
        op = ">=";
      } else if (expr.contains(" <= ")) {
        parts = expr.split(" <= ");
        op = "<=";
      } else if (expr.contains(" != ")) {
        parts = expr.split(" != ");
        op = "!=";
      } else if (expr.contains(" == ")) {
        parts = expr.split(" == ");
        op = "==";
      } else if (expr.contains(" < ")) {
        parts = expr.split(" < ");
        op = "<";
      } else if (expr.contains(" > ")) {
        parts = expr.split(" > ");
        op = ">";
      } else {
        return null;
      }
      if (parts.length != 2) {
        return null;
      }
      String left = parts[0].strip();
      String right = parts[1].strip();
      if ("NULL".equals(right)) {
        return bfmgr.not(ifmgr.equal(ifmgr.makeVariable(left), ifmgr.makeNumber(0)));
      }
      IntegerFormula lv = ifmgr.makeVariable(left);
      try {
        long rv = Long.parseLong(right);
        IntegerFormula rvf = ifmgr.makeNumber(rv);
        return switch (op) {
          case ">=" -> bfmgr.not(ifmgr.lessThan(lv, rvf));
          case "<=" -> bfmgr.not(ifmgr.greaterThan(lv, rvf));
          case "!=" -> bfmgr.not(ifmgr.equal(lv, rvf));
          case "==" -> ifmgr.equal(lv, rvf);
          case "<" -> ifmgr.lessThan(lv, rvf);
          case ">" -> ifmgr.greaterThan(lv, rvf);
          default -> null;
        };
      } catch (NumberFormatException e2) {
        IntegerFormula rv2 = ifmgr.makeVariable(right);
        return switch (op) {
          case ">=" -> bfmgr.not(ifmgr.lessThan(lv, rv2));
          case "<=" -> bfmgr.not(ifmgr.greaterThan(lv, rv2));
          case "!=" -> bfmgr.not(ifmgr.equal(lv, rv2));
          case "==" -> ifmgr.equal(lv, rv2);
          case "<" -> ifmgr.lessThan(lv, rv2);
          case ">" -> ifmgr.greaterThan(lv, rv2);
          default -> null;
        };
      }
    } catch (Exception e) {
      return null;
    }
  }
}
