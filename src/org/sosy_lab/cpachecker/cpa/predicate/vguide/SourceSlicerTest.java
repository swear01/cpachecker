// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.truth.Truth.assertThat;

import java.util.List;
import java.util.stream.Collectors;
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
  public void assertionRangesLocateAllCallSites() {
    String source = "int a;\n__VERIFIER_assert(a == 0);\nint b;\n__VERIFIER_assert(b == 1);\n";
    List<int[]> ranges = SourceSlicer.assertionRanges(source);
    assertThat(toKeys(ranges)).containsExactly("2-2", "4-4");
  }

  @Test
  public void assertionRangesSkipMultiLineHelperBody() {
    String source =
        """
        void __VERIFIER_assert(int cond) {
          if (!(cond)) { ERROR: {reach_error();abort();} }
        }
        int main() {
          __VERIFIER_assert(x == 0);
        }
        """;
    List<int[]> ranges = SourceSlicer.assertionRanges(source);
    assertThat(toKeys(ranges)).containsExactly("5-5");
  }

  @Test
  public void assertionRangesCoverMultiLineCall() {
    String source =
        """
        int main() {
          __VERIFIER_assert(
              a == 0 &&
              b == 1);
        }
        """;
    List<int[]> ranges = SourceSlicer.assertionRanges(source);
    assertThat(toKeys(ranges)).containsExactly("2-4");
  }

  @Test
  public void assertionRangesIgnoreCommentsMentioningAssert() {
    String source =
        """
        // __VERIFIER_assert is defined below
        /* reach_error(); is used by the helper */
        int main() {
          __VERIFIER_assert(x == 0);
        }
        """;
    List<int[]> ranges = SourceSlicer.assertionRanges(source);
    assertThat(toKeys(ranges)).containsExactly("4-4");
  }

  @Test
  public void assertionRangesWithoutAssertIsEmpty() {
    assertThat(SourceSlicer.assertionRanges("int x;\nreturn 0;\n")).isEmpty();
  }

  @Test
  public void assertionRangesTolerateWhitespaceBeforeParen() {
    String source = "int main() {\n  __VERIFIER_assert (x == 0);\n  reach_error ();\n}\n";
    List<int[]> ranges = SourceSlicer.assertionRanges(source);
    assertThat(toKeys(ranges)).containsExactly("2-2", "3-3");
  }

  @Test
  public void assertionRangesExternPrototypeDoesNotStartHelperMode() {
    String source =
        """
        extern void __VERIFIER_assert(int cond);
        int main() {
          __VERIFIER_assert(x == 0);
        }
        """;
    List<int[]> ranges = SourceSlicer.assertionRanges(source);
    assertThat(toKeys(ranges)).containsExactly("3-3");
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
    assertThat(toKeys(ranges)).containsExactly("1-1", "2-2", "3-3");
  }

  @Test
  public void topLevelRangesResetDepthAtEndif() {
    String source =
        """
        #if 0
        int fragment() {
        #endif
        int g = 0;
        int main() {
          return 0;
        }
        """;
    List<int[]> ranges = SourceSlicer.topLevelDeclarationRanges(source);
    assertThat(toKeys(ranges)).containsExactly("1-1", "2-2", "3-3", "4-4", "5-5");
  }

  @Test
  public void sliceElidesOneLineInitializerValues() {
    StringBuilder sb = new StringBuilder();
    sb.append("const int w[100] = {");
    for (int i = 0; i < 100; i++) {
      sb.append("111111,");
    }
    sb.append("};\nint main() { return 0; }\n");
    String source = sb.toString();
    String sliced = SourceSlicer.slice(source, List.of(new int[] {1, 2}), 0);
    assertThat(sliced).doesNotContain("111111");
    assertThat(sliced).contains("/* values elided */");
    assertThat(sliced).contains("const int w[100]");
  }

  @Test
  public void topLevelRangesIgnoreStringAndMacroBraces() {
    String source =
        """
        const char *s = "{";
        #define M(x) ({ int t = (x); t; })
        int g = 0;
        int main() {
          return 0;
        }
        """;
    List<int[]> ranges = SourceSlicer.topLevelDeclarationRanges(source);
    assertThat(toKeys(ranges)).containsExactly("1-1", "2-2", "3-3", "4-4");
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

  @Test
  public void sliceTrailingNewlineDoesNotAddPhantomLine() {
    String source = "a\nb\n";
    String sliced = SourceSlicer.slice(source, List.of(new int[] {1, 2}), 0);
    assertThat(sliced).contains("2 lines)");
    assertThat(sliced.trim()).endsWith("b");
  }

  private static List<String> toKeys(List<int[]> ranges) {
    return ranges.stream().map(r -> r[0] + "-" + r[1]).collect(Collectors.toList());
  }
}
