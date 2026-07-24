// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-FileCopyrightText: 2026 SSU-WEI HUANG <https://github.com/swear01>
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import java.net.URI;
import java.net.URISyntaxException;
import java.nio.file.Path;
import java.time.Duration;
import org.sosy_lab.common.configuration.Configuration;
import org.sosy_lab.common.configuration.FileOption;
import org.sosy_lab.common.configuration.IntegerOption;
import org.sosy_lab.common.configuration.InvalidConfigurationException;
import org.sosy_lab.common.configuration.Option;
import org.sosy_lab.common.configuration.Options;

/** Minimal configuration for the clean VGuide boundary. */
@Options(prefix = "vguide")
final class VGuideOptions {

  enum Provider {
    OPENAI_COMPATIBLE,
    EMPTY
  }

  @Option(secure = true, description = "Enable verifier-guided predicate augmentation")
  private boolean enable = false;

  @Option(secure = true, description = "Candidate-provider implementation")
  private Provider provider = Provider.OPENAI_COMPATIBLE;

  @Option(secure = true, description = "OpenAI-compatible chat-completions endpoint")
  private String endpoint = "";

  @Option(secure = true, description = "Exact provider model identifier, including Leanstral")
  private String model = "";

  @Option(secure = true, description = "Environment variable containing the provider API key")
  private String apiKeyEnvironmentVariable = "";

  @Option(secure = true, description = "Provider timeout in seconds")
  @IntegerOption(min = 1)
  private int timeoutSeconds = 120;

  @Option(secure = true, description = "Maximum candidates accepted from each agent")
  @IntegerOption(min = 1)
  private int maxCandidatesPerAgent = 8;

  @Option(secure = true, description = "Number of previous counterexamples retained in context")
  @IntegerOption(min = 0, max = 8)
  private int counterexampleHistory = 3;

  @Option(secure = true, description = "Machine-readable candidate provenance")
  @FileOption(FileOption.Type.OUTPUT_FILE)
  private Path telemetryFile = Path.of("vguide-telemetry.json");

  VGuideOptions(Configuration config) throws InvalidConfigurationException {
    config.inject(this);
    if (enable
        && provider == Provider.OPENAI_COMPATIBLE
        && (endpoint.isBlank() || model.isBlank())) {
      throw new InvalidConfigurationException(
          "vguide.endpoint and vguide.model are required when VGuide is enabled");
    }
  }

  boolean enabled() {
    return enable;
  }

  Provider provider() {
    return provider;
  }

  URI endpoint() throws InvalidConfigurationException {
    try {
      URI parsed = new URI(endpoint);
      if (!("http".equals(parsed.getScheme()) || "https".equals(parsed.getScheme()))
          || parsed.getHost() == null
          || parsed.getUserInfo() != null
          || parsed.getFragment() != null) {
        throw new InvalidConfigurationException(
            "vguide.endpoint must be an absolute HTTP(S) URI without credentials or fragment");
      }
      return parsed;
    } catch (URISyntaxException e) {
      throw new InvalidConfigurationException("Invalid vguide.endpoint", e);
    }
  }

  String model() {
    return model;
  }

  String apiKey() throws InvalidConfigurationException {
    if (apiKeyEnvironmentVariable.isBlank()) {
      return "";
    }
    String value = System.getenv(apiKeyEnvironmentVariable);
    if (value == null || value.isBlank()) {
      throw new InvalidConfigurationException(
          "Required API-key environment variable is missing: " + apiKeyEnvironmentVariable);
    }
    return value;
  }

  Duration timeout() {
    return Duration.ofSeconds(timeoutSeconds);
  }

  int maxCandidatesPerAgent() {
    return maxCandidatesPerAgent;
  }

  int counterexampleHistory() {
    return counterexampleHistory;
  }

  Path telemetryFile() {
    return telemetryFile;
  }
}
