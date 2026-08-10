// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.truth.Truth.assertThat;

import com.google.common.collect.ImmutableList;
import org.junit.Test;

public class LoopHeadCandidateParserTest {

  @Test
  public void acceptsSingleLoopHeadCandidateWithRoleAndVariables() {
    var outcome =
        LoopHeadCandidateParser.parseWithRejects(
            """
            {"schema_version":"loop-head-candidate-v1","candidates":[
              {"loop_head":"N12","predicate":"(bvslt i n)","role":"relational","variables":["i","n"]}
            ]}
            """);

    assertThat(outcome.accepted())
        .containsExactly(
            new LoopHeadCandidate(
                ImmutableList.of("N12"), "(bvslt i n)", "relational", ImmutableList.of("i", "n")));
    assertThat(outcome.rejected()).isEmpty();
  }

  @Test
  public void acceptsExplicitMultiHeadCandidate() {
    var outcome =
        LoopHeadCandidateParser.parseWithRejects(
            """
            {"schema_version":"loop-head-candidate-v1","candidates":[
              {"loop_heads":["N12","N15"],"predicate":"(= i k)","role":"bound"}
            ]}
            """);

    assertThat(outcome.accepted())
        .containsExactly(
            new LoopHeadCandidate(ImmutableList.of("N12", "N15"), "(= i k)", "bound", ImmutableList.of()));
  }

  @Test
  public void mergesSingleAndMultiHeadKeysInOneCandidate() {
    var outcome =
        LoopHeadCandidateParser.parseWithRejects(
            """
            {"schema_version":"loop-head-candidate-v1","candidates":[
              {"loop_head":"N12","loop_heads":["N15"],"predicate":"(= i k)"}
            ]}
            """);

    assertThat(outcome.accepted())
        .containsExactly(
            new LoopHeadCandidate(ImmutableList.of("N12", "N15"), "(= i k)", "", ImmutableList.of()));
  }

  @Test
  public void rejectsLegacyPredicatesArrayWithMissingLoopHead() {
    var outcome = LoopHeadCandidateParser.parseWithRejects("{\"predicates\":[\"(bvslt i n)\"]}");

    assertThat(outcome.accepted()).isEmpty();
    assertThat(outcome.rejected())
        .containsExactly(
            new CandidateRejection(
                "(bvslt i n)",
                "",
                "(bvslt i n)",
                LoopHeadCandidateParser.REASON_MISSING_LOOP_HEAD,
                "legacy predicates array has no loop-head location"));
  }

  @Test
  public void rejectsCandidateWithoutLoopHead() {
    var outcome =
        LoopHeadCandidateParser.parseWithRejects(
            """
            {"schema_version":"loop-head-candidate-v1","candidates":[
              {"predicate":"(bvslt i n)"}
            ]}
            """);

    assertThat(outcome.accepted()).isEmpty();
    assertThat(outcome.rejected()).hasSize(1);
    assertThat(outcome.rejected().get(0).reason())
        .isEqualTo(LoopHeadCandidateParser.REASON_MISSING_LOOP_HEAD);
  }

  @Test
  public void rejectsL1ContractViolations() {
    var outcome =
        LoopHeadCandidateParser.parseWithRejects(
            """
            {"schema_version":"loop-head-candidate-v1","candidates":[
              {"loop_head":"N12","predicate":"(select A i)"}
            ]}
            """);

    assertThat(outcome.accepted()).isEmpty();
    assertThat(outcome.rejected()).hasSize(1);
    assertThat(outcome.rejected().get(0).reason())
        .isEqualTo(LoopHeadCandidateParser.REASON_CONTRACT_VIOLATION);
  }

  @Test
  public void rejectsWrongSchemaVersion() {
    var outcome =
        LoopHeadCandidateParser.parseWithRejects(
            "{\"schema_version\":\"loop-head-candidate-v0\",\"candidates\":[]}");

    assertThat(outcome.accepted()).isEmpty();
    assertThat(outcome.rejected()).hasSize(1);
    assertThat(outcome.rejected().get(0).reason())
        .isEqualTo(LoopHeadCandidateParser.REASON_WRONG_SCHEMA);
  }

  @Test
  public void rejectsMalformedJson() {
    var outcome = LoopHeadCandidateParser.parseWithRejects("{not json");

    assertThat(outcome.accepted()).isEmpty();
    assertThat(outcome.rejected()).hasSize(1);
    assertThat(outcome.rejected().get(0).reason())
        .isEqualTo(LoopHeadCandidateParser.REASON_INVALID_JSON);
  }

  @Test
  public void toleratesMarkdownFences() {
    var outcome =
        LoopHeadCandidateParser.parseWithRejects(
            """
            ```json
            {"schema_version":"loop-head-candidate-v1","candidates":[
              {"loop_head":"N12","predicate":"(bvslt i n)"}
            ]}
            ```
            """);

    assertThat(outcome.accepted()).hasSize(1);
    assertThat(outcome.rejected()).isEmpty();
  }

  @Test
  public void unknownRoleAndMissingVariablesAreTolerated() {
    var outcome =
        LoopHeadCandidateParser.parseWithRejects(
            """
            {"schema_version":"loop-head-candidate-v1","candidates":[
              {"loop_head":"N12","predicate":"(bvslt i n)","role":"mystery"}
            ]}
            """);

    assertThat(outcome.accepted())
        .containsExactly(
            new LoopHeadCandidate(ImmutableList.of("N12"), "(bvslt i n)", "mystery", ImmutableList.of()));
    assertThat(outcome.rejected()).isEmpty();
  }
}
