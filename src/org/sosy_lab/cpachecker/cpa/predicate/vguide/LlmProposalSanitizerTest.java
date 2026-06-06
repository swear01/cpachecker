// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.truth.Truth.assertThat;

import java.util.List;
import org.junit.Test;

public class LlmProposalSanitizerTest {

  @Test
  public void dropsInvalidAndDedupes() {
    assertThat(
            LlmProposalSanitizer.sanitize(
                List.of("(bvsge i (_ bv0 32))", "(= A[i] 0)", "(bvsge i (_ bv0 32))")))
        .containsExactly("(bvsge i (_ bv0 32))");
  }
}
