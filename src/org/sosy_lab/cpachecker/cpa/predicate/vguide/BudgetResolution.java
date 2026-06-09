// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

/** Result of adaptive predicate budget selection for one LLM call. */
public record BudgetResolution(PredicateBudget budget, String tier, int complexityScore) {}
