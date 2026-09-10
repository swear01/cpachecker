// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.truth.Truth.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.spy;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.sosy_lab.cpachecker.cfa.model.CFANode.newDummyCFANode;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableMap;
import com.google.common.collect.ImmutableSet;
import com.google.common.collect.ImmutableSetMultimap;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.Rule;
import org.junit.Test;
import org.junit.rules.TemporaryFolder;
import org.sosy_lab.common.collect.PathCopyingPersistentTreeMap;
import org.sosy_lab.common.configuration.Configuration;
import org.sosy_lab.common.log.LogManager;
import org.sosy_lab.cpachecker.cfa.model.CFANode;
import org.sosy_lab.cpachecker.core.interfaces.AbstractState;
import org.sosy_lab.cpachecker.core.interfaces.Precision;
import org.sosy_lab.cpachecker.core.reachedset.UnmodifiableReachedSet;
import org.sosy_lab.cpachecker.cpa.arg.ARGReachedSet;
import org.sosy_lab.cpachecker.cpa.arg.ARGState;
import org.sosy_lab.cpachecker.cpa.predicate.BlockFormulaStrategy.BlockFormulas;
import org.sosy_lab.cpachecker.cpa.predicate.PredicateAbstractState;
import org.sosy_lab.cpachecker.cpa.predicate.PredicatePrecision;
import org.sosy_lab.cpachecker.cpa.predicate.VocabularyGuide;
import org.sosy_lab.cpachecker.util.predicates.AbstractionFormula;
import org.sosy_lab.cpachecker.util.predicates.AbstractionPredicate;
import org.sosy_lab.cpachecker.util.predicates.interpolation.CounterexampleTraceInfo;
import org.sosy_lab.cpachecker.util.predicates.pathformula.PathFormula;
import org.sosy_lab.cpachecker.util.predicates.regions.SymbolicRegionManager;
import org.sosy_lab.cpachecker.util.predicates.smt.FormulaManagerView;
import org.sosy_lab.cpachecker.util.predicates.smt.SolverViewBasedTest0;
import org.sosy_lab.java_smt.api.BooleanFormula;

/** Refinement rows must preserve diagnostics needed by offline analysis. */
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
  public void appendJsonLinesStreamRowsAndPreservesPreviousRowsOnFailure() throws Exception {
    VGuideAnalysisDumper dumper =
        new VGuideAnalysisDumper(
            LOGGER,
            tmp.getRoot().toPath(),
            "task",
            "task",
            0,
            false,
            false,
            mgrv,
            new VGuideOptions(Configuration.builder().build()));
    Path rows = tmp.getRoot().toPath().resolve("rows.jsonl");
    String large = "x".repeat(1_000_000);
    dumper.appendJsonLine(
        rows, JSON.createObjectNode().put("row", 1).put("text", "quotes \" and newline\n漢字"));
    dumper.appendJsonLine(rows, JSON.createObjectNode().put("row", 2).put("text", large));

    assertThat(Files.readAllLines(rows, StandardCharsets.UTF_8)).hasSize(2);
    assertThat(Files.readString(rows, StandardCharsets.UTF_8)).endsWith("\n");
    assertThat(
            JSON.readTree(Files.readAllLines(rows, StandardCharsets.UTF_8).get(0))
                .path("text")
                .asText())
        .isEqualTo("quotes \" and newline\n漢字");
    assertThat(
            JSON.readTree(Files.readAllLines(rows, StandardCharsets.UTF_8).get(1))
                .path("text")
                .asText())
        .isEqualTo(large);

    Path failure = tmp.getRoot().toPath().resolve("not-a-file");
    Files.createDirectory(failure);
    dumper.appendJsonLine(failure, JSON.createObjectNode().put("row", 3));
    assertThat(Files.readAllLines(rows, StandardCharsets.UTF_8)).hasSize(2);
  }

  @Test
  public void cachesOnlyIdenticalBlockObjectsWithinOneRow() throws Exception {
    FormulaManagerView formulaManager = spy(mgrv);
    VGuideAnalysisDumper dumper =
        new VGuideAnalysisDumper(
            LOGGER,
            tmp.getRoot().toPath(),
            "task",
            "task",
            0,
            false,
            false,
            formulaManager,
            new VGuideOptions(Configuration.builder().build()));
    CFANode node = newDummyCFANode("f1");
    BooleanFormula blockOne = bmgrv.makeTrue();
    BooleanFormula blockTwo = bmgrv.makeFalse();
    BooleanFormula candidateOne =
        VocabularyGuide.parsePredicate("(= x (_ bv1 32))", mgrv, ImmutableSet.of());
    BooleanFormula candidateTwo =
        VocabularyGuide.parsePredicate("(= x (_ bv2 32))", mgrv, ImmutableSet.of());
    BooleanFormula candidateThree =
        VocabularyGuide.parsePredicate("(= x (_ bv3 32))", mgrv, ImmutableSet.of());
    ValidatedPredicate vpOne =
        new ValidatedPredicate(
            candidateOne,
            node,
            ValidatedPredicate.Classification.PRECISION_ONLY,
            "",
            ImmutableList.of(),
            false,
            false);
    ValidatedPredicate vpTwo =
        new ValidatedPredicate(
            candidateTwo,
            node,
            ValidatedPredicate.Classification.PRECISION_ONLY,
            "",
            ImmutableList.of(),
            false,
            false);
    ValidatedPredicate vpThree =
        new ValidatedPredicate(
            candidateThree,
            node,
            ValidatedPredicate.Classification.PRECISION_ONLY,
            "",
            ImmutableList.of(),
            false,
            false);
    VGuideAnalysisDumper.DumpValidatedPredicate dumpOne =
        new VGuideAnalysisDumper.DumpValidatedPredicate(
            1, "one", vpOne, blockOne, true, true, false, "");
    VGuideAnalysisDumper.DumpValidatedPredicate dumpTwo =
        new VGuideAnalysisDumper.DumpValidatedPredicate(
            2, "two", vpTwo, blockOne, true, true, false, "");
    VGuideAnalysisDumper.DumpValidatedPredicate dumpThree =
        new VGuideAnalysisDumper.DumpValidatedPredicate(
            3, "three", vpThree, blockTwo, true, true, false, "");
    BlockFormulas firstBlocks = new BlockFormulas(ImmutableList.of(blockOne, blockTwo));
    ContextPack pack =
        new ContextPack(
            1,
            "",
            "",
            ImmutableList.of(),
            ImmutableMap.of(),
            ImmutableSet.of(),
            firstBlocks,
            ImmutableList.of(),
            "",
            "");

    dumper.recordRefinement(
        1,
        true,
        null,
        1,
        null,
        pack,
        ImmutableList.of(),
        firstBlocks,
        CounterexampleTraceInfo.infeasible(ImmutableList.of()),
        null,
        null,
        ImmutableList.of(dumpOne, dumpTwo, dumpThree),
        ImmutableList.of(),
        ImmutableList.of(),
        null,
        null,
        null,
        -1,
        -1,
        false,
        null,
        null);

    verify(formulaManager, times(2)).dumpFormula(blockOne);
    verify(formulaManager, times(2)).dumpFormula(blockTwo);

    BlockFormulas secondBlocks = new BlockFormulas(ImmutableList.of(blockOne));
    dumper.recordRefinement(
        2,
        true,
        null,
        2,
        null,
        pack,
        ImmutableList.of(),
        secondBlocks,
        CounterexampleTraceInfo.infeasible(ImmutableList.of()),
        null,
        null,
        ImmutableList.of(dumpOne),
        ImmutableList.of(),
        ImmutableList.of(),
        null,
        null,
        null,
        -1,
        -1,
        false,
        null,
        null);

    verify(formulaManager, times(4)).dumpFormula(blockOne);
    Path rowFile = tmp.getRoot().toPath().resolve("tasks/task/refinements.jsonl");
    var rows = Files.readAllLines(rowFile, StandardCharsets.UTF_8);
    JsonNode firstRow = JSON.readTree(rows.get(0));
    JsonNode secondRow = JSON.readTree(rows.get(1));
    assertThat(firstRow.path("validated_predicates").get(0).path("block_formula_smt").asText())
        .isEqualTo(firstRow.path("block_formulas").get(0).path("smt").asText());
    assertThat(firstRow.path("validated_predicates").get(1).path("block_formula_smt").asText())
        .isEqualTo(firstRow.path("block_formulas").get(0).path("smt").asText());
    assertThat(firstRow.path("validated_predicates").get(2).path("block_formula_smt").asText())
        .isEqualTo(firstRow.path("block_formulas").get(1).path("smt").asText());
    assertThat(firstRow.path("block_formulas")).hasSize(2);
    assertThat(
            firstRow.path("block_formulas").get(0).path("smt").asText())
        .isNotEqualTo(firstRow.path("block_formulas").get(1).path("smt").asText());
    assertThat(secondRow.path("validated_predicates").get(0).path("block_formula_smt").asText())
        .isEqualTo(secondRow.path("block_formulas").get(0).path("smt").asText());
  }

  @Test
  public void schema5RecordsCandidateDiagnosticsAndRejections() throws Exception {
    VGuideOptions options = new VGuideOptions(Configuration.builder().build());
    VGuideAnalysisDumper dumper =
        new VGuideAnalysisDumper(
            LOGGER, tmp.getRoot().toPath(), "task", "task", 0, false, false, mgrv, options);
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
    VGuideAnalysisDumper.DumpValidatedPredicate suppressedPred =
        new VGuideAnalysisDumper.DumpValidatedPredicate(
            2, "(bvsge x (_ bv0 32))", vp, bmgrv.makeTrue(), true, true, false, "SAFE");
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

    String incomplete = "{\"candidates\":";
    dumper.recordLlmApiCall(
        1,
        1,
        "safe_primary",
        "safe",
        new PromptMessages("system", "user"),
        pack,
        PromptProfile.SAFE,
        new LlmProposalResult(
            incomplete,
            "",
            null,
            1,
            2,
            "request",
            "live",
            new LlmProposalResult.TerminalEvidence(
                200, "done", "length", "hash", incomplete.length(), null)),
        ImmutableList.of(),
        null);
    JsonNode call =
        JSON.readTree(
            Files.readAllLines(
                    tmp.getRoot()
                        .toPath()
                        .resolve("tasks")
                        .resolve("task")
                        .resolve("llm_rounds.jsonl"))
                .getFirst());
    assertThat(call.path("stream_state").asText()).isEqualTo("done");
    assertThat(call.path("finish_reason").asText()).isEqualTo("length");
    assertThat(call.path("response_parse_reason").asText())
        .isEqualTo(LoopHeadCandidateParser.REASON_INVALID_JSON);

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
        ImmutableList.of(dumpPred, suppressedPred),
        ImmutableList.of(dumpPred, suppressedPred),
        ImmutableList.of(rejection),
        null,
        null,
        null,
        -1,
        -1,
        false,
        null,
        null);

    Path rowFile =
        tmp.getRoot().toPath().resolve("tasks").resolve("task").resolve("refinements.jsonl");
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
    assertThat(row.path("validated_predicates").size()).isEqualTo(2);
    assertThat(row.path("validated_predicates").get(0).path("injected").asBoolean()).isTrue();
    assertThat(row.path("validated_predicates").get(1).path("injected").asBoolean()).isFalse();
    assertThat(row.path("precision_injected").size()).isEqualTo(1);

    JsonNode manifest = JSON.readTree(tmp.getRoot().toPath().resolve("run_manifest.json").toFile());
    assertThat(manifest.path("schema_version").asText()).isEqualTo("12");
    assertThat(manifest.path("model").asText()).isEqualTo("muse-spark-1.2-contributor");
  }

  @Test
  public void schema6RecordsCeHistoryMetadata() throws Exception {
    VGuideOptions options = new VGuideOptions(Configuration.builder().build());
    VGuideAnalysisDumper dumper =
        new VGuideAnalysisDumper(
            LOGGER, tmp.getRoot().toPath(), "task", "task", 0, false, false, mgrv, options);
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
        null,
        null,
        -1,
        -1,
        false,
        null,
        null);

    Path rowFile =
        tmp.getRoot().toPath().resolve("tasks").resolve("task").resolve("refinements.jsonl");
    JsonNode row = JSON.readTree(Files.readString(rowFile).strip());
    assertThat(row.path("ce_history").isArray()).isTrue();
    assertThat(row.path("ce_history").get(0).path("refinement_index").asInt()).isEqualTo(1);
    assertThat(row.path("ce_history").get(0).path("repeat_count").asInt()).isEqualTo(2);
    assertThat(row.path("ce_history_omitted").asInt()).isEqualTo(0);
  }

  @Test
  public void precisionBeforeSurvivesReachedSetMutation() throws Exception {
    VGuideOptions options = new VGuideOptions(Configuration.builder().build());
    VGuideAnalysisDumper dumper =
        new VGuideAnalysisDumper(
            LOGGER, tmp.getRoot().toPath(), "task", "task", 0, false, false, mgrv, options);
    BooleanFormula formula =
        VocabularyGuide.parsePredicate("(bvsge x (_ bv0 32))", mgrv, ImmutableSet.of());
    AbstractionPredicate predicate = mock(AbstractionPredicate.class);
    when(predicate.getSymbolicAtom()).thenReturn(formula);
    CFANode node = newDummyCFANode("f1");
    PredicatePrecision afterPrecision =
        new PredicatePrecision(
            ImmutableSetMultimap.of(),
            ImmutableSetMultimap.of(node, predicate),
            ImmutableSetMultimap.of(),
            ImmutableSet.of());
    AtomicReference<Precision> currentPrecision = new AtomicReference<>(PredicatePrecision.empty());
    AbstractState state = mock(AbstractState.class);
    UnmodifiableReachedSet reachedView = mock(UnmodifiableReachedSet.class);
    when(reachedView.getFirstState()).thenReturn(state);
    when(reachedView.getPrecision(state)).thenAnswer(unused -> currentPrecision.get());
    ARGReachedSet reached = mock(ARGReachedSet.class);
    when(reached.asReachedSet()).thenReturn(reachedView);

    ObjectNode precisionBefore = dumper.precisionSnapshot(reached);
    currentPrecision.set(afterPrecision);
    BlockFormulas formulas = new BlockFormulas(ImmutableList.of(formula));
    ContextPack pack =
        new ContextPack(
            1,
            "",
            "",
            ImmutableList.of(),
            ImmutableMap.of(),
            ImmutableSet.of(),
            formulas,
            ImmutableList.of(),
            "",
            "");

    dumper.recordRefinement(
        1,
        false,
        "schedule",
        null,
        null,
        pack,
        ImmutableList.of(),
        formulas,
        CounterexampleTraceInfo.infeasible(ImmutableList.of(formula)),
        precisionBefore,
        reached,
        null,
        null,
        null,
        null,
        null,
        null,
        -1,
        -1,
        false,
        null,
        null);

    Path rowFile =
        tmp.getRoot().toPath().resolve("tasks").resolve("task").resolve("refinements.jsonl");
    JsonNode row = JSON.readTree(Files.readString(rowFile).strip());
    assertThat(row.path("precision_local_before").size()).isEqualTo(0);
    assertThat(row.path("precision_local_after").path("N" + node.getNodeNumber()).size())
        .isEqualTo(1);
  }

  @Test
  public void recordsActualAbstractionFormulaForTraceState() throws Exception {
    VGuideOptions options = new VGuideOptions(Configuration.builder().build());
    VGuideAnalysisDumper dumper =
        new VGuideAnalysisDumper(
            LOGGER, tmp.getRoot().toPath(), "task", "task", 0, false, false, mgrv, options);
    BooleanFormula uninstantiated = imgrv.greaterThan(imgrv.makeVariable("x"), imgrv.makeNumber(0));
    BooleanFormula instantiated =
        imgrv.greaterThan(imgrv.makeVariable("x", 2), imgrv.makeNumber(0));
    PathFormula pathFormula = mock(PathFormula.class);
    AbstractionFormula abstractionFormula =
        new AbstractionFormula(
            mgrv,
            new SymbolicRegionManager(solver).makeTrue(),
            uninstantiated,
            instantiated,
            pathFormula,
            ImmutableSet.of());
    PredicateAbstractState predicateState =
        PredicateAbstractState.mkAbstractionState(
            pathFormula, abstractionFormula, PathCopyingPersistentTreeMap.of());
    ARGState argState = new ARGState(predicateState, null);
    BlockFormulas formulas = new BlockFormulas(ImmutableList.of(instantiated));
    ContextPack pack =
        new ContextPack(
            1,
            "",
            "",
            ImmutableList.of(),
            ImmutableMap.of(),
            ImmutableSet.of(),
            formulas,
            ImmutableList.of(),
            "",
            "");

    dumper.recordRefinement(
        1,
        false,
        "schedule",
        null,
        null,
        pack,
        ImmutableList.of(argState),
        formulas,
        CounterexampleTraceInfo.infeasible(ImmutableList.of(instantiated)),
        null,
        null,
        null,
        null,
        null,
        null,
        null,
        null,
        -1,
        -1,
        false,
        null,
        null);

    Path rowFile =
        tmp.getRoot().toPath().resolve("tasks").resolve("task").resolve("refinements.jsonl");
    JsonNode row = JSON.readTree(Files.readString(rowFile).strip());
    JsonNode dumped = row.path("abstraction_formulas_pre").get(0);
    assertThat(dumped.path("index").asInt()).isEqualTo(0);
    assertThat(dumped.path("uninstantiated_smt").asText()).contains("x");
    assertThat(dumped.path("instantiated_smt").asText()).contains("x@2");
  }
}
