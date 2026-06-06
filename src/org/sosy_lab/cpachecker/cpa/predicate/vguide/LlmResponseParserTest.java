// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.truth.Truth.assertThat;

import org.junit.Test;

public class LlmResponseParserTest {

  @Test
  public void parsesPredicatesArray() {
    String json = "{\"predicates\": [\"(= k i)\", \"(bvslt i n)\"]}";
    assertThat(LlmResponseParser.parsePredicates(json))
        .containsExactly("(= k i)", "(bvslt i n)")
        .inOrder();
  }

  @Test
  public void flattensLegacyLocationKeyedJson() {
    String json = "{\"N19\": [\"(= x y)\"], \"N23\": [\"(>= i 0)\"]}";
    assertThat(LlmResponseParser.parsePredicates(json))
        .containsExactly("(= x y)", "(>= i 0)");
  }

  @Test
  public void stripsMarkdownFences() {
    String raw =
        """
        ```json
        {"predicates": ["(= a b)"]}
        ```
        """;
    assertThat(LlmResponseParser.parsePredicates(raw)).containsExactly("(= a b)");
  }

  @Test
  public void nullOrInvalidReturnsEmpty() {
    assertThat(LlmResponseParser.parsePredicates(null)).isEmpty();
    assertThat(LlmResponseParser.parsePredicates("not json")).isEmpty();
  }

  @Test
  public void sanitizeDropsArraySubscriptFromJson() {
    String json = "{\"predicates\": [\"(bvsge i (_ bv0 32))\", \"(= A[i] 0)\"]}";
    assertThat(LlmResponseParser.parsePredicates(json))
        .containsExactly("(bvsge i (_ bv0 32))");
    assertThat(LlmResponseParser.parseWithRejects(json).rejected()).containsExactly("(= A[i] 0)");
  }
}
