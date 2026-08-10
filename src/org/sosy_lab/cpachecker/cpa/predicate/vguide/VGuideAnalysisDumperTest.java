// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.truth.Truth.assertThat;
import static org.sosy_lab.cpachecker.cfa.model.CFANode.newDummyCFANode;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableMap;
import com.google.common.collect.ImmutableSet;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import org.junit.Rule;
import org.junit.Test;
import org.junit.rules.TemporaryFolder;
import org.sosy_lab.common.configuration.Configuration;
import org.sosy_lab.common.log.LogManager;
import org.sosy_lab.cpachecker.cfa.model.CFANode;
import org.sosy_lab.cpachecker.cpa.predicate.BlockFormulaStrategy.BlockFormulas;
import org.sosy_lab.cpachecker.cpa.predicate.VocabularyGuide;
import org.sosy_lab.cpachecker.util.predicates.interpolation.CounterexampleTraceInfo;
import org.sosy_lab.cpachecker.util.predicates.smt.SolverViewBasedTest0;
import org.sosy_lab.java_smt.api.BooleanFormula;

/** Schema-5 refinement rows must carry candidate diagnostics and observable rejections. */
public class VGuideAnalysisDumperTest extends SolverViewBasedTest0 {

  private static final LogManager LOGGER = LogManager.createNullLogManager();
  private static final ObjectMapper JSON = new ObjectMapper();

  @Rule public final TemporaryFolder tmp = new TemporaryFolder();

  @org.junit.Before
  public void resetManifestFlag() {
    // run_manifest.json is written once per JVM (static); each test gets its own run root.
    VGuideAnalysisDumper.MANIFEST_WRITTEN.set(false);
  }

  @Test
  public void schema5RecordsCandidateDiagnosticsAndRejections() throws Exception {
    VGuideOptions options = new VGuideOptions(Configuration.builder().build());
    VGuideAnalysisDumper dumper =
        new VGuideAnalysisDumper(
            LOGGER, tmp.getRoot().toPath(), "task", "task", 0, false, mgrv, options);
    CFANode node = newDummyCFANode("f1");
    LoopHeadInfo head = new LoopHeadInfo(node, "ignored", "f1");
    BooleanFormula formula =
        VocabularyGuide.parsePredicate("(bvsge x (_ bv0 32))", mgrv, ImmutableSet.of());
    ValidatedPredicate vp =
        new ValidatedPredicate(
            formula,
            node,
            ValidatedPredicate.Classification.PRECISION_ONLY,
            "bound",
            ImmutableList.of("x"),
            true,
            false);
    VGuideAnalysisDumper.DumpValidatedPredicate dumpPred =
        new VGuideAnalysisDumper.DumpValidatedPredicate(
            1, "(bvsge x (_ bv0 32))", vp, bmgrv.makeTrue(), true, true, true, "SAFE");
    CandidateRejection rejection =
        new CandidateRejection(
            "{\"loop_head\":\"N1\"}",
            "N1",
            "(bvslt w n)",
            PredicateValidationPipeline.REASON_VARIABLE_NOT_IN_SCOPE,
            "variables not visible at N1: [w]");
    ContextPack pack =
        new ContextPack(
            1,
            "",
            "",
            ImmutableList.of(head),
            ImmutableMap.of(),
            ImmutableSet.of(),
            new BlockFormulas(ImmutableList.of(formula)),
            ImmutableList.of(),
            "",
            "");

    dumper.recordRefinement(
        1,
        true,
        null,
        1,
        "ce",
        pack,
        ImmutableList.of(),
        new BlockFormulas(ImmutableList.of(formula)),
        CounterexampleTraceInfo.infeasible(ImmutableList.of(formula)),
        null,
        null,
        ImmutableList.of(dumpPred),
        ImmutableList.of(dumpPred),
        ImmutableList.of(rejection),
        null,
        false,
        null);

    Path rowFile = tmp.getRoot().toPath().resolve("tasks").resolve("task").resolve("refinements.jsonl");
    JsonNode row = JSON.readTree(Files.readString(rowFile).strip());
    JsonNode validated = row.path("validated_predicates").get(0);
    assertThat(validated.path("role").asText()).isEqualTo("bound");
    assertThat(validated.path("declared_variables").get(0).asText()).isEqualTo("x");
    assertThat(validated.path("over_specific").asBoolean()).isTrue();
    assertThat(validated.path("group_conflict").asBoolean()).isFalse();
    JsonNode rejected = row.path("candidate_rejections").get(0);
    assertThat(rejected.path("reason").asText())
        .isEqualTo(PredicateValidationPipeline.REASON_VARIABLE_NOT_IN_SCOPE);
    assertThat(rejected.path("detail").asText()).contains("N1");
    assertThat(rejected.path("predicate").asText()).isEqualTo("(bvslt w n)");

    JsonNode manifest =
        JSON.readTree(tmp.getRoot().toPath().resolve("run_manifest.json").toFile());
    assertThat(manifest.path("schema_version").asText()).isEqualTo("9");
  }

  @Test
  public void schema6RecordsCeHistoryMetadata() throws Exception {
    VGuideOptions options = new VGuideOptions(Configuration.builder().build());
    VGuideAnalysisDumper dumper =
        new VGuideAnalysisDumper(
            LOGGER, tmp.getRoot().toPath(), "task", "task", 0, false, mgrv, options);
    CFANode node = newDummyCFANode("f1");
    LoopHeadInfo head = new LoopHeadInfo(node, "ignored", "f1");
    BooleanFormula formula =
        VocabularyGuide.parsePredicate("(bvsge x (_ bv0 32))", mgrv, ImmutableSet.of());
    ValidatedPredicate vp =
        new ValidatedPredicate(
            formula,
            node,
            ValidatedPredicate.Classification.PRECISION_ONLY,
            "",
            ImmutableList.of(),
            false,
            false);
    VGuideAnalysisDumper.DumpValidatedPredicate dumpPred =
        new VGuideAnalysisDumper.DumpValidatedPredicate(
            1, "(bvsge x (_ bv0 32))", vp, bmgrv.makeTrue(), true, true, false, "SAFE");
    CeHistoryStore store = new CeHistoryStore();
    store.record(1, "{\"schema_version\":\"structured-ce-v1\",\"trace\":[]}");
    store.record(2, "{\"schema_version\":\"structured-ce-v1\",\"trace\":[]}");
    ContextPack pack =
        new ContextPack(
            1,
            "",
            "",
            ImmutableList.of(head),
            ImmutableMap.of(),
            ImmutableSet.of(),
            new BlockFormulas(ImmutableList.of(formula)),
            ImmutableList.of(),
            "",
            "");

    dumper.recordRefinement(
        2,
        true,
        null,
        2,
        "ce",
        pack,
        ImmutableList.of(),
        new BlockFormulas(ImmutableList.of(formula)),
        CounterexampleTraceInfo.infeasible(ImmutableList.of(formula)),
        null,
        null,
        ImmutableList.of(dumpPred),
        ImmutableList.of(dumpPred),
        ImmutableList.of(),
        store.snapshot(),
        false,
        null);

    Path rowFile =
        tmp.getRoot().toPath().resolve("tasks").resolve("task").resolve("refinements.jsonl");
    JsonNode row = JSON.readTree(Files.readString(rowFile).strip());
    assertThat(row.path("ce_history").isArray()).isTrue();
    assertThat(row.path("ce_history").get(0).path("refinement_index").asInt()).isEqualTo(1);
    assertThat(row.path("ce_history").get(0).path("repeat_count").asInt()).isEqualTo(2);
    assertThat(row.path("ce_history_omitted").asInt()).isEqualTo(0);
  }
}
