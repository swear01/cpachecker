// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.truth.Truth.assertThat;

import org.junit.Test;

public class SourceVariableHintsTest {

  @Test
  public void scalarNamesExcludeArrays() {
    String src = "int A[1024]; int i; int n;";
    assertThat(SourceVariableHints.scalarNames(src)).containsExactly("i", "n");
    assertThat(SourceVariableHints.hasArrayDecl(src)).isTrue();
  }
}
