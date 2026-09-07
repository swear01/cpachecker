// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.truth.Truth.assertThat;
import static org.junit.Assert.assertThrows;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableMap;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.Authenticator;
import java.net.CookieHandler;
import java.net.ProxySelector;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpHeaders;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.function.Supplier;
import java.util.logging.Level;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLSession;
import org.junit.Test;
import org.sosy_lab.common.log.LogManager;
import org.sosy_lab.cpachecker.cpa.predicate.LlmApiUrl;

public class PredicateProposalClientTest {

  private static final ObjectMapper JSON = new ObjectMapper();
  private static final PromptMessages PROMPT = new PromptMessages("system", "user");

  @Test
  public void defaultsToMetaContributor() {
    assertThat(PredicateProposalClient.provider(null)).isEqualTo("meta");
    assertThat(PredicateProposalClient.model("meta", null)).isEqualTo("muse-spark-1.2-contributor");
    assertThat(LlmApiUrl.DEFAULT_API_URL).isEqualTo("https://api.meta.ai/v1/chat/completions");
  }

  @Test
  public void deepSeekIsReplayOnly() {
    assertThrows(
        IllegalStateException.class,
        () -> PredicateProposalClient.validateProviderMode("deepseek", false));
    PredicateProposalClient.validateProviderMode("deepseek", true);
  }

  @Test
  public void metaRequestUsesSchemaAndMinimalReasoningWhenDisabled() throws Exception {
    JsonNode request =
        JSON.readTree(
            PredicateProposalClient.buildRequestBody(
                PROMPT, "meta", "muse-spark-1.2-contributor", 1024, false, null));

    assertThat(request.path("model").asText()).isEqualTo("muse-spark-1.2-contributor");
    assertThat(request.path("reasoning_effort").asText()).isEqualTo("minimal");
    assertThat(request.has("thinking")).isFalse();
    JsonNode format = request.path("response_format");
    assertThat(format.path("type").asText()).isEqualTo("json_schema");
    JsonNode schema = format.path("json_schema").path("schema");
    assertThat(schema.path("properties").path("schema_version").path("const").asText())
        .isEqualTo("loop-head-candidate-v1");
    assertThat(schema.path("required").toString()).contains("candidates");
    JsonNode alternatives =
        schema.path("properties").path("candidates").path("items").path("anyOf");
    assertThat(alternatives.size()).isEqualTo(2);
    assertThat(alternatives.get(0).path("required").get(0).asText()).isEqualTo("loop_head");
    assertThat(alternatives.get(1).path("required").get(0).asText()).isEqualTo("loop_heads");
  }

  @Test
  public void metaRequestUsesConfiguredReasoningEffortWhenEnabled() throws Exception {
    JsonNode request =
        JSON.readTree(
            PredicateProposalClient.buildRequestBody(
                PROMPT, "meta", "muse-spark-1.2-contributor", 1024, true, "high"));

    assertThat(request.path("reasoning_effort").asText()).isEqualTo("high");
    assertThat(request.has("thinking")).isFalse();
  }

  @Test
  public void deepSeekRequestKeepsJsonObjectAndDisabledThinking() throws Exception {
    JsonNode request =
        JSON.readTree(
            PredicateProposalClient.buildRequestBody(
                PROMPT, "deepseek", "deepseek-v4-flash", 1024, false, null));

    assertThat(request.path("response_format").path("type").asText()).isEqualTo("json_object");
    assertThat(request.path("thinking").path("type").asText()).isEqualTo("disabled");
    assertThat(request.has("reasoning_effort")).isFalse();
    assertThat(request.path("stream").asBoolean()).isTrue();
    assertThat(request.path("stream_options").path("include_usage").asBoolean()).isTrue();
  }

  @Test
  public void streamingResponseAssemblesReasoningContentAndUsage() throws Exception {
    String response =
        "event: message\nid: 1\ndata:   \n"
            + "data: {\"choices\":[{\"delta\":{\"reasoning_content\":\"think \"}}]}\n\n"
            + "data: {\"choices\":[{\"delta\":{\"reasoning_content\":\"more\","
            + "\"content\":\"{\\\"candidates\\\":\"}}]}\n\n"
            + "data: {\"choices\":[{\"delta\":{\"content\":\"[]}\"}}],"
            + "\"usage\":{\"prompt_tokens\":10,\"completion_tokens\":20}}\n\n"
            + "data: [DONE]   \n\n";

    LlmProposalResult result =
        PredicateProposalClient.parseStreamingResponse(
            new ByteArrayInputStream(response.getBytes(StandardCharsets.UTF_8)));

    assertThat(result.content()).isEqualTo("{\"candidates\":[]}");
    assertThat(result.reasoningContent()).isEqualTo("think more");
    assertThat(result.usage().path("prompt_tokens").asInt()).isEqualTo(10);
    assertThat(result.usage().path("completion_tokens").asInt()).isEqualTo(20);
  }

  @Test(expected = IOException.class)
  public void streamingResponseWithoutDoneFailsClosed() throws Exception {
    String response = "data: {\"choices\":[{\"delta\":{\"content\":\"partial\"}}]}\n\n";

    PredicateProposalClient.parseStreamingResponse(
        new ByteArrayInputStream(response.getBytes(StandardCharsets.UTF_8)));
  }

  @Test
  public void streamingResponseReportsProviderError() throws Exception {
    String response = "data: {\"error\":{\"message\":\"context limit\"}}\n\n";

    IOException failure =
        assertThrows(
            IOException.class,
            () ->
                PredicateProposalClient.parseStreamingResponse(
                    new ByteArrayInputStream(response.getBytes(StandardCharsets.UTF_8))));

    assertThat(failure).hasMessageThat().contains("context limit");
  }

  @Test
  public void streamingResponseReportsStringProviderError() throws Exception {
    String response = "data: {\"error\":\"unauthorized\"}\n\n";

    IOException failure =
        assertThrows(
            IOException.class,
            () ->
                PredicateProposalClient.parseStreamingResponse(
                    new ByteArrayInputStream(response.getBytes(StandardCharsets.UTF_8))));

    assertThat(failure).hasMessageThat().contains("unauthorized");
  }

  @Test
  public void recordsRetryAttemptAndSuccess() throws Exception {
    List<String> logs = new ArrayList<>();
    byte[] response =
        "data: {\"choices\":[{\"delta\":{\"content\":\"ok\"}}]}\n\ndata: [DONE]\n\n"
            .getBytes(StandardCharsets.UTF_8);
    var http =
        new MockHttpClient(
            ImmutableList.of(
                new MockHttpResponse(503, new ByteArrayInputStream(new byte[0])),
                new MockHttpResponse(200, new ByteArrayInputStream(response))));
    var client =
        new PredicateProposalClient(
            new RecordingLogManager(logs), URI.create("http://loopback/"), http, 1, 0);
    assertThat(client.proposeWithUsage(PROMPT).content()).isEqualTo("ok");
    assertThat(http.calls()).isEqualTo(2);
    assertThat(logs).hasSize(5);
    assertThat(JSON.readTree(logs.getFirst()).path("phase").asText()).isEqualTo("start");
    assertThat(JSON.readTree(logs.get(1)).path("outcome").asText())
        .isEqualTo("retryable_http_error");
    assertThat(JSON.readTree(logs.get(3)).path("outcome").asText()).isEqualTo("stream_success");
    assertThat(JSON.readTree(logs.get(4)).path("outcome").asText()).isEqualTo("success");
    assertThat(JSON.readTree(logs.get(1)).path("http_status").asInt()).isEqualTo(503);
    assertThat(JSON.readTree(logs.get(3)).path("attempt").asInt()).isEqualTo(2);
    assertThat(JSON.readTree(logs.get(4)).path("logical_request_scope").asText())
        .isEqualTo("client_instance");
  }

  @Test
  public void recordsAllFailedRequestWithoutResponseRow() throws Exception {
    List<String> logs = new ArrayList<>();
    var http =
        new MockHttpClient(
            ImmutableList.of(
                new MockHttpResponse(503, new ByteArrayInputStream(new byte[0])),
                new MockHttpResponse(503, new ByteArrayInputStream(new byte[0]))));
    var client =
        new PredicateProposalClient(
            new RecordingLogManager(logs), URI.create("http://loopback/"), http, 1, 0);
    assertThrows(IOException.class, () -> client.proposeWithUsage(PROMPT));
    assertThat(logs).hasSize(5);
    assertThat(JSON.readTree(logs.get(4)).path("outcome").asText()).isEqualTo("retry_exhausted");
    assertThat(JSON.readTree(logs.get(4)).path("event").asText()).isEqualTo("llm_request_outcome");
  }

  @Test
  public void recordsInterruptedSendAsTerminalAttempt() throws Exception {
    List<String> logs = new ArrayList<>();
    var client =
        new PredicateProposalClient(
            new RecordingLogManager(logs),
            URI.create("http://loopback/"),
            new MockHttpClient(true),
            1,
            0);
    assertThrows(InterruptedException.class, () -> client.proposeWithUsage(PROMPT));
    assertThat(logs).hasSize(3);
    assertThat(JSON.readTree(logs.get(1)).path("outcome").asText()).isEqualTo("interrupted");
    assertThat(JSON.readTree(logs.get(2)).path("outcome").asText()).isEqualTo("interrupted");
  }

  @Test
  public void recordsNonretryableErrorBodyReadFailure() throws Exception {
    List<String> logs = new ArrayList<>();
    var client =
        new PredicateProposalClient(
            new RecordingLogManager(logs),
            URI.create("http://loopback/"),
            new MockHttpClient(
                ImmutableList.of(new MockHttpResponse(400, new FailingInputStream()))),
            2,
            0);
    assertThrows(IOException.class, () -> client.proposeWithUsage(PROMPT));
    assertThat(logs).hasSize(3);
    assertThat(JSON.readTree(logs.get(1)).path("outcome").asText()).isEqualTo("http_error");
    assertThat(JSON.readTree(logs.get(2)).path("outcome").asText()).isEqualTo("failed");
  }

  @Test
  public void recordsStreamCloseFailureBeforeSuccess() throws Exception {
    List<String> logs = new ArrayList<>();
    byte[] response =
        "data: {\"choices\":[{\"delta\":{\"content\":\"ok\"}}]}\n\ndata: [DONE]\n\n"
            .getBytes(StandardCharsets.UTF_8);
    var client =
        new PredicateProposalClient(
            new RecordingLogManager(logs),
            URI.create("http://loopback/"),
            new MockHttpClient(
                ImmutableList.of(
                    new MockHttpResponse(200, new CloseOnSecondCloseInputStream(response)))),
            0,
            0);
    assertThrows(IOException.class, () -> client.proposeWithUsage(PROMPT));
    assertThat(logs).hasSize(3);
    assertThat(JSON.readTree(logs.get(1)).path("outcome").asText())
        .isEqualTo("stream_close_failure");
    assertThat(logs.toString()).doesNotContain("success");
  }

  private static final class MockHttpClient extends HttpClient {
    private final ArrayDeque<HttpResponse<InputStream>> responses;
    private final boolean interrupt;
    private int calls;

    MockHttpClient(List<HttpResponse<InputStream>> pResponses) {
      this(pResponses, false);
    }

    MockHttpClient(boolean pInterrupt) {
      this(ImmutableList.of(), pInterrupt);
    }

    private MockHttpClient(List<HttpResponse<InputStream>> pResponses, boolean pInterrupt) {
      responses = new ArrayDeque<>(pResponses);
      interrupt = pInterrupt;
    }

    int calls() {
      return calls;
    }

    @Override
    @SuppressWarnings("unchecked")
    public <T> HttpResponse<T> send(HttpRequest request, HttpResponse.BodyHandler<T> handler)
        throws IOException, InterruptedException {
      calls++;
      if (interrupt) {
        throw new InterruptedException();
      }
      return (HttpResponse<T>) (HttpResponse<?>) responses.removeFirst();
    }

    @Override
    public Optional<CookieHandler> cookieHandler() {
      return Optional.empty();
    }

    @Override
    public Optional<java.time.Duration> connectTimeout() {
      return Optional.empty();
    }

    @Override
    public Redirect followRedirects() {
      return Redirect.NEVER;
    }

    @Override
    public Optional<ProxySelector> proxy() {
      return Optional.empty();
    }

    @Override
    public SSLContext sslContext() {
      try {
        return SSLContext.getDefault();
      } catch (NoSuchAlgorithmException e) {
        throw new AssertionError(e);
      }
    }

    @Override
    public SSLParameters sslParameters() {
      return new SSLParameters();
    }

    @Override
    public Optional<Authenticator> authenticator() {
      return Optional.empty();
    }

    @Override
    public Version version() {
      return Version.HTTP_1_1;
    }

    @Override
    public Optional<Executor> executor() {
      return Optional.empty();
    }

    @Override
    public <T> CompletableFuture<HttpResponse<T>> sendAsync(
        HttpRequest r, HttpResponse.BodyHandler<T> h) {
      throw new UnsupportedOperationException();
    }

    @Override
    public <T> CompletableFuture<HttpResponse<T>> sendAsync(
        HttpRequest r, HttpResponse.BodyHandler<T> h, HttpResponse.PushPromiseHandler<T> p) {
      throw new UnsupportedOperationException();
    }
  }

  private record MockHttpResponse(int statusCode, InputStream body)
      implements HttpResponse<InputStream> {
    @Override
    public HttpRequest request() {
      return null;
    }

    @Override
    public Optional<HttpResponse<InputStream>> previousResponse() {
      return Optional.empty();
    }

    @Override
    public HttpHeaders headers() {
      return HttpHeaders.of(ImmutableMap.of(), (n, v) -> true);
    }

    @Override
    public Optional<SSLSession> sslSession() {
      return Optional.empty();
    }

    @Override
    public URI uri() {
      return URI.create("http://loopback/");
    }

    @Override
    public HttpClient.Version version() {
      return HttpClient.Version.HTTP_1_1;
    }
  }

  private static final class FailingInputStream extends InputStream {
    @Override
    public int read() throws IOException {
      throw new IOException("test body read failure");
    }

    @Override
    public int read(byte[] bytes, int offset, int length) throws IOException {
      throw new IOException("test body read failure");
    }
  }

  private static final class CloseOnSecondCloseInputStream extends InputStream {
    private final ByteArrayInputStream delegate;
    private int closes;

    CloseOnSecondCloseInputStream(byte[] bytes) {
      delegate = new ByteArrayInputStream(bytes);
    }

    @Override
    public int read() {
      return delegate.read();
    }

    @Override
    public int read(byte[] bytes, int offset, int length) {
      return delegate.read(bytes, offset, length);
    }

    @Override
    public void close() throws IOException {
      if (++closes == 2) {
        throw new IOException("test close failure");
      }
    }
  }

  private static final class RecordingLogManager implements LogManager {
    private final List<String> logs;

    RecordingLogManager(List<String> pLogs) {
      logs = pLogs;
    }

    @Override
    public LogManager withComponentName(String name) {
      return this;
    }

    @Override
    public boolean wouldBeLogged(Level level) {
      return true;
    }

    @Override
    public void log(Level level, Object... messages) {
      if (messages.length > 1 && messages[0].toString().startsWith("VGuide LLM HTTP evidence")) {
        logs.add(messages[1].toString());
      }
    }

    @Override
    public void log(Level level, Supplier<String> msgSupplier) {}

    @Override
    public void logf(Level level, String format, Object... args) {}

    @Override
    public void logUserException(Level level, Throwable throwable, String message) {}

    @Override
    public void logfUserException(
        Level level, Throwable throwable, String format, Object... args) {}

    @Override
    public void logDebugException(Throwable throwable, String message) {}

    @Override
    public void logfDebugException(Throwable throwable, String format, Object... args) {}

    @Override
    public void logDebugException(Throwable throwable) {}

    @Override
    public void logException(Level level, Throwable throwable, String message) {}

    @Override
    public void logfException(Level level, Throwable throwable, String format, Object... args) {}

    @Override
    public void flush() {}
  }
}
