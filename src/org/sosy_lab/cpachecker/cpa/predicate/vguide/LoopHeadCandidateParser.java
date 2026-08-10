// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.google.common.collect.ImmutableList;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;

/**
 * Parses the versioned, location-explicit candidate contract.
 *
 * <p>Accepted candidates always carry at least one loop-head label. Anything without a resolvable
 * location is rejected with an observable reason instead of being broadcast to all loop heads.
 */
public final class LoopHeadCandidateParser {

  public static final String SCHEMA_VERSION = "loop-head-candidate-v1";

  public static final String REASON_INVALID_JSON = "invalid_json";
  public static final String REASON_WRONG_SCHEMA = "wrong_schema";
  public static final String REASON_MISSING_LOOP_HEAD = "missing_loop_head";
  public static final String REASON_CONTRACT_VIOLATION = "contract_violation";

  private static final ObjectMapper JSON = new ObjectMapper();

  private LoopHeadCandidateParser() {}

  public record ParseOutcome(
      ImmutableList<LoopHeadCandidate> accepted, ImmutableList<CandidateRejection> rejected) {}

  /** Accepted candidates only (rejections are dropped). */
  public static ImmutableList<LoopHeadCandidate> parse(String response) {
    return parseWithRejects(response).accepted();
  }

  public static ParseOutcome parseWithRejects(String response) {
    if (response == null || response.isBlank()) {
      return new ParseOutcome(ImmutableList.of(), ImmutableList.of());
    }
    JsonNode root;
    try {
      root = JSON.readTree(extractJson(response));
    } catch (Exception e) {
      return new ParseOutcome(
          ImmutableList.of(),
          ImmutableList.of(
              new CandidateRejection(
                  response.strip(), "", "", REASON_INVALID_JSON, "response is not valid JSON")));
    }
    String schema = root.path("schema_version").asText();
    if (!SCHEMA_VERSION.equals(schema)) {
      JsonNode legacy = root.path("predicates");
      if (legacy.isArray()) {
        List<CandidateRejection> rejects = new ArrayList<>();
        for (JsonNode p : legacy) {
          if (p.isTextual() && !p.asText().isBlank()) {
            rejects.add(
                new CandidateRejection(
                    p.asText(),
                    "",
                    p.asText().strip(),
                    REASON_MISSING_LOOP_HEAD,
                    "legacy predicates array has no loop-head location"));
          }
        }
        return new ParseOutcome(ImmutableList.of(), ImmutableList.copyOf(rejects));
      }
      return new ParseOutcome(
          ImmutableList.of(),
          ImmutableList.of(
              new CandidateRejection(
                  response.strip(),
                  "",
                  "",
                  REASON_WRONG_SCHEMA,
                  "expected schema_version " + SCHEMA_VERSION)));
    }
    JsonNode candidates = root.path("candidates");
    if (!candidates.isArray()) {
      return new ParseOutcome(
          ImmutableList.of(),
          ImmutableList.of(
              new CandidateRejection(
                  response.strip(), "", "", REASON_WRONG_SCHEMA, "missing candidates array")));
    }
    List<LoopHeadCandidate> accepted = new ArrayList<>();
    List<CandidateRejection> rejects = new ArrayList<>();
    for (JsonNode candidate : candidates) {
      if (candidate == null || !candidate.isObject()) {
        rejects.add(
            new CandidateRejection(
                candidate == null ? "" : candidate.toString(),
                "",
                "",
                REASON_INVALID_JSON,
                "candidate is not an object"));
        continue;
      }
      String predicate = candidate.path("predicate").asText().strip();
      LinkedHashSet<String> heads = new LinkedHashSet<>();
      JsonNode single = candidate.path("loop_head");
      if (single.isTextual() && !single.asText().isBlank()) {
        heads.add(single.asText().strip());
      }
      JsonNode multi = candidate.path("loop_heads");
      if (multi.isArray()) {
        for (JsonNode h : multi) {
          if (h.isTextual() && !h.asText().isBlank()) {
            heads.add(h.asText().strip());
          }
        }
      }
      if (heads.isEmpty()) {
        rejects.add(
            new CandidateRejection(
                candidate.toString(),
                "",
                predicate,
                REASON_MISSING_LOOP_HEAD,
                "candidate has no loop_head/loop_heads"));
        continue;
      }
      if (predicate.isEmpty()) {
        rejects.add(
            new CandidateRejection(
                candidate.toString(),
                heads.iterator().next(),
                "",
                REASON_CONTRACT_VIOLATION,
                "empty predicate"));
        continue;
      }
      if (!PredicateContractValidator.isValid(predicate)) {
        rejects.add(
            new CandidateRejection(
                candidate.toString(),
                heads.iterator().next(),
                predicate,
                REASON_CONTRACT_VIOLATION,
                "L1 contract violation"));
        continue;
      }
      String role = candidate.path("role").asText().strip();
      List<String> variables = new ArrayList<>();
      JsonNode vars = candidate.path("variables");
      if (vars.isArray()) {
        for (JsonNode v : vars) {
          if (v.isTextual() && !v.asText().isBlank()) {
            variables.add(v.asText().strip());
          }
        }
      }
      accepted.add(
          new LoopHeadCandidate(
              ImmutableList.copyOf(heads), predicate, role, ImmutableList.copyOf(variables)));
    }
    return new ParseOutcome(ImmutableList.copyOf(accepted), ImmutableList.copyOf(rejects));
  }

  /**
   * Locates the first balanced JSON object in a possibly noisy response (markdown fences,
   * conversational prose around the JSON). Returns the whole response when no object is found.
   */
  private static String extractJson(String response) {
    String trimmed = response.strip();
    int start = trimmed.indexOf('{');
    if (start < 0) {
      return trimmed;
    }
    int depth = 0;
    for (int i = start; i < trimmed.length(); i++) {
      char c = trimmed.charAt(i);
      if (c == '{') {
        depth++;
      } else if (c == '}') {
        depth--;
        if (depth == 0) {
          return trimmed.substring(start, i + 1);
        }
      }
    }
    return trimmed.substring(start);
  }
}
