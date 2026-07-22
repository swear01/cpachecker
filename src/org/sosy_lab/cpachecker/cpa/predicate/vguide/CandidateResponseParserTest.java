// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-FileCopyrightText: 2026 SSU-WEI HUANG <https://github.com/swear01>
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.truth.Truth.assertThat;
import static org.junit.Assert.assertThrows;

import java.io.IOException;
import org.junit.Test;

public class CandidateResponseParserTest {

  @Test
  public void parsesStrictSchema() throws Exception {
    String response =
        """
        {"schema_version":"vguide-candidates-v1","candidates":[
          {"loop_head_id":"N12","predicate":"(assert (= |main::x| 0))"}
        ]}
        """;

    assertThat(CandidateResponseParser.parse(response, "invariant", 2))
        .containsExactly(new CandidateProposal("N12", "(assert (= |main::x| 0))", "invariant"));
  }

  @Test
  public void rejectsExtraFields() {
    String response =
        """
        {"schema_version":"vguide-candidates-v1","candidates":[
          {"loop_head_id":"N12","predicate":"true","rationale":"not allowed"}
        ]}
        """;

    assertThrows(IOException.class, () -> CandidateResponseParser.parse(response, "invariant", 2));
  }

  @Test
  public void rejectsOverBudgetResponse() {
    String response =
        """
        {"schema_version":"vguide-candidates-v1","candidates":[
          {"loop_head_id":"N1","predicate":"p"},
          {"loop_head_id":"N2","predicate":"q"}
        ]}
        """;

    assertThrows(IOException.class, () -> CandidateResponseParser.parse(response, "invariant", 1));
  }

  @Test
  public void rejectsNullAndDuplicateFields() {
    assertThrows(IOException.class, () -> CandidateResponseParser.parse("null", "invariant", 1));
    assertThrows(
        IOException.class,
        () ->
            CandidateResponseParser.parse(
                """
                {"schema_version":"vguide-candidates-v1",
                 "schema_version":"vguide-candidates-v1","candidates":[]}
                """,
                "invariant",
                1));
  }
}
