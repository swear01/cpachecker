// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import com.fasterxml.jackson.databind.JsonNode;

/** LLM HTTP response body text plus API usage statistics. */
public record LlmProposalResult(String content, JsonNode usage, long latencyMs) {

  public boolean hasUsage() {
    return usage != null && !usage.isMissingNode();
  }
}
