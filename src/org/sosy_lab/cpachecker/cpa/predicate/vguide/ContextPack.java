// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-FileCopyrightText: 2026 SSU-WEI HUANG <https://github.com/swear01>
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import com.google.common.collect.ImmutableList;

/** Versioned, bounded verifier context sent to predicate-candidate agents. */
public record ContextPack(
    String schemaVersion,
    int refinementIndex,
    ImmutableList<LoopHeadContext> loopHeads,
    ImmutableList<CounterexampleStep> counterexample,
    ImmutableList<ImmutableList<CounterexampleStep>> previousCounterexamples,
    ImmutableList<NativePredicateContext> nativePredicates,
    NativeRefinementOutcome nativeRefinement,
    ImmutableList<VariableContext> allowedVariables) {

  public static final String SCHEMA_VERSION = "vguide-context-v1";

  public record LoopHeadContext(String id, int nodeNumber, String function, String description) {}

  public record CounterexampleStep(
      int sourceNode, int targetNode, String edgeType, String code, String loopHeadId) {}

  public record NativePredicateContext(String scope, String location, String predicate) {}

  public record NativeRefinementOutcome(boolean spurious, int predicatesAdded) {}

  public record VariableContext(String name, String smtSort) {}
}
