// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

/** One raw predicate string and the prompt profile that produced it. */
public record AttributedRawPredicate(String raw, PromptProfile profile) {}
