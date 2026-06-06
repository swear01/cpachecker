// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

/** Result of the unified VGuide orchestration for one analysis run or spurious event. */
public enum VGuideOutcome {

  /** At least one spurious CE; LLM proposal path ran or was scheduled. */
  FIRST_SPURIOUS_LLM,

  /** No spurious within budget; optional frozen predicates injected from predicate_sets/. */
  FROZEN_SEED_EXCEPTION,

  /** No spurious and no frozen file; analysis ends without LLM. */
  NO_SPURIOUS_GIVE_UP
}
