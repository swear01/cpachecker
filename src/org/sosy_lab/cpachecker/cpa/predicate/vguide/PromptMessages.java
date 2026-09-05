// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.base.Preconditions.checkArgument;

import com.google.common.collect.ImmutableMap;

/** System + user messages for one LLM chat completion. */
public record PromptMessages(
    String system, String user, ImmutableMap<String, String> userComponents) {

  public PromptMessages {
    checkArgument(
        user.equals(String.join("", userComponents.values())),
        "Prompt components must reproduce the exact user message");
  }

  public PromptMessages(String system, String user) {
    this(system, user, ImmutableMap.of("user", user));
  }

  PromptMessages(String system, ImmutableMap<String, String> userComponents) {
    this(system, String.join("", userComponents.values()), userComponents);
  }

  public int charCount() {
    return system.length() + user.length();
  }

  /** Full text for logs and prompt dump files. */
  public String fullText() {
    return "SYSTEM:\n" + system + "\nUSER:\n" + user;
  }
}
