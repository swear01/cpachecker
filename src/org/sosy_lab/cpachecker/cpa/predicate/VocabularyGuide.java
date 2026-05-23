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
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.checkerframework.checker.nullness.qual.Nullable;
import org.sosy_lab.common.log.LogManager;
import org.sosy_lab.cpachecker.util.predicates.smt.BooleanFormulaManagerView;
import org.sosy_lab.cpachecker.util.predicates.smt.FormulaManagerView;
import org.sosy_lab.cpachecker.util.predicates.smt.Solver;
import org.sosy_lab.java_smt.api.BooleanFormula;

/**
 * Dynamic Predicate Vocabulary V maintained by the LLM. Stores per-location predicates as strings,
 * with lazy parsing to BooleanFormula. Supports variable-overlap filtering for predicate quality
 * control.
 */
public class VocabularyGuide {

  static class VocabEntry {
    final String locationKey;
    final String predicateText;
    volatile @Nullable BooleanFormula parsedFormula;

    VocabEntry(String pLocationKey, String pPredicateText) {
      locationKey = pLocationKey;
      predicateText = pPredicateText;
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
    List<BooleanFormula> result = new ArrayList<>();
    for (VocabEntry e : vocab) {
      if (!e.locationKey.equals(locationKey)) {
        continue;
      }
      BooleanFormula f = e.parsedFormula;
      if (f == null) {
        f = parseAndCache(e, fmgr);
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
    if (solver == null) {
      return Set.of();
    }
    FormulaManagerView fmgr = solver.getFormulaManager();
    Set<String> allVars = new HashSet<>();
    for (VocabEntry e : vocab) {
      BooleanFormula f = e.parsedFormula;
      if (f == null) {
        f = parseAndCache(e, fmgr);
      }
      if (f != null) {
        allVars.addAll(fmgr.extractVariableNames(f));
      }
    }
    cachedVariableNames = allVars;
    return allVars;
  }

  private static @Nullable BooleanFormula parseAndCache(
      VocabEntry e, FormulaManagerView fmgr) {
    BooleanFormula f = parsePredicate(e.predicateText, fmgr);
    e.parsedFormula = f;
    return f;
  }

  static @Nullable BooleanFormula parsePredicate(
      String expr, FormulaManagerView fmgr) {
    try {
      return fmgr.parse("(assert " + expr + ")");
    } catch (IllegalArgumentException first) {
      try {
        Set<String> vars = new HashSet<>();
        Matcher m = IDENTIFIER_PATTERN.matcher(expr);
        while (m.find()) {
          String v = m.group(1);
          if (!SMT_RESERVED_WORDS.contains(v) && !v.matches("\\d+")) {
            vars.add(v);
          }
        }
        StringBuilder sb = new StringBuilder();
        for (String v : vars) {
          sb.append("(declare-fun ").append(v).append(" () Int) ");
        }
        sb.append("(assert ").append(expr).append(")");
        return fmgr.parse(sb.toString());
      } catch (IllegalArgumentException second) {
        return null;
      }
    }
  }

  private static final Pattern IDENTIFIER_PATTERN =
      Pattern.compile("\\b([a-zA-Z_][a-zA-Z0-9_]*)\\b");

  private static final Set<String> SMT_RESERVED_WORDS =
      Set.of(
          "assert",
          "declare",
          "fun",
          "mod",
          "div",
          "and",
          "or",
          "not",
          "ite",
          "true",
          "false",
          "Int",
          "Bool",
          "Array",
          "BitVec",
          "Float16",
          "Float32",
          "Float64",
          "RoundingMode");
}
