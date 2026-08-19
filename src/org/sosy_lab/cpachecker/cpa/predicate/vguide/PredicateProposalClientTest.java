// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.truth.Truth.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.Test;

public class PredicateProposalClientTest {

  private static final ObjectMapper JSON = new ObjectMapper();
  private static final PromptMessages PROMPT = new PromptMessages("system", "user");

  @Test
  public void metaRequestUsesSchemaAndMinimalReasoning() throws Exception {
    JsonNode request =
        JSON.readTree(
            PredicateProposalClient.buildRequestBody(
                PROMPT, "meta", "muse-spark-1.2", 1024, false, null));

    assertThat(request.path("model").asText()).isEqualTo("muse-spark-1.2");
    assertThat(request.path("reasoning_effort").asText()).isEqualTo("minimal");
    assertThat(request.has("thinking")).isFalse();
    JsonNode format = request.path("response_format");
    assertThat(format.path("type").asText()).isEqualTo("json_schema");
    JsonNode schema = format.path("json_schema").path("schema");
    assertThat(schema.path("properties").path("schema_version").path("const").asText())
        .isEqualTo("loop-head-candidate-v1");
    assertThat(schema.path("required").toString()).contains("candidates");
    JsonNode alternatives =
        schema.path("properties").path("candidates").path("items").path("anyOf");
    assertThat(alternatives.size()).isEqualTo(2);
    assertThat(alternatives.get(0).path("required").get(0).asText()).isEqualTo("loop_head");
    assertThat(alternatives.get(1).path("required").get(0).asText()).isEqualTo("loop_heads");
  }

  @Test
  public void deepSeekRequestKeepsJsonObjectAndDisabledThinking() throws Exception {
    JsonNode request =
        JSON.readTree(
            PredicateProposalClient.buildRequestBody(
                PROMPT, "deepseek", "deepseek-v4-flash", 1024, false, null));

    assertThat(request.path("response_format").path("type").asText()).isEqualTo("json_object");
    assertThat(request.path("thinking").path("type").asText()).isEqualTo("disabled");
    assertThat(request.has("reasoning_effort")).isFalse();
  }
}
