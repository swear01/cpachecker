// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.google.common.hash.Hashing;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

/** Fail-closed per-task storage for paired LLM response recording and replay. */
final class LlmResponseCache {

  private static final int SCHEMA_VERSION = 1;
  private static final ObjectMapper JSON = new ObjectMapper();

  enum Mode {
    RECORD,
    REPLAY
  }

  record Request(String requestBody, String requestHash, int ordinal, Path path) {}

  private final Path root;
  private final String namespace;
  private final Mode mode;
  private final boolean preserveLatency;
  private final ConcurrentHashMap<String, AtomicInteger> ordinals = new ConcurrentHashMap<>();

  static LlmResponseCache forRecording(Path root, String namespace) {
    return new LlmResponseCache(root, namespace, Mode.RECORD, false);
  }

  static LlmResponseCache forReplay(Path root, String namespace, boolean preserveLatency) {
    return new LlmResponseCache(root, namespace, Mode.REPLAY, preserveLatency);
  }

  private LlmResponseCache(Path pRoot, String pNamespace, Mode pMode, boolean pPreserveLatency) {
    root = pRoot;
    namespace = sanitizeNamespace(pNamespace);
    mode = pMode;
    preserveLatency = pPreserveLatency;
  }

  Mode mode() {
    return mode;
  }

  Request nextRequest(String requestBody) {
    String requestHash =
        Hashing.sha256().hashString(requestBody, StandardCharsets.UTF_8).toString();
    int ordinal = ordinals.computeIfAbsent(requestHash, unused -> new AtomicInteger()).incrementAndGet();
    Path path =
        root.resolve(namespace)
            .resolve(requestHash)
            .resolve(String.format("%06d.json", ordinal));
    return new Request(requestBody, requestHash, ordinal, path);
  }

  void record(Request request, LlmProposalResult result) throws IOException {
    if (mode != Mode.RECORD) {
      throw new IllegalStateException("LLM response cache is not in record mode");
    }
    ObjectNode row = JSON.createObjectNode();
    row.put("schema_version", SCHEMA_VERSION);
    row.put("request_hash", request.requestHash());
    row.put("ordinal", request.ordinal());
    row.put("content", result.content());
    row.put("reasoning_content", result.reasoningContent());
    if (result.usage() == null) {
      row.putNull("usage");
    } else {
      row.set("usage", result.usage());
    }
    row.put("latency_ms", result.latencyMs());
    row.put("recorded_start_epoch_ms", result.startEpochMs());

    Files.createDirectories(request.path().getParent());
    Path temporary = request.path().resolveSibling(request.path().getFileName() + ".tmp");
    JSON.writerWithDefaultPrettyPrinter().writeValue(temporary.toFile(), row);
    Files.move(
        temporary,
        request.path(),
        StandardCopyOption.ATOMIC_MOVE,
        StandardCopyOption.REPLACE_EXISTING);
  }

  LlmProposalResult replay(Request request) throws IOException, InterruptedException {
    if (mode != Mode.REPLAY) {
      throw new IllegalStateException("LLM response cache is not in replay mode");
    }
    if (!Files.isRegularFile(request.path())) {
      throw new IOException("Missing recorded LLM response: " + request.path());
    }
    JsonNode row = JSON.readTree(request.path().toFile());
    if (row.path("schema_version").asInt(-1) != SCHEMA_VERSION) {
      throw new IOException("Unsupported recorded LLM response schema: " + request.path());
    }
    if (!request.requestHash().equals(row.path("request_hash").asText())) {
      throw new IOException("Recorded LLM response request hash mismatch: " + request.path());
    }
    if (request.ordinal() != row.path("ordinal").asInt(-1)) {
      throw new IOException("Recorded LLM response ordinal mismatch: " + request.path());
    }
    JsonNode content = row.path("content");
    if (!content.isTextual()) {
      throw new IOException("Recorded LLM response has no text content: " + request.path());
    }
    long latencyMs = row.path("latency_ms").asLong(-1);
    if (latencyMs < 0) {
      throw new IOException("Recorded LLM response has invalid latency: " + request.path());
    }
    long startEpochMs = System.currentTimeMillis();
    if (preserveLatency && latencyMs > 0) {
      Thread.sleep(latencyMs);
    }
    JsonNode usage = row.path("usage");
    JsonNode reasoning = row.path("reasoning_content");
    return new LlmProposalResult(
        content.asText(),
        reasoning.isTextual() ? reasoning.asText() : "",
        usage.isNull() || usage.isMissingNode() ? null : usage,
        latencyMs,
        startEpochMs,
        request.requestHash(),
        "replay");
  }

  private static String sanitizeNamespace(String value) {
    String sanitized = value.replaceAll("[^A-Za-z0-9._-]", "_");
    return sanitized.isBlank() ? "default" : sanitized;
  }
}
