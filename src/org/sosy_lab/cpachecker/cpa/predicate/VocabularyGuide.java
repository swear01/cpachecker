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
import org.sosy_lab.cpachecker.util.predicates.smt.BitvectorFormulaManagerView;
import org.sosy_lab.cpachecker.util.predicates.smt.FormulaManagerView;
import org.sosy_lab.cpachecker.util.predicates.smt.Solver;
import org.sosy_lab.java_smt.api.BooleanFormula;
import org.sosy_lab.java_smt.api.BitvectorFormula;
import org.sosy_lab.java_smt.api.Formula;
import org.sosy_lab.java_smt.api.FormulaType;

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

  public List<BooleanFormula> getFormulasForLocation(
      String locationKey, Set<String> encodedVariableNames) {
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
        f = parseAndCache(e, fmgr, encodedVariableNames);
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
        f = parseAndCache(e, fmgr, Set.of());
      }
      if (f != null) {
        allVars.addAll(fmgr.extractVariableNames(f));
      }
    }
    cachedVariableNames = allVars;
    return allVars;
  }

  private static @Nullable BooleanFormula parseAndCache(
      VocabEntry e, FormulaManagerView fmgr, Set<String> encodedVariableNames) {
    BooleanFormula f = parsePredicate(e.predicateText, fmgr, encodedVariableNames);
    e.parsedFormula = f;
    return f;
  }

  static @Nullable BooleanFormula parsePredicate(
      String expr, FormulaManagerView fmgr, Set<String> encodedVariableNames) {
    expr = expr.strip();
    if (expr.isEmpty() || !expr.startsWith("(")) {
      return null;
    }
    try {
      BooleanFormula result = parseSexp(expr, fmgr, encodedVariableNames);
      if (result != null) {
        try {
          fmgr.getBooleanFormulaManager().isTrue(result);
        } catch (Exception e) {
          return null;
        }
      }
      return result;
    } catch (Exception e) {
      return null;
    }
  }

  private static BooleanFormula parseSexp(
      String expr, FormulaManagerView fmgr, Set<String> encodedVariableNames) {
    expr = expr.strip();
    if (!expr.startsWith("(") || !expr.endsWith(")")) {
      return null;
    }
    String inner = expr.substring(1, expr.length() - 1).trim();
    if (inner.isEmpty()) {
      return null;
    }

    List<String> tokens = tokenizeSexp(inner);
    if (tokens.isEmpty()) {
      return null;
    }

    String op = tokens.get(0);
    List<String> args = tokens.subList(1, tokens.size());

    BooleanFormulaManagerView bfmgr = fmgr.getBooleanFormulaManager();
    BitvectorFormulaManagerView bvmgr = fmgr.getBitvectorFormulaManager();

    return switch (op) {
      case "and" -> {
        BooleanFormula result = parseSexpArg(args.get(0), fmgr, encodedVariableNames);
        for (int i = 1; i < args.size(); i++) {
          result = bfmgr.and(result, parseSexpArg(args.get(i), fmgr, encodedVariableNames));
        }
        yield result;
      }
      case "or" -> {
        BooleanFormula result = parseSexpArg(args.get(0), fmgr, encodedVariableNames);
        for (int i = 1; i < args.size(); i++) {
          result = bfmgr.or(result, parseSexpArg(args.get(i), fmgr, encodedVariableNames));
        }
        yield result;
      }
      case "not" -> bfmgr.not(parseSexpArg(args.get(0), fmgr, encodedVariableNames));
      case "=" -> bvmgr.equal(
          parseBvExpr(args.get(0), fmgr, bvmgr, encodedVariableNames),
          parseBvExpr(args.get(1), fmgr, bvmgr, encodedVariableNames));
      case ">=" -> bvmgr.greaterOrEquals(
          parseBvExpr(args.get(0), fmgr, bvmgr, encodedVariableNames),
          parseBvExpr(args.get(1), fmgr, bvmgr, encodedVariableNames), true);
      case "<=" -> bvmgr.lessOrEquals(
          parseBvExpr(args.get(0), fmgr, bvmgr, encodedVariableNames),
          parseBvExpr(args.get(1), fmgr, bvmgr, encodedVariableNames), true);
      case ">" -> bvmgr.greaterThan(
          parseBvExpr(args.get(0), fmgr, bvmgr, encodedVariableNames),
          parseBvExpr(args.get(1), fmgr, bvmgr, encodedVariableNames), true);
      case "<" -> bvmgr.lessThan(
          parseBvExpr(args.get(0), fmgr, bvmgr, encodedVariableNames),
          parseBvExpr(args.get(1), fmgr, bvmgr, encodedVariableNames), true);
      default -> null;
    };
  }

  private static BooleanFormula parseSexpArg(
      String token, FormulaManagerView fmgr, Set<String> encodedVariableNames) {
    token = token.strip();
    if (token.startsWith("(")) {
      return parseSexp(token, fmgr, encodedVariableNames);
    }
    return null;
  }

  private static BitvectorFormula parseBvExpr(
      String token, FormulaManagerView fmgr, BitvectorFormulaManagerView bvmgr,
      Set<String> encodedVariableNames) {
    token = token.strip();
    if (token.startsWith("(")) {
      return parseBvSexp(token, fmgr, bvmgr, encodedVariableNames);
    }
    if (token.matches("-?\\d+")) {
      return bvmgr.makeBitvector(32, Long.parseLong(token));
    }
    String encoded = resolveVariableName(token, encodedVariableNames);
    return bvmgr.makeVariable(32, encoded);
  }

  private static BitvectorFormula parseBvSexp(
      String expr, FormulaManagerView fmgr, BitvectorFormulaManagerView bvmgr,
      Set<String> encodedVariableNames) {
    expr = expr.strip();
    if (!expr.startsWith("(") || !expr.endsWith(")")) {
      return null;
    }
    String inner = expr.substring(1, expr.length() - 1).trim();
    List<String> tokens = tokenizeSexp(inner);
    if (tokens.isEmpty()) {
      return null;
    }
    String op = tokens.get(0);
    List<String> args = tokens.subList(1, tokens.size());

    return switch (op) {
      case "+" -> bvmgr.add(
          parseBvExpr(args.get(0), fmgr, bvmgr, encodedVariableNames),
          parseBvExpr(args.get(1), fmgr, bvmgr, encodedVariableNames));
      case "-" -> bvmgr.subtract(
          parseBvExpr(args.get(0), fmgr, bvmgr, encodedVariableNames),
          parseBvExpr(args.get(1), fmgr, bvmgr, encodedVariableNames));
      case "*" -> bvmgr.multiply(
          parseBvExpr(args.get(0), fmgr, bvmgr, encodedVariableNames),
          parseBvExpr(args.get(1), fmgr, bvmgr, encodedVariableNames));
      case "mod" -> bvmgr.remainder(
          parseBvExpr(args.get(0), fmgr, bvmgr, encodedVariableNames),
          parseBvExpr(args.get(1), fmgr, bvmgr, encodedVariableNames), false);
      default -> null;
    };
  }

  private static String resolveVariableName(String simpleName, Set<String> encodedNames) {
    for (String encoded : encodedNames) {
      if (encoded.endsWith("::" + simpleName + "@")
          || encoded.contains("::" + simpleName + "@")) {
        return encoded;
      }
    }
    for (String encoded : encodedNames) {
      if (encoded.endsWith(simpleName) || encoded.contains("::" + simpleName)) {
        return encoded;
      }
    }
    return simpleName;
  }

  private static List<String> tokenizeSexp(String inner) {
    List<String> tokens = new ArrayList<>();
    int i = 0;
    while (i < inner.length()) {
      char c = inner.charAt(i);
      if (c == ' ' || c == '\t' || c == '\n' || c == '\r') {
        i++;
        continue;
      }
      if (c == '(') {
        int depth = 1;
        int start = i;
        i++;
        while (i < inner.length() && depth > 0) {
          if (inner.charAt(i) == '(') depth++;
          else if (inner.charAt(i) == ')') depth--;
          i++;
        }
        tokens.add(inner.substring(start, i));
        continue;
      }
      int start = i;
      while (i < inner.length() && inner.charAt(i) != ' '
          && inner.charAt(i) != '\t' && inner.charAt(i) != '\n') {
        i++;
      }
      tokens.add(inner.substring(start, i));
    }
    return tokens;
  }
}
