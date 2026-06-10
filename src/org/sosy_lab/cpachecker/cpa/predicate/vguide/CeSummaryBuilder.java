// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import com.google.common.base.Splitter;
import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableMap;
import com.google.common.collect.ImmutableSet;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.sosy_lab.cpachecker.cfa.model.CFANode;
import org.sosy_lab.cpachecker.core.interfaces.AbstractState;
import org.sosy_lab.cpachecker.util.predicates.smt.FormulaManagerView;
import org.sosy_lab.java_smt.api.BooleanFormula;

/**
 * Builds a compressed CE summary for LLM prompts (loop-head relations + non-redundant interpolants).
 */
public final class CeSummaryBuilder {

  static final int MAX_LOOP_HEADS = 4;
  static final int MAX_RELS_PER_HEAD = 8;
  static final int MAX_INTERPOLANTS = 3;
  static final int MAX_REL_CHARS = 280;
  static final int MAX_TOTAL_CHARS = 12000;

  private static final Pattern IDENT = Pattern.compile("[a-zA-Z_][a-zA-Z0-9_]*");

  private CeSummaryBuilder() {}

  static String build(
      FormulaManagerView fmgr,
      org.sosy_lab.cpachecker.cpa.predicate.BlockFormulaStrategy.BlockFormulas blockFormulas,
      ImmutableList<BooleanFormula> interpolants,
      ImmutableList<LoopHeadInfo> loopHeads,
      ImmutableMap<String, ImmutableSet<String>> varContract,
      String assertion,
      List<? extends AbstractState> abstractionTrace) {
    Map<CFANode, BooleanFormula> blockByNode =
        LoopHeadBlockFormulaIndex.fromTrace(blockFormulas, abstractionTrace);
    Set<String> assertionVars = assertionVarNames(assertion);
    Set<String> seenRelKeys = new HashSet<>();
    StringBuilder sb = new StringBuilder();

    int headsListed = 0;
    for (LoopHeadInfo head : loopHeads) {
      if (headsListed >= MAX_LOOP_HEADS) {
        break;
      }
      BooleanFormula block = blockByNode.get(head.node());
      if (block == null) {
        continue;
      }
      List<String> rels = extractRelations(fmgr, block, varContract, assertionVars, seenRelKeys);
      if (rels.isEmpty()) {
        continue;
      }
      sb.append("  L@").append(head.label()).append(": ");
      for (int i = 0; i < rels.size() && i < MAX_RELS_PER_HEAD; i++) {
        if (i > 0) {
          sb.append(' ');
        }
        sb.append(rels.get(i));
      }
      sb.append('\n');
      headsListed++;
    }

    int itpListed = 0;
    for (BooleanFormula itp : interpolants) {
      if (itpListed >= MAX_INTERPOLANTS) {
        break;
      }
      List<String> rels = extractRelations(fmgr, itp, varContract, assertionVars, seenRelKeys);
      for (String rel : rels) {
        if (itpListed >= MAX_INTERPOLANTS) {
          break;
        }
        sb.append("  interp: ").append(rel).append('\n');
        itpListed++;
      }
    }

    String text = sb.toString().strip();
    if (text.isEmpty()) {
      return "(no CE relations extracted)\n";
    }
    return applyTotalFallback(text);
  }

  private static String applyTotalFallback(String text) {
    if (text.length() <= MAX_TOTAL_CHARS) {
      return text + "\n";
    }
    StringBuilder out = new StringBuilder();
    for (String line : Splitter.on('\n').split(text)) {
      if (out.length() + line.length() + 1 > MAX_TOTAL_CHARS) {
        break;
      }
      if (!out.isEmpty()) {
        out.append('\n');
      }
      out.append(line);
    }
    return out.append('\n').toString();
  }

  private static Set<String> assertionVarNames(String assertion) {
    Set<String> vars = new LinkedHashSet<>();
    Matcher m = IDENT.matcher(assertion);
    while (m.find()) {
      String id = m.group();
      if (!isKeyword(id)) {
        vars.add(id);
      }
    }
    return vars;
  }

  private static boolean isKeyword(String id) {
    return switch (id) {
      case "bv", "true", "false", "not", "and", "or", "let" -> true;
      default -> false;
    };
  }

  private static List<String> extractRelations(
      FormulaManagerView fmgr,
      BooleanFormula formula,
      ImmutableMap<String, ImmutableSet<String>> varContract,
      Set<String> assertionVars,
      Set<String> seenRelKeys) {
    String dump = fmgr.dumpFormula(formula).toString().replace('\n', ' ');
    List<String> assertBodies = extractAssertBodies(dump);
    if (assertBodies.isEmpty() && !dump.isBlank()) {
      assertBodies = List.of(dump);
    }
    List<String> rels = new ArrayList<>();
    List<String> other = new ArrayList<>();
    for (String body : assertBodies) {
      if (body.isEmpty() || isInternalDef(body)) {
        continue;
      }
      String simplified = simplifyEncodedNames(body, varContract);
      simplified = truncateRel(simplified);
      String key = simplified.replaceAll("\\s+", " ").toLowerCase(Locale.ROOT);
      if (seenRelKeys.contains(key)) {
        continue;
      }
      seenRelKeys.add(key);
      if (mentionsAny(simplified, assertionVars)) {
        rels.add(simplified);
      } else {
        other.add(simplified);
      }
    }
    rels.addAll(other);
    return rels;
  }

  private static boolean isInternalDef(String body) {
    return body.contains(".def_") && !body.contains("bv") && !body.contains("=");
  }

  private static boolean mentionsAny(String text, Set<String> vars) {
    for (String v : vars) {
      if (text.contains(v)) {
        return true;
      }
    }
    return false;
  }

  private static String truncateRel(String rel) {
    if (rel.length() <= MAX_REL_CHARS) {
      return rel;
    }
    return rel.substring(0, MAX_REL_CHARS - 3) + "...";
  }

  private static List<String> extractAssertBodies(String smtDump) {
    List<String> out = new ArrayList<>();
    int i = 0;
    while (i < smtDump.length()) {
      int a = smtDump.indexOf("(assert ", i);
      if (a < 0) {
        break;
      }
      int start = a + 8;
      int depth = 1;
      int j = start;
      while (j < smtDump.length() && depth > 0) {
        char c = smtDump.charAt(j);
        if (c == '(') {
          depth++;
        } else if (c == ')') {
          depth--;
        }
        j++;
      }
      if (depth == 0) {
        out.add(smtDump.substring(start, j - 1).trim());
        i = j;
      } else {
        break;
      }
    }
    return out;
  }

  private static String simplifyEncodedNames(
      String smt, ImmutableMap<String, ImmutableSet<String>> varContract) {
    String result = smt;
    for (var e : varContract.entrySet()) {
      String source = e.getKey();
      for (String encoded : e.getValue()) {
        result = result.replace(encoded, source);
      }
    }
    result = result.replaceAll("\\|main::([^|@]+)@[0-9]+\\|", "$1");
    result = result.replaceAll("\\s+", " ").strip();
    return result;
  }
}
