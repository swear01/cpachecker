// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-FileCopyrightText: 2026 Dirk Beyer <https://www.sosy-lab.org>
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.util.arrayabstraction;

import static com.google.common.truth.Truth.assertThat;

import org.junit.Test;
import org.sosy_lab.common.log.LogManager;
import org.sosy_lab.cpachecker.cfa.CFA;
import org.sosy_lab.cpachecker.util.arrayabstraction.ArrayAbstractionResult.Status;
import org.sosy_lab.cpachecker.util.test.TestDataTools;

public class ArrayAbstractionUnsupportedBaseTest {

  @Test
  public void unsupportedArrayBasesPreserveOriginalCfa() throws Exception {
    for (String body :
        new String[] {
          "int a[2][2]; for (int i=0; i<2; i++) { a[i][1]=i; } return a[1][1];",
          "int a[2][2]={{0,1},{2,3}}; int b[2];"
              + " for (int i=0; i<2; i++) { b[i]=a[i][1]; } return b[1];",
          "int a[2][2][2]; for (int i=0; i<2; i++) { a[i][1][1]=i; }" + " return a[1][1][1];",
          "int a[2][2]; int b[2]; for (int i=0; i<2; i++) {"
              + " b[i]=0; for (int j=0; j<2; j++) { a[i][j]=i+j; }} return a[1][1];",
          "int a[2][2]; int (*p)[2]=a; for (int i=0; i<2; i++) { p[i][1]=i; }" + " return a[1][1];",
          "int a[2]; int *p=a; for (int i=0; i<2; i++) { a[i]=0; p[i]=1; }" + " return a[1];",
        }) {
      CFA cfa = TestDataTools.makeCFA("int main() {" + body + "}");
      ArrayAbstractionResult result = transform(cfa);
      assertThat(result.getStatus()).isEqualTo(Status.UNCHANGED);
      assertThat(result.getTransformedCfa()).isSameInstanceAs(cfa);
      assertThat(result.getTransformedArrays()).isEmpty();
      assertThat(result.getTransformedLoops()).isEmpty();
    }
  }

  @Test
  public void directArrayAccessStillTransforms() throws Exception {
    CFA cfa =
        TestDataTools.makeCFA(
            "int main() { int a[2]; for (int i=0; i<2; i++) { a[i]=0; } return 0; }");
    ArrayAbstractionResult result = transform(cfa);
    assertThat(result.getStatus()).isEqualTo(Status.PRECISE);
    assertThat(result.getTransformedArrays()).hasSize(1);
    assertThat(result.getTransformedLoops()).hasSize(1);
  }

  private static ArrayAbstractionResult transform(CFA pCfa) throws Exception {
    return ArrayAbstraction.transformCfa(
        TestDataTools.configurationForTest().build(), LogManager.createTestLogManager(), pCfa);
  }
}
