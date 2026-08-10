// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.truth.Truth.assertThat;

import org.junit.Test;

/** LLM-predicate lifecycle ownership keys (Issue #8). */
public class LlmPredicateLifecycleTest {

  @Test
  public void ownershipKeyIsDeterministicAndScopedPerNode() {
    assertThat(VGuideRefinementBridge.llmOwnedKey(12, "(bvslt i n)"))
        .isEqualTo("local N12|(bvslt i n)");
    assertThat(VGuideRefinementBridge.llmOwnedKey(15, "(bvslt i n)"))
        .isEqualTo("local N15|(bvslt i n)");
    assertThat(VGuideRefinementBridge.llmOwnedKey(12, "(bvslt i n)"))
        .isNotEqualTo(VGuideRefinementBridge.llmOwnedKey(15, "(bvslt i n)"));
  }

  @Test
  public void ownershipKeySurvivesCanonicalRoundTripShape() {
    // Recording and removal both build keys via llmOwnedKey(nodeNumber, canonical(formula));
    // the canonical form is the fmgr dump string, which may contain spaces.
    assertThat(VGuideRefinementBridge.llmOwnedKey(3, "(= x (_ bv1 32))"))
        .isEqualTo("local N3|(= x (_ bv1 32))");
  }
}
