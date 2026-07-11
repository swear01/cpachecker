// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.truth.Truth.assertThat;
import static org.junit.Assert.assertThrows;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.nio.file.Path;
import org.junit.Rule;
import org.junit.Test;
import org.junit.rules.TemporaryFolder;

public class LlmResponseCacheTest {

  private static final ObjectMapper JSON = new ObjectMapper();

  @Rule public TemporaryFolder temp = new TemporaryFolder();

  @Test
  public void recordsAndReplaysRepeatedPromptInOrder() throws Exception {
    Path root = temp.newFolder("cache").toPath();
    LlmResponseCache recorder = LlmResponseCache.forRecording(root, "task/a");
    String request = "{\"model\":\"m\",\"messages\":[\"same\"]}";

    LlmResponseCache.Request first = recorder.nextRequest(request);
    recorder.record(first, result("first", 17));
    LlmResponseCache.Request second = recorder.nextRequest(request);
    recorder.record(second, result("second", 23));

    LlmResponseCache replay = LlmResponseCache.forReplay(root, "task/a", false);
    LlmProposalResult replayedFirst = replay.replay(replay.nextRequest(request));
    LlmProposalResult replayedSecond = replay.replay(replay.nextRequest(request));

    assertThat(replayedFirst.content()).isEqualTo("first");
    assertThat(replayedSecond.content()).isEqualTo("second");
    assertThat(replayedFirst.latencyMs()).isEqualTo(17);
    assertThat(replayedFirst.responseSource()).isEqualTo("replay");
    assertThat(replayedFirst.requestHash()).isEqualTo(first.requestHash());
    assertThat(
            root.resolve("task_a").resolve(first.requestHash()).resolve("000001.json").toFile().exists())
        .isTrue();
  }

  @Test
  public void replayMissFailsWithoutLiveFallback() throws Exception {
    Path root = temp.newFolder("missing").toPath();
    LlmResponseCache replay = LlmResponseCache.forReplay(root, "task", false);

    IOException failure =
        assertThrows(
            IOException.class, () -> replay.replay(replay.nextRequest("missing request")));

    assertThat(failure).hasMessageThat().contains("Missing recorded LLM response");
  }

  @Test
  public void rejectsResponseStoredUnderWrongRequestHash() throws Exception {
    Path root = temp.newFolder("corrupt").toPath();
    LlmResponseCache recorder = LlmResponseCache.forRecording(root, "task");
    LlmResponseCache.Request recordedRequest = recorder.nextRequest("request");
    recorder.record(recordedRequest, result("content", 1));
    Path entry = root.resolve("task").resolve(recordedRequest.requestHash()).resolve("000001.json");
    var json = (com.fasterxml.jackson.databind.node.ObjectNode) JSON.readTree(entry.toFile());
    json.put("request_hash", "wrong");
    JSON.writerWithDefaultPrettyPrinter().writeValue(entry.toFile(), json);

    LlmResponseCache replay = LlmResponseCache.forReplay(root, "task", false);
    IOException failure =
        assertThrows(IOException.class, () -> replay.replay(replay.nextRequest("request")));

    assertThat(failure).hasMessageThat().contains("request hash mismatch");
  }

  private static LlmProposalResult result(String content, long latencyMs) {
    return new LlmProposalResult(
        content, JSON.createObjectNode().put("prompt_tokens", 4), latencyMs, 100, "", "live");
  }
}
