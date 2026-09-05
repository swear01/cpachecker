// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.truth.Truth.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.google.common.collect.ImmutableList;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import org.junit.Rule;
import org.junit.Test;
import org.junit.rules.TemporaryFolder;
import org.sosy_lab.cpachecker.cfa.CFA;
import org.sosy_lab.cpachecker.util.predicates.smt.FormulaManagerView;

public class ContextPackBudgetTest {
  @Rule public final TemporaryFolder tmp = new TemporaryFolder();

  @Test
  public void cumulativeBudgetIncludesHeadersAndFallbacks() throws Exception {
    List<Path> files = new ArrayList<>();
    for (int i = 0; i < 5; i++) {
      Path file = tmp.newFile("part" + i + ".c").toPath();
      Files.writeString(file, "// padding\n".repeat(9085) + "__VERIFIER_assert(x" + i + " > 0);\n");
      files.add(file);
    }
    CFA cfa = mock(CFA.class);
    when(cfa.getFileNames()).thenReturn(files);
    when(cfa.getLoopStructure()).thenReturn(Optional.empty());
    ContextPack pack =
        new ContextPackBuilder(
                cfa, new LoopHeadIndex(Optional.empty()), mock(FormulaManagerView.class))
            .buildSourceOnly();
    assertThat(pack.sourceCode().length()).isAtMost(300000);
    assertThat(pack.sourceCode()).contains("omitted");
    for (int i = 0; i < 5; i++) {
      assertThat(pack.sourceCode()).contains("__VERIFIER_assert(x" + i + " > 0)");
    }
  }

  @Test
  public void extractsCallInsteadOfHelperAndBalancesParentheses() {
    String source =
        "/* __VERIFIER_assert(fake) */\nvoid __VERIFIER_assert(int cond) {\n"
            + "  if (!cond) reach_error();\n}\nint main() {\n"
            + "  __VERIFIER_assert(\n    (x + 1) > a[i]);\n}\n";
    assertThat(ContextPackBuilder.extractAssertion(source)).isEqualTo("(x + 1) > a[i]");
    assertThat(ContextPackBuilder.extractAssertion("__VERIFIER_assert(x /* ) */ == 1);\n"))
        .isEqualTo("x /* ) */ == 1");
    String continuedString = "const char *s = \"a" + '\\' + "\nb\";\n__VERIFIER_assert(x > 0);\n";
    assertThat(ContextPackBuilder.extractAssertion(continuedString)).isEqualTo("x > 0");
  }

  @Test
  public void readFailureDoesNotDiscardOtherFiles() throws Exception {
    Path first = tmp.newFile("first.c").toPath();
    Path last = tmp.newFile("last.c").toPath();
    Files.writeString(first, "__VERIFIER_assert(first > 0);\n");
    Files.writeString(last, "__VERIFIER_assert(last > 0);\n");
    CFA cfa = mock(CFA.class);
    when(cfa.getFileNames())
        .thenReturn(ImmutableList.of(first, first.resolveSibling("missing.c"), last));
    ContextPack pack =
        new ContextPackBuilder(
                cfa, new LoopHeadIndex(Optional.empty()), mock(FormulaManagerView.class))
            .buildSourceOnly();
    assertThat(pack.sourceCode()).contains("__VERIFIER_assert(first > 0)");
    assertThat(pack.sourceCode()).contains("// source unavailable: read failed");
    assertThat(pack.sourceCode()).contains("__VERIFIER_assert(last > 0)");
  }

  @Test
  public void boundedLongFunctionLineIsNotAnArrayInitializer() {
    String line = "int main() { " + "x++; ".repeat(100) + " reach_error(); }\n";
    String sliced = SourceSlicer.slice(line, ImmutableList.of(new int[] {1, 1}), 0);
    assertThat(sliced).contains("// truncated");
    assertThat(sliced).doesNotContain("values elided");
    String branch = "if (x == y) { " + "x++; ".repeat(100) + " reach_error(); }\n";
    assertThat(SourceSlicer.slice(branch, ImmutableList.of(new int[] {1, 1}), 0))
        .doesNotContain("values elided");
  }

  @Test
  public void oversizedAssertionRangesStillUseTheExistingHeadLimit() throws Exception {
    Path file = tmp.newFile("many_assertions.c").toPath();
    Files.writeString(file, "__VERIFIER_assert(x > 0);\n".repeat(20000));
    CFA cfa = mock(CFA.class);
    when(cfa.getFileNames()).thenReturn(ImmutableList.of(file));
    when(cfa.getLoopStructure()).thenReturn(Optional.empty());
    ContextPack pack =
        new ContextPackBuilder(
                cfa, new LoopHeadIndex(Optional.empty()), mock(FormulaManagerView.class))
            .buildSourceOnly();
    assertThat(pack.sourceCode().length()).isAtMost(SourceSlicer.HEAD_LIMIT + 64);
    assertThat(pack.sourceCode()).contains("source omitted: file budget exhausted");
  }

  @Test
  public void reachErrorAbsenceFromSummaryDoesNotMeanAbsenceFromSource() {
    String source = "void reach_error(void);\nint main() {\n  if (x != 10) reach_error();\n}\n";
    assertThat(ContextPackBuilder.extractAssertion(source)).isEmpty();
    assertThat(SourceSlicer.slice(source, SourceSlicer.assertionRanges(source), 2))
        .contains("if (x != 10) reach_error();");
  }
}
