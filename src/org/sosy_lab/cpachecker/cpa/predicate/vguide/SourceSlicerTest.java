// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.truth.Truth.assertThat;

import java.util.List;
import org.junit.Test;

public class SourceSlicerTest {

  @Test
  public void sliceAppliesWhenRangesGiven() {
    String source = "int main() {\n  return 0;\n}\n";
    String sliced = SourceSlicer.slice(source, List.of(new int[] {2, 2}), 0);
    assertThat(sliced).contains("return 0;");
    assertThat(sliced).doesNotContain("int main() {");
  }

  @Test
  public void sliceKeepsOnlyMergedRanges() {
    StringBuilder sb = new StringBuilder();
    for (int i = 1; i <= 100; i++) {
      sb.append("line ").append(i).append('\n');
    }
    String source = sb.toString();
    // lines 10-12 and 20-30 (margin 2 => 8-14 and 18-32)
    String sliced =
        SourceSlicer.slice(source, List.of(new int[] {10, 12}, new int[] {20, 30}), 2);
    assertThat(sliced).contains("// [lines 8-14]");
    assertThat(sliced).contains("line 8\n");
    assertThat(sliced).contains("line 14\n");
    assertThat(sliced).contains("// [lines 18-32]");
    assertThat(sliced).contains("line 18\n");
    assertThat(sliced).contains("line 32\n");
    assertThat(sliced).doesNotContain("line 7\n");
    assertThat(sliced).doesNotContain("line 15\n");
    assertThat(sliced).doesNotContain("line 33\n");
    assertThat(sliced).contains("// source truncated");
  }

  @Test
  public void adjacentRangesMerge() {
    StringBuilder sb = new StringBuilder();
    for (int i = 1; i <= 50; i++) {
      sb.append("x ").append(i).append('\n');
    }
    String source = sb.toString();
    String sliced = SourceSlicer.slice(source, List.of(new int[] {10, 12}, new int[] {14, 16}), 1);
    assertThat(sliced).contains("// [lines 9-17]");
    assertThat(sliced).doesNotContain("// [lines 13-15]");
  }

  @Test
  public void assertionLineLocatesFirstAssert() {
    String source = "int a;\n__VERIFIER_assert(a == 0);\nint b;\n__VERIFIER_assert(b == 1);\n";
    assertThat(SourceSlicer.assertionLine(source)).isEqualTo(2);
  }

  @Test
  public void assertionLineFindsReachError() {
    String source = "void reach_error() { __assert_fail(\"0\", \"x\", 1, \"reach_error\"); }\nint main() {\n  reach_error();\n}\n";
    assertThat(SourceSlicer.assertionLine(source)).isEqualTo(3);
  }

  @Test
  public void assertionLineSkipsHelperDeclaration() {
    String source =
        """
        extern void __VERIFIER_assert(int cond);
        #define __VERIFIER_assert(cond) do { if (!(cond)) __VERIFIER_error(); } while (0)
        int main() {
          __VERIFIER_assert(x == 0);
        }
        """;
    assertThat(SourceSlicer.assertionLine(source)).isEqualTo(4);
  }

  @Test
  public void topLevelDeclarationRangesKeepGlobalsAndSkipBody() {
    String source =
        """
        #include <stdint.h>
        const int weights[2] = {1, 2};
        int main() {
          int x = 0;
          while (x < 1) { x++; }
          return 0;
        }
        """;
    List<int[]> ranges = SourceSlicer.topLevelDeclarationRanges(source);
    assertThat(
            ranges.stream().map(r -> r[0] + "-" + r[1]).collect(java.util.stream.Collectors.toList()))
        .containsExactly("1-1", "2-2", "3-3");
  }

  @Test
  public void headBoundsLargeSourceAtLineBoundary() {
    StringBuilder sb = new StringBuilder();
    for (int i = 1; i <= 100_000; i++) {
      sb.append("l").append(i).append('\n');
    }
    String source = sb.toString();
    String head = SourceSlicer.head(source);
    assertThat(head.length()).isLessThan(SourceSlicer.HEAD_LIMIT + 100);
    assertThat(head).contains("// source truncated to head");
    assertThat(head).contains("l5000"); // early content preserved
    assertThat(head).doesNotContain("l99999"); // tail cut off
  }

  @Test
  public void assertionLineWithoutAssertIsMinusOne() {
    assertThat(SourceSlicer.assertionLine("int x;\nreturn 0;\n")).isEqualTo(-1);
  }

  @Test
  public void sliceWithoutRangesReturnsSource() {
    String source = "int x;\n";
    assertThat(SourceSlicer.slice(source, List.of(), 2)).isEqualTo(source);
  }

  @Test
  public void sliceClampsToSourceBounds() {
    String source = "only one line";
    String sliced = SourceSlicer.slice(source, List.of(new int[] {1, 5}), 10);
    assertThat(sliced).contains("only one line");
  }
}
