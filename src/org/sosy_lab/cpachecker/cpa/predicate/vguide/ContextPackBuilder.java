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
      CounterexampleTraceInfo counterexample,
      List<? extends org.sosy_lab.cpachecker.core.interfaces.AbstractState> abstractionTrace) {
    Set<String> encodedVars = new HashSet<>();
    for (BooleanFormula f : formulas.getFormulas()) {
      encodedVars.addAll(fmgr.extractVariableNames(f));
    }
    ImmutableList<BooleanFormula> itps =
        counterexample.isSpurious() && counterexample.getInterpolants() != null
            ? counterexample.getInterpolants()
            : ImmutableList.of();
    String source = readSource();
    String assertion = extractAssertion(source);
    var varContract = VarContractBuilder.build(encodedVars);
    ImmutableList<LoopHeadInfo> loopHeads = loopHeadIndex.getLoopHeads();
    String ceSummary =
        CeSummaryBuilder.build(
            fmgr, formulas, itps, loopHeads, varContract, assertion, abstractionTrace);
    return new ContextPack(
        refinementIndex,
        source,
        assertion,
        loopHeads,
        varContract,
        ImmutableSet.copyOf(encodedVars),
        formulas,
        itps,
        ceSummary,
        "");
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
