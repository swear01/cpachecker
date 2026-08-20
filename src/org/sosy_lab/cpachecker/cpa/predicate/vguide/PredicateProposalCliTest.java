// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.truth.Truth.assertThat;
import static org.junit.Assert.assertThrows;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.Rule;
import org.junit.Test;
import org.junit.rules.TemporaryFolder;

public class PredicateProposalCliTest {

  private static final ObjectMapper JSON = new ObjectMapper();

  @Rule public TemporaryFolder temp = new TemporaryFolder();

  @Test
  public void loadMessagesReadsExactFileContents() throws Exception {
    Path systemFile = temp.newFile("system.txt").toPath();
    Path userFile = temp.newFile("user.txt").toPath();
    Files.writeString(systemFile, "system\nwith newline\n");
    Files.writeString(userFile, "user \"quoted\" text\n");

    PromptMessages messages =
        PredicateProposalCli.loadMessages(
            new String[] {
              "--system-file", systemFile.toString(), "--user-file", userFile.toString()
            });

    assertThat(messages.system()).isEqualTo("system\nwith newline\n");
    assertThat(messages.user()).isEqualTo("user \"quoted\" text\n");
  }

  @Test
  public void loadMessagesRejectsMissingUserFile() throws Exception {
    Path systemFile = temp.newFile("system.txt").toPath();

    IllegalArgumentException error =
        assertThrows(
            IllegalArgumentException.class,
            () ->
                PredicateProposalCli.loadMessages(
                    new String[] {"--system-file", systemFile.toString()}));

    assertThat(error).hasMessageThat().contains("--user-file");
  }

  @Test
  public void loadMessagesRejectsUnknownOption() throws Exception {
    Path systemFile = temp.newFile("system.txt").toPath();
    Path userFile = temp.newFile("user.txt").toPath();

    IllegalArgumentException error =
        assertThrows(
            IllegalArgumentException.class,
            () ->
                PredicateProposalCli.loadMessages(
                    new String[] {
                      "--system-file", systemFile.toString(), "--prompt-file", userFile.toString()
                    }));

    assertThat(error).hasMessageThat().contains("--prompt-file");
  }

  @Test
  public void formatResultProducesMachineReadableJson() throws Exception {
    LlmProposalResult result =
        new LlmProposalResult(
            "{\"candidates\":[]}",
            JSON.readTree("{\"prompt_tokens\":12,\"completion_tokens\":7}"),
            1234,
            5678,
            "abc123",
            "live");

    var output = JSON.readTree(PredicateProposalCli.formatResult(result));

    assertThat(output.path("content").asText()).isEqualTo("{\"candidates\":[]}");
    assertThat(output.path("usage").path("prompt_tokens").asInt()).isEqualTo(12);
    assertThat(output.path("latency_ms").asLong()).isEqualTo(1234);
    assertThat(output.path("start_epoch_ms").asLong()).isEqualTo(5678);
    assertThat(output.path("request_hash").asText()).isEqualTo("abc123");
    assertThat(output.path("response_source").asText()).isEqualTo("live");
  }

  @Test
  public void formatResultWritesNullWhenUsageIsUnavailable() throws Exception {
    LlmProposalResult result = new LlmProposalResult("{}", null, 1, 2, "hash", "replay");

    var output = JSON.readTree(PredicateProposalCli.formatResult(result));

    assertThat(output.has("usage")).isTrue();
    assertThat(output.path("usage").isNull()).isTrue();
  }
}
