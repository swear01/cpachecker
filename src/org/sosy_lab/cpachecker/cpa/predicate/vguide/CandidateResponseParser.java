// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-FileCopyrightText: 2026 SSU-WEI HUANG <https://github.com/swear01>
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import com.fasterxml.jackson.core.StreamReadFeature;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.google.common.collect.ImmutableList;
import java.io.IOException;

/** Strict parser for the only accepted model-response schema. */
public final class CandidateResponseParser {

  static final String SCHEMA_VERSION = "vguide-candidates-v1";
  private static final ObjectMapper JSON =
      JsonMapper.builder().enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION).build();

  private CandidateResponseParser() {}

  public static ImmutableList<CandidateProposal> parse(
      String response, String agentRole, int maxCandidates) throws IOException {
    JsonNode root = JSON.readTree(response);
    if (root == null
        || !root.isObject()
        || root.size() != 2
        || !SCHEMA_VERSION.equals(root.path("schema_version").textValue())
        || !root.path("candidates").isArray()) {
      throw new IOException("Response does not match vguide-candidates-v1");
    }
    JsonNode candidates = root.path("candidates");
    if (candidates.size() > maxCandidates) {
      throw new IOException("Response exceeds the candidate limit of " + maxCandidates);
    }
    ImmutableList.Builder<CandidateProposal> parsed = ImmutableList.builder();
    for (JsonNode candidate : candidates) {
      if (!candidate.isObject()
          || candidate.size() != 2
          || !candidate.path("loop_head_id").isTextual()
          || !candidate.path("predicate").isTextual()) {
        throw new IOException("Candidate does not match the strict schema");
      }
      String loopHeadId = candidate.path("loop_head_id").textValue().strip();
      String predicate = candidate.path("predicate").textValue().strip();
      if (loopHeadId.isEmpty()
          || loopHeadId.length() > 64
          || predicate.isEmpty()
          || predicate.length() > 4096) {
        throw new IOException("Candidate contains an invalid field");
      }
      parsed.add(new CandidateProposal(loopHeadId, predicate, agentRole));
    }
    return parsed.build();
  }
}
