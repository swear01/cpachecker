// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableSet;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.sosy_lab.cpachecker.cfa.CFA;
import org.sosy_lab.cpachecker.cpa.predicate.BlockFormulaStrategy.BlockFormulas;
import org.sosy_lab.cpachecker.util.predicates.interpolation.CounterexampleTraceInfo;
import org.sosy_lab.cpachecker.util.predicates.smt.FormulaManagerView;
import org.sosy_lab.java_smt.api.BooleanFormula;

/** Builds {@link ContextPack} from a spurious refinement event. */
public final class ContextPackBuilder {

  private static final Pattern ASSERTION =
      Pattern.compile("__VERIFIER_assert\\s*\\(\\s*(.+?)\\s*\\)");

  private final CFA cfa;
  private final LoopHeadIndex loopHeadIndex;
  private final FormulaManagerView fmgr;

  public ContextPackBuilder(CFA cfa, LoopHeadIndex loopHeadIndex, FormulaManagerView fmgr) {
    this.cfa = cfa;
    this.loopHeadIndex = loopHeadIndex;
    this.fmgr = fmgr;
  }

  public ContextPack build(
      int refinementIndex,
      BlockFormulas formulas,
      CounterexampleTraceInfo counterexample) {
    Set<String> encodedVars = new HashSet<>();
    for (BooleanFormula f : formulas.getFormulas()) {
      encodedVars.addAll(fmgr.extractVariableNames(f));
    }
    String traceSummary = summarizeTrace(formulas);
    ImmutableList<BooleanFormula> itps =
        counterexample.isSpurious() && counterexample.getInterpolants() != null
            ? counterexample.getInterpolants()
            : ImmutableList.of();
    return new ContextPack(
        refinementIndex,
        readSource(),
        extractAssertion(readSource()),
        loopHeadIndex.getLoopHeads(),
        VarContractBuilder.build(encodedVars),
        ImmutableSet.copyOf(encodedVars),
        formulas,
        itps,
        traceSummary);
  }

  private String summarizeTrace(BlockFormulas formulas) {
    StringBuilder sb = new StringBuilder();
    int n = Math.min(5, formulas.getSize());
    for (int i = 0; i < n; i++) {
      sb.append("block ")
          .append(i)
          .append(": ")
          .append(fmgr.dumpFormula(formulas.getFormulas().get(i)).toString().replace('\n', ' '))
          .append('\n');
    }
    if (formulas.getSize() > n) {
      sb.append("... (").append(formulas.getSize() - n).append(" more blocks)\n");
    }
    return sb.toString();
  }

  private String readSource() {
    try {
      StringBuilder sb = new StringBuilder();
      for (Path f : cfa.getFileNames()) {
        sb.append("// File: ").append(f.getFileName()).append('\n');
        sb.append(Files.readString(f)).append('\n');
      }
      return sb.toString();
    } catch (IOException e) {
      return "// source unavailable";
    }
  }

  static String extractAssertion(String source) {
    Matcher m = ASSERTION.matcher(source);
    if (m.find()) {
      return m.group(1).trim();
    }
    return "";
  }
}
