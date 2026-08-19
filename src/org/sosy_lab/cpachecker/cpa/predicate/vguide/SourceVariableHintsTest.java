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

  @Test
  public void scalarNamesSupportCommaSeparatedDeclarations() {
    String src = "int i,j,k,n,l,m;";
    assertThat(SourceVariableHints.scalarNames(src))
        .containsExactly("i", "j", "k", "n", "l", "m")
        .inOrder();
    assertThat(SourceVariableHints.scalarDeclCount(src)).isEqualTo(6);
  }

  @Test
  public void scalarNamesKeepScalarsFromMixedDeclaration() {
    String src = "int A[16], i = (j + 1), j;";
    assertThat(SourceVariableHints.scalarNames(src)).containsExactly("i", "j").inOrder();
  }

  @Test
  public void scalarNamesIgnoreFunctionDeclarations() {
    String src = "int helper(int x); int i;";
    assertThat(SourceVariableHints.scalarNames(src)).containsExactly("i");
  }

  @Test
  public void scalarNamesIgnoreCommentsLiteralsStructFieldsAndPointers() {
    String src =
        """
        // int commentOnly;
        const char *text = "int literalOnly;";
        struct{ int field; };
        int *pointer, **pointerPointer, i = foo("a,b", '('), j;
        """;

    assertThat(SourceVariableHints.scalarNames(src)).containsExactly("i", "j").inOrder();
    assertThat(SourceVariableHints.scalarDeclCount(src)).isEqualTo(2);
  }

  @Test
  public void arrayDetectionHandlesMixedDeclarationsAndIndexedInitializers() {
    String src = "int value = A[0], A[16], count;";

    assertThat(SourceVariableHints.scalarNames(src)).containsExactly("value", "count").inOrder();
    assertThat(SourceVariableHints.hasArrayDecl(src)).isTrue();
  }

  @Test
  public void arrayNamesAreNeverAllowedAsScalars() {
    String src = "int A[10]; { int A; }";

    assertThat(SourceVariableHints.scalarNames(src)).doesNotContain("A");
  }

  @Test
  public void arrayPromptUsesCanonicalSourceSyntax() {
    String hints = SourceVariableHints.formatForPrompt("int A[1024]; int i;", java.util.Map.of());
    assertThat(hints).contains("array element reads are allowed");
    assertThat(hints).contains("A[i]");
    assertThat(hints).doesNotContain("do NOT use array identifiers");
    assertThat(hints).doesNotContain("BAD (rejected)");
  }
}
