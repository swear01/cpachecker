// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.truth.Truth.assertThat;

import java.util.List;
import org.junit.Test;

public class PredicateUsefulnessGateTest {

  @Test
  public void rejectsSeveralMultiplicativePredicatesOnShortPeel() {
    PredicateUsefulnessGate.Decision decision =
        PredicateUsefulnessGate.evaluateDumped(
            8,
            List.of(
                "(assert (= x (bvmul y z)))",
                "(assert (bvsle (bvmul a b) c))",
                "(assert (bvsle x y))"));

    assertThat(decision.rejects()).isTrue();
    assertThat(decision.uniqueMultiplicativePredicates()).isEqualTo(2);
    assertThat(decision.uniqueValidatedPredicates()).isEqualTo(3);
    assertThat(decision.canonicalPredicateHashes()).hasSize(3);
  }

  @Test
  public void acceptsAtMostOneMultiplicativePredicate() {
    assertThat(
            PredicateUsefulnessGate.evaluateDumped(
                    8,
                    List.of(
                        "(assert (= x (bvmul y z)))",
                        "(assert (= x (bvmul y z)))",
                        "(assert (bvsle x y))"))
                .rejects())
        .isFalse();
  }

  @Test
  public void ignoresLoopHeadAndProfileDuplication() {
    PredicateUsefulnessGate.Decision decision =
        PredicateUsefulnessGate.evaluateDumped(
            8,
            List.of(
                "(assert (= x (bvmul y z)))",
                "(assert (= x (bvmul y z)))",
                "(assert (bvsle x y))"));

    assertThat(decision.uniqueValidatedPredicates()).isEqualTo(2);
    assertThat(decision.uniqueMultiplicativePredicates()).isEqualTo(1);
    assertThat(decision.rejects()).isFalse();
  }

  @Test
  public void exposesFrozenRuleVersion() {
    assertThat(PredicateUsefulnessGate.RULE_VERSION).isEqualTo("frozen-20260711");
  }

  @Test
  public void acceptsLongerPeel() {
    assertThat(
            PredicateUsefulnessGate.evaluateDumped(
                    9,
                    List.of(
                        "(assert (= x (bvmul y z)))",
                        "(assert (bvsle (bvmul a b) c))"))
                .rejects())
        .isFalse();
  }
}
