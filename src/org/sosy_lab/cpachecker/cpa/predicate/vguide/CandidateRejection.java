// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

/** An observable rejection of one loop-head invariant candidate. */
public record CandidateRejection(
    String rawJson, String loopHead, String predicate, String reason, String detail) {}
