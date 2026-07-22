// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-FileCopyrightText: 2026 SSU-WEI HUANG <https://github.com/swear01>
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import java.io.IOException;
import java.io.PrintStream;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Level;
import org.sosy_lab.common.io.IO;
import org.sosy_lab.common.log.LogManager;
import org.sosy_lab.cpachecker.core.CPAcheckerResult.Result;
import org.sosy_lab.cpachecker.core.interfaces.Statistics;
import org.sosy_lab.cpachecker.core.reachedset.UnmodifiableReachedSet;

final class VGuideStatistics implements Statistics {

  private static final ObjectMapper JSON = new ObjectMapper();

  private final LogManager logger;
  private final Path telemetryFile;
  private final ArrayNode events = JSON.createArrayNode();
  private final AtomicInteger rounds = new AtomicInteger();
  private final AtomicInteger proposed = new AtomicInteger();
  private final AtomicInteger activated = new AtomicInteger();
  private final AtomicInteger rejected = new AtomicInteger();

  VGuideStatistics(LogManager pLogger, Path pTelemetryFile) {
    logger = pLogger;
    telemetryFile = pTelemetryFile;
  }

  synchronized void record(
      int refinement,
      AgentPortfolio.PortfolioResult portfolio,
      Iterable<ValidatedCandidate> accepted,
      int rejectedCount) {
    rounds.incrementAndGet();
    proposed.addAndGet(portfolio.candidates().size());
    rejected.addAndGet(rejectedCount);
    var event = events.addObject();
    event.put("schema_version", "vguide-telemetry-v1");
    event.put("refinement", refinement);
    var calls = event.putArray("provider_calls");
    for (AgentPortfolio.ProviderCall call : portfolio.providerCalls()) {
      calls
          .addObject()
          .put("agent_role", call.agentRole())
          .put("model", call.model())
          .put("response_sha256", call.responseSha256());
    }
    var candidates = event.putArray("activated_candidates");
    for (ValidatedCandidate candidate : accepted) {
      activated.incrementAndGet();
      candidates
          .addObject()
          .put("loop_head_id", candidate.proposal().loopHeadId())
          .put("predicate", candidate.proposal().predicate())
          .put("agent_role", candidate.proposal().agentRole());
    }
    event.put("rejected_candidates", rejectedCount);
  }

  @Override
  public void printStatistics(PrintStream out, Result result, UnmodifiableReachedSet reached) {
    put(out, "Augmented refinement rounds", rounds);
    put(out, "Proposed candidates", proposed);
    put(out, "Activated candidates", activated);
    put(out, "Rejected candidates", rejected);
  }

  @Override
  public void writeOutputFiles(Result result, UnmodifiableReachedSet reached) {
    if (telemetryFile == null) {
      return;
    }
    try (Writer writer = IO.openOutputFile(telemetryFile, StandardCharsets.UTF_8)) {
      JSON.writerWithDefaultPrettyPrinter().writeValue(writer, events);
    } catch (IOException e) {
      logger.logUserException(Level.WARNING, e, "Could not write VGuide telemetry");
    }
  }

  @Override
  public String getName() {
    return "VGuide";
  }
}
