// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

/** System + user messages for one DeepSeek chat completion. */
public record PromptMessages(String system, String user) {

  public int charCount() {
    return system.length() + user.length();
  }

  /** Full text for logs and prompt dump files. */
  public String fullText() {
    return "SYSTEM:\n" + system + "\nUSER:\n" + user;
  }
}
