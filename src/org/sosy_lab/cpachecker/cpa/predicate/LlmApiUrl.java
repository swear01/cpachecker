// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-FileCopyrightText: 2007-2024 Dirk Beyer <https://www.sosy-lab.org>
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate;

import java.net.URI;

/** Shared validation for the LLM API endpoint (issue #64). */
public final class LlmApiUrl {

  public static final String DEFAULT_API_URL = "https://api.deepseek.com/chat/completions";

  private LlmApiUrl() {}

  /**
   * Returns the configured endpoint from {@code VGUIDE_LLM_API_URL} (default DeepSeek),
   * fail-fast on malformed values (trimmed, absolute, http/https, valid host).
   */
  public static URI validate(String configured) {
    String trimmed = configured == null ? null : configured.strip();
    if (trimmed == null || trimmed.isEmpty()) {
      return URI.create(DEFAULT_API_URL);
    }
    try {
      URI uri = URI.create(trimmed);
      if (!uri.isAbsolute()) {
        throw new IllegalArgumentException("not an absolute URI");
      }
      String scheme = uri.getScheme();
      if (scheme == null || !(scheme.equalsIgnoreCase("http") || scheme.equalsIgnoreCase("https"))) {
        throw new IllegalArgumentException("scheme must be http or https, got: " + scheme);
      }
      if (uri.getHost() == null) {
        throw new IllegalArgumentException("URI has no valid host: " + trimmed);
      }
      return uri;
    } catch (IllegalArgumentException e) {
      throw new IllegalStateException(
          "VGUIDE_LLM_API_URL is invalid: " + e.getMessage() + " (got: " + configured + ")", e);
    }
  }
}
