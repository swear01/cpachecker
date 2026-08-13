// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.truth.Truth.assertThat;

import com.google.common.collect.ImmutableList;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.Test;
import org.sosy_lab.common.ShutdownNotifier;
import org.sosy_lab.common.log.LogManager;
import org.sosy_lab.cpachecker.cfa.CFA;
import org.sosy_lab.cpachecker.cfa.CFACreator;
import org.sosy_lab.cpachecker.util.predicates.smt.SolverViewBasedTest0;
import org.sosy_lab.cpachecker.util.test.TestDataTools;

/**
 * End-to-end check for issue #74: a source above {@link SourceSlicer#SLICE_THRESHOLD} is sliced
 * down to the loop head and the assertion before it enters the LLM prompt.
 */
public class ContextPackSourceSlicingTest extends SolverViewBasedTest0 {

  @Test
  public void largeSourceSlicedToLoopHeadAndAssertion() throws Exception {
    Path cFile = Files.createTempFile("vguide_slice_", ".c");
    cFile.toFile().deleteOnExit();
    String source = generateLargeSource();
    assertThat(source.length()).isGreaterThan(SourceSlicer.SLICE_THRESHOLD);
    Files.writeString(cFile, source);

    CFACreator parser =
        new CFACreator(
            TestDataTools.configurationForTest().build(),
            LogManager.createTestLogManager(),
            ShutdownNotifier.createDummy());
    CFA cfa = parser.parseFileAndCreateCFA(ImmutableList.of(cFile.toString()));

    LoopHeadIndex loopHeadIndex = new LoopHeadIndex(cfa.getLoopStructure());
    ContextPackBuilder builder = new ContextPackBuilder(cfa, loopHeadIndex, mgrv);
    ContextPack pack = builder.buildSourceOnly();

    assertThat(pack.sourceCode()).contains("// source truncated");
    assertThat(pack.sourceCode()).contains("__VERIFIER_assert");
    assertThat(pack.sourceCode()).contains("while (i < N)");
    // the huge constant array lines are dropped from the prompt
    assertThat(pack.sourceCode()).doesNotContain("314159");
    assertThat(pack.sourceCode().length()).isLessThan(SourceSlicer.SLICE_THRESHOLD);
    // assertion text still extracted from the sliced source
    assertThat(pack.assertion()).contains("sum");
  }

  /** Mirrors the neural-net family: one loop over a huge constant array. */
  private static String generateLargeSource() {
    StringBuilder sb = new StringBuilder();
    sb.append("int N = 16000;\n");
    sb.append("const int weights[16000] = {\n");
    for (int i = 0; i < 16000; i++) {
      sb.append("314159");
      if (i + 1 < 16000) {
        sb.append(", ");
      }
      if (i % 20 == 19) {
        sb.append('\n');
      }
    }
    sb.append("};\n");
    sb.append("int main() {\n");
    sb.append("  int sum = 0;\n");
    sb.append("  int i = 0;\n");
    sb.append("  while (i < N) {\n");
    sb.append("    sum += weights[i];\n");
    sb.append("    i++;\n");
    sb.append("  }\n");
    sb.append("  __VERIFIER_assert(sum != 0);\n");
    sb.append("  return 0;\n");
    sb.append("}\n");
    return sb.toString();
  }
}
