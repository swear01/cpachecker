// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-FileCopyrightText: 2026 Dirk Beyer <https://www.sosy-lab.org>
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.core.algorithm.termination.lasso_analysis.vguide;

import static com.google.common.base.Preconditions.checkNotNull;

import com.google.common.collect.ImmutableMap;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.checkerframework.checker.nullness.qual.Nullable;
import org.sosy_lab.cpachecker.util.predicates.smt.BooleanFormulaManagerView;
import org.sosy_lab.cpachecker.util.predicates.smt.FormulaManagerView;
import org.sosy_lab.cpachecker.util.predicates.smt.IntegerFormulaManagerView;
import org.sosy_lab.java_smt.api.BooleanFormula;
import org.sosy_lab.java_smt.api.NumeralFormula.IntegerFormula;

/**
 * Parses an LLM-proposed ranking function / supporting invariant given as a prefix S-expression
 * into JavaSMT formulas over the (linear-integer) program variables. The lasso/termination analysis
 * uses integer arithmetic ({@code encodeBitvectorAs=INTEGER}), so terms are built with the integer
 * theory.
 *
 * <p>The ranking function is parsed into a {@link LinearTerm} (constant + integer coefficients over
 * qualified variable names); this both enforces linearity and lets {@link RankingRelationFactory}
 * build the primed/unprimed ranking relation. Supported relations inside invariants: {@code >= <= >
 * < =} over linear terms, combined with {@code and/or/not} (plus {@code true}/{@code false}).
 *
 * <p>Anything outside this grammar (non-linear multiplication, unknown variables, malformed input)
 * yields {@code null} so the candidate is discarded — a parse failure can never make a candidate
 * look valid.
 */
public final class RankingTermParser {

  private final IntegerFormulaManagerView ifmgr;
  private final BooleanFormulaManagerView bfmgr;
  // source/qualified variable name -> qualified name used in the loop formula
  private final ImmutableMap<String, String> nameToQualified;

  public RankingTermParser(FormulaManagerView pFmgr, Map<String, String> pNameToQualified) {
    ifmgr = pFmgr.getIntegerFormulaManager();
    bfmgr = pFmgr.getBooleanFormulaManager();
    nameToQualified = ImmutableMap.copyOf(checkNotNull(pNameToQualified));
  }

  /** A linear integer term: {@code constant + sum(coeff_i * qualifiedVar_i)}. */
  public record LinearTerm(ImmutableMap<String, Long> coefficients, long constant) {

    /** Builds the integer formula, appending {@code varSuffix} to each variable name. */
    IntegerFormula toFormula(IntegerFormulaManagerView fmgr, String varSuffix) {
      IntegerFormula result = fmgr.makeNumber(constant);
      for (Map.Entry<String, Long> e : coefficients.entrySet()) {
        IntegerFormula v = fmgr.makeVariable(e.getKey() + varSuffix);
        IntegerFormula summand =
            e.getValue() == 1L ? v : fmgr.multiply(fmgr.makeNumber(e.getValue()), v);
        result = fmgr.add(result, summand);
      }
      return result;
    }
  }

  /** Parses a ranking-function term into a linear form; {@code null} if unparseable/non-linear. */
  public @Nullable LinearTerm parseLinear(String pExpr) {
    Object tree = parseTree(pExpr);
    return tree == null ? null : evalLinear(tree);
  }

  /** Parses a ranking-function term as an integer formula over the (unsuffixed) variables. */
  public @Nullable IntegerFormula parseTerm(String pExpr) {
    LinearTerm lt = parseLinear(pExpr);
    return lt == null ? null : lt.toFormula(ifmgr, "");
  }

  /**
   * Parses a supporting invariant; an empty input or the literal {@code true} yields {@code true}.
   * Returns {@code null} if unparseable.
   */
  public @Nullable BooleanFormula parseInvariant(@Nullable String pExpr) {
    if (pExpr == null || pExpr.isBlank() || pExpr.strip().equalsIgnoreCase("true")) {
      return bfmgr.makeTrue();
    }
    Object tree = parseTree(pExpr);
    return tree == null ? null : toBool(tree);
  }

  // ---- linear term evaluation -------------------------------------------------

  private @Nullable LinearTerm evalLinear(Object node) {
    if (node instanceof String atom) {
      Long literal = tryParseLong(atom);
      if (literal != null) {
        return new LinearTerm(ImmutableMap.of(), literal);
      }
      String qualified = nameToQualified.get(atom);
      return qualified == null
          ? null
          : new LinearTerm(ImmutableMap.of(qualified, 1L), 0L);
    }
    @SuppressWarnings("unchecked")
    List<Object> list = (List<Object>) node;
    if (list.isEmpty() || !(list.get(0) instanceof String op)) {
      return null;
    }
    List<Object> args = list.subList(1, list.size());
    return switch (op) {
      case "+" -> {
        if (args.isEmpty()) {
          yield null;
        }
        LinearTerm acc = evalLinear(args.get(0));
        for (int i = 1; i < args.size() && acc != null; i++) {
          acc = add(acc, evalLinear(args.get(i)));
        }
        yield acc;
      }
      case "-" -> {
        if (args.size() == 1) {
          yield scale(evalLinear(args.get(0)), -1L);
        }
        if (args.size() == 2) {
          yield add(evalLinear(args.get(0)), scale(evalLinear(args.get(1)), -1L));
        }
        yield null;
      }
      case "*" -> {
        if (args.size() != 2) {
          yield null;
        }
        Long c0 = (args.get(0) instanceof String s) ? tryParseLong(s) : null;
        Long c1 = (args.get(1) instanceof String s) ? tryParseLong(s) : null;
        if (c0 != null) {
          yield scale(evalLinear(args.get(1)), c0);
        }
        if (c1 != null) {
          yield scale(evalLinear(args.get(0)), c1);
        }
        yield null; // non-linear
      }
      default -> null;
    };
  }

  private static @Nullable LinearTerm add(@Nullable LinearTerm a, @Nullable LinearTerm b) {
    if (a == null || b == null) {
      return null;
    }
    Map<String, Long> coeffs = new LinkedHashMap<>(a.coefficients());
    for (Map.Entry<String, Long> e : b.coefficients().entrySet()) {
      long sum = coeffs.getOrDefault(e.getKey(), 0L) + e.getValue();
      if (sum == 0L) {
        coeffs.remove(e.getKey());
      } else {
        coeffs.put(e.getKey(), sum);
      }
    }
    return new LinearTerm(ImmutableMap.copyOf(coeffs), a.constant() + b.constant());
  }

  private static @Nullable LinearTerm scale(@Nullable LinearTerm t, long factor) {
    if (t == null) {
      return null;
    }
    if (factor == 0L) {
      return new LinearTerm(ImmutableMap.of(), 0L);
    }
    Map<String, Long> coeffs = new LinkedHashMap<>();
    for (Map.Entry<String, Long> e : t.coefficients().entrySet()) {
      coeffs.put(e.getKey(), e.getValue() * factor);
    }
    return new LinearTerm(ImmutableMap.copyOf(coeffs), t.constant() * factor);
  }

  // ---- invariant (boolean) construction --------------------------------------

  private @Nullable BooleanFormula toBool(Object node) {
    if (node instanceof String atom) {
      if (atom.equalsIgnoreCase("true")) {
        return bfmgr.makeTrue();
      }
      if (atom.equalsIgnoreCase("false")) {
        return bfmgr.makeFalse();
      }
      return null;
    }
    @SuppressWarnings("unchecked")
    List<Object> list = (List<Object>) node;
    if (list.isEmpty() || !(list.get(0) instanceof String op)) {
      return null;
    }
    List<Object> args = list.subList(1, list.size());
    return switch (op) {
      case "and", "or" -> {
        if (args.isEmpty()) {
          yield null;
        }
        BooleanFormula acc = toBool(args.get(0));
        for (int i = 1; i < args.size() && acc != null; i++) {
          BooleanFormula next = toBool(args.get(i));
          if (next == null) {
            yield null;
          }
          acc = op.equals("and") ? bfmgr.and(acc, next) : bfmgr.or(acc, next);
        }
        yield acc;
      }
      case "not" -> {
        if (args.size() != 1) {
          yield null;
        }
        BooleanFormula b = toBool(args.get(0));
        yield b == null ? null : bfmgr.not(b);
      }
      case ">=", "<=", ">", "<", "=" -> {
        if (args.size() != 2) {
          yield null;
        }
        LinearTerm a = evalLinear(args.get(0));
        LinearTerm b = evalLinear(args.get(1));
        if (a == null || b == null) {
          yield null;
        }
        IntegerFormula fa = a.toFormula(ifmgr, "");
        IntegerFormula fb = b.toFormula(ifmgr, "");
        yield switch (op) {
          case ">=" -> bfmgr.not(ifmgr.lessThan(fa, fb));
          case "<=" -> bfmgr.not(ifmgr.greaterThan(fa, fb));
          case ">" -> ifmgr.greaterThan(fa, fb);
          case "<" -> ifmgr.lessThan(fa, fb);
          default -> ifmgr.equal(fa, fb);
        };
      }
      default -> null;
    };
  }

  // ---- S-expression parsing ---------------------------------------------------

  private @Nullable Object parseTree(String pExpr) {
    List<String> tokens = tokenize(pExpr);
    if (tokens.isEmpty()) {
      return null;
    }
    int[] pos = {0};
    Object tree = parseTokens(tokens, pos);
    return pos[0] == tokens.size() ? tree : null; // reject trailing garbage
  }

  private @Nullable Object parseTokens(List<String> tokens, int[] pos) {
    if (pos[0] >= tokens.size()) {
      return null;
    }
    String tok = tokens.get(pos[0]++);
    if (tok.equals("(")) {
      List<Object> list = new ArrayList<>();
      while (pos[0] < tokens.size() && !tokens.get(pos[0]).equals(")")) {
        Object child = parseTokens(tokens, pos);
        if (child == null) {
          return null;
        }
        list.add(child);
      }
      if (pos[0] >= tokens.size()) {
        return null; // unbalanced
      }
      pos[0]++; // consume ")"
      return list;
    }
    if (tok.equals(")")) {
      return null;
    }
    return tok; // atom
  }

  private static List<String> tokenize(String pExpr) {
    List<String> tokens = new ArrayList<>();
    StringBuilder cur = new StringBuilder();
    for (int i = 0; i < pExpr.length(); i++) {
      char c = pExpr.charAt(i);
      if (c == '(' || c == ')') {
        flush(cur, tokens);
        tokens.add(String.valueOf(c));
      } else if (Character.isWhitespace(c)) {
        flush(cur, tokens);
      } else {
        cur.append(c);
      }
    }
    flush(cur, tokens);
    return tokens;
  }

  private static void flush(StringBuilder cur, List<String> tokens) {
    if (cur.length() > 0) {
      tokens.add(cur.toString());
      cur.setLength(0);
    }
  }

  private static @Nullable Long tryParseLong(String s) {
    try {
      return Long.parseLong(s);
    } catch (NumberFormatException e) {
      return null;
    }
  }
}
