// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.truth.Truth.assertThat;

import java.nio.file.Path;
import org.junit.Test;
import org.junit.rules.TemporaryFolder;
import org.sosy_lab.common.log.LogManager;

public class FrozenPredicateLoaderTest {

  @org.junit.Rule public TemporaryFolder temp = new TemporaryFolder();

  @Test
  public void loadsJsonPredicates() throws Exception {
    Path dir = temp.newFolder("predicate_sets").toPath();
    java.nio.file.Files.writeString(
        dir.resolve("bench.json"),
        "{\"predicates\": [\"(= k i)\", \"(bvslt i n)\"]}");
    var loader = new FrozenPredicateLoader(LogManager.createTestLogManager(), dir.toString());
    assertThat(loader.loadForBenchmark("bench").orElseThrow())
        .containsExactly("(= k i)", "(bvslt i n)");
  }

  @Test
  public void loadsMarkdownBootstrapSection() throws Exception {
    Path dir = temp.newFolder("predicate_sets").toPath();
    java.nio.file.Files.writeString(
        dir.resolve("up.md"),
        """
        ## Bootstrap Predicates
        - `(= k i)`
        - `(bvslt i n)`
        ## Count
        2
        """);
    var loader = new FrozenPredicateLoader(LogManager.createTestLogManager(), dir.toString());
    assertThat(loader.loadForBenchmark("up").orElseThrow())
        .containsExactly("(= k i)", "(bvslt i n)");
  }

  @Test
  public void missingBenchmarkReturnsEmpty() {
    var loader =
        new FrozenPredicateLoader(
            LogManager.createTestLogManager(), temp.getRoot().getAbsolutePath());
    assertThat(loader.loadForBenchmark("missing")).isEmpty();
  }
}
