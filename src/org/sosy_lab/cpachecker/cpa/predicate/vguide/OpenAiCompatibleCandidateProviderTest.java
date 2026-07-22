// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-FileCopyrightText: 2026 SSU-WEI HUANG <https://github.com/swear01>
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.truth.Truth.assertThat;
import static org.junit.Assert.assertThrows;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.google.common.base.Splitter;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.Test;

public class OpenAiCompatibleCandidateProviderTest {

  @Test
  public void rejectsOversizedResponseBeforeParsing() {
    assertThrows(
        java.io.IOException.class,
        () ->
            OpenAiCompatibleCandidateProvider.readBoundedResponse(
                new ByteArrayInputStream(new byte[1_048_577])));
  }

  @Test
  public void sendsContextAndExtractsStrictContent() throws Exception {
    AtomicReference<String> requestBody = new AtomicReference<>();
    try (ServerSocket server = new ServerSocket(0, 1, InetAddress.getLoopbackAddress());
        ExecutorService executor = Executors.newSingleThreadExecutor()) {
      Future<?> responseTask =
          executor.submit(
              () -> {
                try (Socket connection = server.accept()) {
                  requestBody.set(readRequestBody(connection.getInputStream()));
                  var root = new ObjectMapper().createObjectNode();
                  root.putArray("choices")
                      .addObject()
                      .putObject("message")
                      .put(
                          "content",
                          "{\"schema_version\":\"vguide-candidates-v1\",\"candidates\":[]}");
                  byte[] response = new ObjectMapper().writeValueAsBytes(root);
                  byte[] headers =
                      ("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: "
                              + response.length
                              + "\r\nConnection: close\r\n\r\n")
                          .getBytes(StandardCharsets.US_ASCII);
                  connection.getOutputStream().write(headers);
                  connection.getOutputStream().write(response);
                }
                return null;
              });
      String host = server.getInetAddress().getHostAddress();
      String uriHost = host.contains(":") ? "[" + host + "]" : host;
      CandidateProvider provider =
          new OpenAiCompatibleCandidateProvider(
              new java.net.URI(
                  "http://" + uriHost + ":" + server.getLocalPort() + "/v1/chat/completions"),
              "test-model",
              "",
              Duration.ofSeconds(2));

      CandidateProvider.ProviderResponse response =
          provider.complete("invariant", "system", "{\"context\":true}");

      assertThat(response.content())
          .isEqualTo("{\"schema_version\":\"vguide-candidates-v1\",\"candidates\":[]}");
      assertThat(response.model()).isEqualTo("test-model");
      assertThat(response.responseSha256()).hasLength(64);
      assertThat(requestBody.get()).contains("\\\"context\\\":true");
      assertThat(requestBody.get()).contains("test-model");
      responseTask.get();
    }
  }

  private static String readRequestBody(InputStream input) throws Exception {
    ByteArrayOutputStream headers = new ByteArrayOutputStream();
    int previous3 = -1;
    int previous2 = -1;
    int previous1 = -1;
    int current;
    while ((current = input.read()) != -1) {
      headers.write(current);
      if (previous3 == '\r' && previous2 == '\n' && previous1 == '\r' && current == '\n') {
        break;
      }
      previous3 = previous2;
      previous2 = previous1;
      previous1 = current;
    }
    String headerText = headers.toString(StandardCharsets.US_ASCII);
    int contentLength = 0;
    for (String header : Splitter.on("\r\n").split(headerText)) {
      String normalized = header.toLowerCase(Locale.ROOT);
      if (normalized.startsWith("content-length:")) {
        contentLength = Integer.parseInt(header.substring(header.indexOf(':') + 1).trim());
      }
    }
    return StandardCharsets.UTF_8
        .decode(ByteBuffer.wrap(input.readNBytes(contentLength)))
        .toString();
  }
}
