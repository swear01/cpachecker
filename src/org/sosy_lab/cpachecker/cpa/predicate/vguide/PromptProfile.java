// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

/** LLM prompt profile for predicate proposals (SAFE vs bug-hunt). */
public enum PromptProfile {
  SAFE,
  BUG_HUNT;

  public String callKindPrefix() {
    return this == BUG_HUNT ? "bug" : "safe";
  }

  public String promptKindSuffix() {
    return this == BUG_HUNT ? "bug" : "safe";
  }
}
