// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.google.common.collect.ImmutableList;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.logging.Level;
import org.sosy_lab.common.log.LogManager;

/** Loads frozen predicate sets from predicate_sets/{benchmark}.json or .md. */
public final class FrozenPredicateLoader {

  private static final ObjectMapper JSON = new ObjectMapper();

  private final LogManager logger;
  private final Path frozenDir;

  public FrozenPredicateLoader(LogManager logger, Path frozenDirPath) {
    this.logger = logger;
    frozenDir = frozenDirPath;
  }

  public Optional<ImmutableList<String>> loadForBenchmark(String benchmarkBaseName) {
    Path json = frozenDir.resolve(benchmarkBaseName + ".json");
    if (Files.isRegularFile(json)) {
      return loadJson(json);
    }
    Path md = frozenDir.resolve(benchmarkBaseName + ".md");
    if (Files.isRegularFile(md)) {
      return loadMarkdown(md);
    }
    logger.log(Level.FINE, "VGuide: no frozen predicates for ", benchmarkBaseName);
    return Optional.empty();
  }

  private Optional<ImmutableList<String>> loadJson(Path file) {
    try {
      JsonNode root = JSON.readTree(file.toFile());
      if (!root.has("predicates") || !root.get("predicates").isArray()) {
        return Optional.empty();
      }
      List<String> preds = new ArrayList<>();
      for (JsonNode p : root.get("predicates")) {
        if (p.isTextual()) {
          preds.add(p.asText().strip());
        }
      }
      return preds.isEmpty() ? Optional.empty() : Optional.of(ImmutableList.copyOf(preds));
    } catch (IOException e) {
      logger.logDebugException(e, "VGuide frozen JSON read failed");
      return Optional.empty();
    }
  }

  private Optional<ImmutableList<String>> loadMarkdown(Path file) {
    try {
      List<String> lines = Files.readAllLines(file);
      boolean inBootstrap = false;
      List<String> preds = new ArrayList<>();
      for (String line : lines) {
        String trimmed = line.strip();
        if (trimmed.startsWith("## Bootstrap")) {
          inBootstrap = true;
          continue;
        }
        if (inBootstrap && trimmed.startsWith("## ")) {
          break;
        }
        if (inBootstrap && trimmed.startsWith("- `") && trimmed.endsWith("`")) {
          preds.add(trimmed.substring(3, trimmed.length() - 1).strip());
        } else if (inBootstrap && trimmed.startsWith("- (")) {
          int start = trimmed.indexOf('(');
          int end = trimmed.lastIndexOf(')');
          if (start >= 0 && end > start) {
            preds.add(trimmed.substring(start, end + 1).strip());
          }
        }
      }
      return preds.isEmpty() ? Optional.empty() : Optional.of(ImmutableList.copyOf(preds));
    } catch (IOException e) {
      logger.logDebugException(e, "VGuide frozen MD read failed");
      return Optional.empty();
    }
  }
}
