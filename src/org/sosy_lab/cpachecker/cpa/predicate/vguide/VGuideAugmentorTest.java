// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-FileCopyrightText: 2026 SSU-WEI HUANG <https://github.com/swear01>
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.truth.Truth.assertThat;

import com.google.common.collect.ImmutableMap;
import org.junit.Test;
import org.sosy_lab.cpachecker.cfa.ImmutableCFA;
import org.sosy_lab.cpachecker.util.predicates.smt.SolverViewBasedTest0;
import org.sosy_lab.cpachecker.util.test.TestCfaUtils;
import org.sosy_lab.java_smt.SolverContextFactory.Solvers;
import org.sosy_lab.java_smt.api.BooleanFormula;

public class VGuideAugmentorTest extends SolverViewBasedTest0 {

  @Override
  protected Solvers solverToUse() {
    return Solvers.Z3;
  }

  @Test
  public void acceptsOnlyDeclaredVariableAndExactBitvectorSort() {
    BooleanFormula accepted =
        mgrv.parse(
            """
            (declare-fun |main::x| () (_ BitVec 32))
            (assert (= |main::x| (_ bv0 32)))
            """);
    BooleanFormula wrongWidth =
        mgrv.parse(
            """
            (declare-fun |main::x| () (_ BitVec 64))
            (assert (= |main::x| (_ bv0 64)))
            """);
    BooleanFormula unknownVariable =
        mgrv.parse(
            """
            (declare-fun |main::y| () (_ BitVec 32))
            (assert (= |main::y| (_ bv0 32)))
            """);
    BooleanFormula uninterpretedFunction =
        mgrv.parse(
            """
            (declare-fun |main::x| () (_ BitVec 32))
            (declare-fun f ((_ BitVec 32)) Bool)
            (assert (f |main::x|))
            """);
    BooleanFormula variableFree = mgrv.parse("(assert (= (_ bv0 32) (_ bv1 32)))");
    ImmutableMap<String, Integer> allowed = ImmutableMap.of("main::x", 32);

    assertThat(VGuideAugmentor.variablesHaveExpectedTypes(mgrv, allowed, accepted)).isTrue();
    assertThat(VGuideAugmentor.variablesHaveExpectedTypes(mgrv, allowed, wrongWidth)).isFalse();
    assertThat(VGuideAugmentor.variablesHaveExpectedTypes(mgrv, allowed, unknownVariable))
        .isFalse();
    assertThat(VGuideAugmentor.variablesHaveExpectedTypes(mgrv, allowed, uninterpretedFunction))
        .isFalse();
    assertThat(VGuideAugmentor.variablesHaveExpectedTypes(mgrv, allowed, variableFree)).isFalse();
  }

  @Test
  public void contextExposesRelevantCVariablesWithMachineWidths() throws Exception {
    ImmutableCFA cfa =
        TestCfaUtils.makeCFA("int main() { int x = 0; while (x < 4) { x++; } return x; }");

    assertThat(VGuideAugmentor.collectVariables(cfa))
        .containsEntry("main::x", cfa.getMachineModel().getSizeofInt() * 8);
  }
}
