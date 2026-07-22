// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-FileCopyrightText: 2026 SSU-WEI HUANG <https://github.com/swear01>
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Duration;
import java.util.HexFormat;

/** Explicit OpenAI-compatible adapter usable with remote models or a local Leanstral server. */
final class OpenAiCompatibleCandidateProvider implements CandidateProvider {

  private static final ObjectMapper JSON = new ObjectMapper();
  private static final int MAX_RESPONSE_BYTES = 1_048_576;

  private final URI endpoint;
  private final String model;
  private final String apiKey;
  private final Duration timeout;
  private final HttpClient client;

  OpenAiCompatibleCandidateProvider(
      URI pEndpoint, String pModel, String pApiKey, Duration pTimeout) {
    endpoint = pEndpoint;
    model = pModel;
    apiKey = pApiKey;
    timeout = pTimeout;
    client = HttpClient.newBuilder().connectTimeout(timeout).build();
  }

  @Override
  public ProviderResponse complete(String agentRole, String systemPrompt, String contextJson)
      throws IOException, InterruptedException {
    ObjectNode requestRoot = JSON.createObjectNode();
    requestRoot.put("model", model);
    requestRoot.put("temperature", 0);
    requestRoot.putObject("response_format").put("type", "json_object");
    var messages = requestRoot.putArray("messages");
    messages.addObject().put("role", "system").put("content", systemPrompt);
    messages.addObject().put("role", "user").put("content", contextJson);
    HttpRequest.Builder request =
        HttpRequest.newBuilder(endpoint)
            .timeout(timeout)
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(JSON.writeValueAsString(requestRoot)));
    if (!apiKey.isEmpty()) {
      request.header("Authorization", "Bearer " + apiKey);
    }
    HttpResponse<InputStream> response =
        client.send(request.build(), HttpResponse.BodyHandlers.ofInputStream());
    try (InputStream body = response.body()) {
      if (response.statusCode() != 200) {
        throw new IOException("Candidate provider returned HTTP " + response.statusCode());
      }
      String responseBody = readBoundedResponse(body);
      JsonNode content = JSON.readTree(responseBody).at("/choices/0/message/content");
      if (!content.isTextual()) {
        throw new IOException("Candidate provider response has no text content");
      }
      return new ProviderResponse(content.textValue(), model, sha256(responseBody));
    }
  }

  static String readBoundedResponse(InputStream input) throws IOException {
    byte[] response = input.readNBytes(MAX_RESPONSE_BYTES + 1);
    if (response.length > MAX_RESPONSE_BYTES) {
      throw new IOException("Candidate provider response exceeds 1048576 bytes");
    }
    return StandardCharsets.UTF_8.decode(ByteBuffer.wrap(response)).toString();
  }

  private static String sha256(String value) {
    try {
      return HexFormat.of()
          .formatHex(
              MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8)));
    } catch (NoSuchAlgorithmException e) {
      throw new AssertionError(e);
    }
  }
}
