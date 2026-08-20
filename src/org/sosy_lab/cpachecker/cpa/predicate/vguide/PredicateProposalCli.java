// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;
import org.sosy_lab.common.annotations.SuppressForbidden;
import org.sosy_lab.common.log.LogManager;

/** Standalone command-line entry point for the production VGuide LLM client. */
@SuppressForbidden("System.out is the machine-readable CLI result stream")
public final class PredicateProposalCli {

  private static final ObjectMapper JSON = new ObjectMapper();

  private PredicateProposalCli() {}

  public static void main(String[] args) throws Exception {
    PromptMessages messages = loadMessages(args);
    var client = new PredicateProposalClient(LogManager.createNullLogManager());
    System.out.println(formatResult(client.proposeWithUsage(messages)));
  }

  static PromptMessages loadMessages(String[] args) throws IOException {
    if (args.length != 4) {
      throw new IllegalArgumentException(
          "Usage: PredicateProposalCli --system-file PATH --user-file PATH");
    }
    Map<String, Path> files = new HashMap<>();
    for (int i = 0; i < args.length; i += 2) {
      String option = args[i];
      if (!option.equals("--system-file") && !option.equals("--user-file")) {
        throw new IllegalArgumentException("Unknown option: " + option);
      }
      if (files.put(option, Path.of(args[i + 1])) != null) {
        throw new IllegalArgumentException("Duplicate option: " + option);
      }
    }
    Path systemFile = requireFile(files, "--system-file");
    Path userFile = requireFile(files, "--user-file");
    return new PromptMessages(
        Files.readString(systemFile, StandardCharsets.UTF_8),
        Files.readString(userFile, StandardCharsets.UTF_8));
  }

  private static Path requireFile(Map<String, Path> files, String option) {
    Path file = files.get(option);
    if (file == null) {
      throw new IllegalArgumentException("Missing required option: " + option);
    }
    return file;
  }

  static String formatResult(LlmProposalResult result) throws IOException {
    var output = JSON.createObjectNode();
    output.put("content", result.content());
    output.put("reasoning_content", result.reasoningContent());
    output.set("usage", result.hasUsage() ? result.usage() : JSON.nullNode());
    output.put("latency_ms", result.latencyMs());
    output.put("start_epoch_ms", result.startEpochMs());
    output.put("request_hash", result.requestHash());
    output.put("response_source", result.responseSource());
    return JSON.writeValueAsString(output);
  }
}
