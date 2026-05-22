// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-FileCopyrightText: 2007-2020 Dirk Beyer <https://www.sosy-lab.org>
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate;

import static com.google.common.truth.Truth.assertThat;

import java.util.Map;
import org.junit.Test;

public class LLMConnectorTest {

  @Test
  public void parsePredicates_newFormat_parsesLocationKeyedJson() {
    String llmOutput =
        """
        {
          "loop at line 12": ["i >= 0", "i < n", "sum == i * (i + 1) / 2"],
          "function foo entry": ["x != NULL", "len > 0"]
        }""";

    Map<String, java.util.List<String>> result =
        LLMConnector.parseLocationPredicates(llmOutput);

    assertThat(result).hasSize(2);
    assertThat(result.get("loop at line 12"))
        .containsExactly("i >= 0", "i < n", "sum == i * (i + 1) / 2");
    assertThat(result.get("function foo entry")).containsExactly("x != NULL", "len > 0");
  }

  @Test
  public void parsePredicates_emptyJson_returnsEmptyMap() {
    assertThat(LLMConnector.parseLocationPredicates("{}")).isEmpty();
  }

  @Test
  public void parsePredicates_jsonWithEmptyArrays_skipsEmpty() {
    String llmOutput = """
        {
          "loop L1": [],
          "function foo": ["x > 0"]
        }""";

    Map<String, java.util.List<String>> result =
        LLMConnector.parseLocationPredicates(llmOutput);

    assertThat(result).hasSize(1);
    assertThat(result.get("function foo")).containsExactly("x > 0");
  }

  @Test
  public void parsePredicates_markdownCodeFences_stripped() {
    String llmOutput = """
        ```json
        {
          "loop at line 5": ["i >= 0"]
        }
        ```""";

    Map<String, java.util.List<String>> result =
        LLMConnector.parseLocationPredicates(llmOutput);

    assertThat(result).hasSize(1);
    assertThat(result.get("loop at line 5")).containsExactly("i >= 0");
  }

  @Test
  public void parsePredicates_invalidJson_returnsEmpty() {
    assertThat(LLMConnector.parseLocationPredicates("not json at all")).isEmpty();
    assertThat(LLMConnector.parseLocationPredicates("")).isEmpty();
  }

  @Test
  public void parsePredicates_nullSafe_returnsEmpty() {
    assertThat(LLMConnector.parseLocationPredicates(null)).isEmpty();
  }
}
