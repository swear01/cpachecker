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
import java.util.List;
/** Extracts predicate strings from LLM JSON output. */
public final class LlmResponseParser {

  private static final ObjectMapper JSON = new ObjectMapper();

  private LlmResponseParser() {}

  public record ParseResult(ImmutableList<String> accepted, ImmutableList<String> rejected) {}

  public static ImmutableList<String> parsePredicates(String llmOutput) {
    return parseWithRejects(llmOutput).accepted();
  }

  public static ParseResult parseWithRejects(String llmOutput) {
    if (llmOutput == null || llmOutput.isBlank()) {
      return new ParseResult(ImmutableList.of(), ImmutableList.of());
    }
    for (String candidate : jsonCandidates(llmOutput)) {
      ImmutableList<String> parsed = tryParseJson(candidate);
      if (!parsed.isEmpty()) {
        List<String> rejected = new ArrayList<>();
        for (String p : parsed) {
          if (!PredicateContractValidator.isValid(p.strip())) {
            rejected.add(p.strip());
          }
        }
        return new ParseResult(LlmProposalSanitizer.sanitize(parsed), ImmutableList.copyOf(rejected));
      }
    }
    return new ParseResult(ImmutableList.of(), ImmutableList.of());
  }

  private static ImmutableList<String> tryParseJson(String cleaned) {
    try {
      JsonNode root = JSON.readTree(cleaned);
      if (root.has("predicates") && root.get("predicates").isArray()) {
        List<String> preds = new ArrayList<>();
        for (JsonNode p : root.get("predicates")) {
          if (p.isTextual()) {
            String text = p.asText().strip();
            if (!text.isEmpty()) {
              preds.add(text);
            }
          }
        }
        return ImmutableList.copyOf(preds);
      }
      if (root.isObject() && !root.has("predicates")) {
        List<String> flat = new ArrayList<>();
        var fields = root.fields();
        while (fields.hasNext()) {
          var field = fields.next();
          if (field.getValue().isArray()) {
            for (JsonNode p : field.getValue()) {
              if (p.isTextual()) {
                String text = p.asText().strip();
                if (!text.isEmpty()) {
                  flat.add(text);
                }
              }
            }
          }
        }
        return ImmutableList.copyOf(flat);
      }
    } catch (Exception e) {
      // fall through
    }
    return ImmutableList.of();
  }

  private static List<String> jsonCandidates(String llmOutput) {
    List<String> out = new ArrayList<>();
    String trimmed = llmOutput.trim();
    if (trimmed.contains("```")) {
      trimmed = trimmed.replaceAll("(?s)```(?:json)?\\s*", " ").replace("```", " ").trim();
    }
    out.add(trimmed);
    int start = trimmed.indexOf('{');
    if (start >= 0) {
      int depth = 0;
      for (int i = start; i < trimmed.length(); i++) {
        char c = trimmed.charAt(i);
        if (c == '{') {
          depth++;
        } else if (c == '}') {
          depth--;
          if (depth == 0) {
            out.add(trimmed.substring(start, i + 1));
            break;
          }
        }
      }
    }
    return out;
  }
}
