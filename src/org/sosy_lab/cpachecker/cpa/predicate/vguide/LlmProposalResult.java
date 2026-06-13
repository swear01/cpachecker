// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import com.fasterxml.jackson.databind.JsonNode;

/**
 * LLM HTTP response body text plus API usage statistics.
 *
 * <p>{@code startEpochMs} is the wall-clock epoch (ms) at which the HTTP call started; together with
 * {@code latencyMs} it lets offline tooling reconstruct inter-call intervals (e.g. to validate
 * {@code vguide.llmMinIntervalSec} under the svcomp portfolio).
 */
public record LlmProposalResult(
    String content, JsonNode usage, long latencyMs, long startEpochMs) {

  public boolean hasUsage() {
    return usage != null && !usage.isMissingNode();
  }
}
