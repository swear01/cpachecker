// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.truth.Truth.assertThat;
import static org.junit.Assert.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableMap;
import com.google.common.collect.ImmutableSet;
import java.io.IOException;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.util.Arrays;
import java.util.List;
import java.util.Optional;
import java.util.logging.Level;
import java.util.stream.Collectors;
import org.junit.Test;
import org.mockito.ArgumentCaptor;
import org.sosy_lab.common.configuration.Configuration;
import org.sosy_lab.common.log.LogManager;
import org.sosy_lab.cpachecker.cfa.CFA;
import org.sosy_lab.cpachecker.cfa.model.CFANode;
import org.sosy_lab.cpachecker.cpa.arg.ARGState;
import org.sosy_lab.cpachecker.cpa.arg.path.ARGPath;
import org.sosy_lab.cpachecker.cpa.predicate.BlockFormulaStrategy.BlockFormulas;
import org.sosy_lab.cpachecker.util.predicates.interpolation.CounterexampleTraceInfo;
import org.sosy_lab.cpachecker.util.predicates.smt.FormulaManagerView;
import org.sosy_lab.java_smt.api.BooleanFormula;

/** Exercises the production round with deterministic client/validator results, without a solver. */
public class VGuideRepairFlowTest {

  @Test
  public void partialValidationUsesOneRepairWithRemainingBudgetAndKeepsEvidence() throws Exception {
    Fixture f = new Fixture();
    when(f.client.proposeWithUsage(any(PromptMessages.class)))
        .thenReturn(f.response(f.primaryJson()), f.response(f.repairJson()));
    f.run();

    ArgumentCaptor<PromptMessages> messages = ArgumentCaptor.forClass(PromptMessages.class);
    verify(f.client, times(2)).proposeWithUsage(messages.capture());
    assertThat(messages.getAllValues().get(1).fullText()).contains("Return at most 1 candidates");
    assertThat(messages.getAllValues().get(1).fullText()).contains("reason=variable_not_in_scope");
    assertThat(messages.getAllValues().get(1).fullText()).contains("head=" + f.head.label());
    assertThat(messages.getAllValues().get(1)).isNotEqualTo(messages.getAllValues().getFirst());
    verify(f.scheduler).recordCallCompleted();
    verify(f.wall, times(2)).recordLlmCall(anyLong());
    ArgumentCaptor<List<LoopHeadCandidate>> repaired = candidateCaptor();
    verify(f.pipeline).validateCandidates(eq(f.pack), repaired.capture(), anyList(), any());
    assertThat(repaired.getValue()).hasSize(1);
    assertThat(repaired.getValue().getFirst().predicate()).isEqualTo("(= x (_ bv1 32))");
    assertThat(((ValidationResult) field(f.bridge, "lastValidation")).validated())
        .containsExactly(f.accepted, f.replacement)
        .inOrder();
    assertThat(field(field(f.bridge, "pendingDump"), "rejections"))
        .isEqualTo(f.primary.rejections());
  }

  @Test
  public void firstSafeRoundRequestsConfiguredExtrasAndRetainsTheirCandidates() throws Exception {
    Fixture f = new Fixture(false, 2);
    when(f.client.proposeWithUsage(any(PromptMessages.class)))
        .thenReturn(f.response(f.primaryJson()));
    when(f.client.proposeParallelExtrasWithUsage(any(PromptMessages.class), eq(1), anyInt()))
        .thenReturn(List.of(f.response(f.json("(= x (_ bv1 32))"))));
    f.run();

    verify(f.client, times(1)).proposeWithUsage(any(PromptMessages.class));
    verify(f.client).proposeParallelExtrasWithUsage(any(PromptMessages.class), eq(1), anyInt());
    ArgumentCaptor<List<LoopHeadCandidate>> candidates = candidateCaptor();
    verify(f.pipeline).validateCandidates(eq(f.pack), candidates.capture(), anyList());
    assertThat(candidates.getValue()).hasSize(3);
    assertThat(candidates.getValue().get(2).predicate()).isEqualTo("(= x (_ bv1 32))");
  }

  @Test
  public void primaryFailuresStillExhaustTheScheduledRequestBudget() throws Exception {
    Fixture f = new Fixture(false);
    LlmCallScheduler actualScheduler =
        new LlmCallScheduler(
            new VGuideOptions(
                Configuration.builder()
                    .setOption("vguide.llmCallSchedule", "every_n")
                    .setOption("vguide.llmEveryNSpuriousRefinements", "1")
                    .setOption("vguide.maxLlmRoundsPerAnalysis", "4")
                    .build()),
            f.logger);
    Field scheduler = VGuideRefinementBridge.class.getDeclaredField("llmScheduler");
    scheduler.setAccessible(true);
    scheduler.set(f.bridge, actualScheduler);
    when(f.client.proposeWithUsage(any(PromptMessages.class)))
        .thenThrow(new IOException("offline primary failure"));
    for (int refinement = 1; refinement <= 6; refinement++) {
      f.bridge.onSpuriousBeforeRefinement(
          refinement, f.path, ImmutableList.of(), f.blocks, f.counterexample, null);
    }
    verify(f.client, times(4)).proposeWithUsage(any(PromptMessages.class));
    verify(f.wall, times(4)).recordLlmCall(anyLong());
    assertThat(actualScheduler.getLlmCallsDone()).isEqualTo(4);
  }

  @Test
  public void disabledRepairPreservesPrimaryWithoutSpendingAnotherRequest() throws Exception {
    Fixture f = new Fixture(false);
    when(f.client.proposeWithUsage(any(PromptMessages.class)))
        .thenReturn(f.response(f.primaryJson()));
    f.run();

    verify(f.client, times(1)).proposeWithUsage(any(PromptMessages.class));
    verify(f.wall, times(1)).recordLlmCall(anyLong());
    assertThat(field(f.bridge, "lastValidation")).isEqualTo(f.primary.validation());
    assertThat(field(field(f.bridge, "pendingDump"), "rejections"))
        .isEqualTo(f.primary.rejections());
  }

  @Test
  public void repairFailureRetainsPrimaryAndDoesNotRetryRound() throws Exception {
    Fixture f = new Fixture();
    when(f.client.proposeWithUsage(any(PromptMessages.class)))
        .thenReturn(f.response(f.primaryJson()))
        .thenThrow(new IOException("offline repair failure"));
    f.run();
    assertThat(field(f.bridge, "lastValidation")).isEqualTo(f.primary.validation());
    assertThat(field(field(f.bridge, "pendingDump"), "rejections"))
        .isEqualTo(f.primary.rejections());
    assertThat(field(field(f.bridge, "pendingDump"), "llmSkipReason")).isEqualTo("repair_failed");
    verify(f.client, times(2)).proposeWithUsage(any(PromptMessages.class));
    verify(f.scheduler).recordCallCompleted();
    verify(f.wall, times(2)).recordLlmCall(anyLong());
    ArgumentCaptor<String> failureMessage = ArgumentCaptor.forClass(String.class);
    verify(f.logger)
        .logUserException(eq(Level.WARNING), any(IOException.class), failureMessage.capture());
    // core_only_records counts this stable prefix, including repair failures.
    assertThat(failureMessage.getValue()).startsWith("VGuide LLM call failed");
  }

  @Test
  public void malformedRepairRetainsPrimaryAndBothRejectionStages() throws Exception {
    Fixture f = new Fixture();
    when(f.pipeline.validateCandidates(eq(f.pack), anyList(), anyList(), any()))
        .thenAnswer(i -> i.getArgument(3));
    when(f.client.proposeWithUsage(any(PromptMessages.class)))
        .thenReturn(f.response(f.primaryJson()), f.response("{"));
    f.run();
    assertThat(field(f.bridge, "lastValidation")).isEqualTo(f.primary.validation());
    @SuppressWarnings("unchecked")
    List<CandidateRejection> rejections =
        (List<CandidateRejection>) field(field(f.bridge, "pendingDump"), "rejections");
    assertThat(rejections.stream().map(CandidateRejection::reason).toList())
        .containsExactly("variable_not_in_scope", "invalid_json")
        .inOrder();
    verify(f.client, times(2)).proposeWithUsage(any(PromptMessages.class));
  }

  @Test
  public void emptySchemaRepairSharesAllowanceAndCannotRecursivelyRepair() throws Exception {
    Fixture f = new Fixture();
    when(f.pipeline.validateCandidates(eq(f.pack), anyList(), anyList()))
        .thenReturn(
            new PredicateValidationPipeline.CandidateValidationOutcome(
                new ValidationResult(ImmutableList.of()), ImmutableList.of(), ImmutableMap.of()));
    when(f.pipeline.validateCandidates(eq(f.pack), anyList(), anyList(), any()))
        .thenAnswer(i -> i.getArgument(3));
    when(f.client.proposeWithUsage(any(PromptMessages.class)))
        .thenReturn(f.response("{"), f.response("{"));
    f.run();
    verify(f.client, times(2)).proposeWithUsage(any(PromptMessages.class));
    verify(f.scheduler).recordCallCompleted();
    assertThat(((ValidationResult) field(f.bridge, "lastValidation")).validated()).isEmpty();
  }

  @Test
  public void repairInterruptionPropagatesWithPrimaryEvidenceAndLatencyIntact() throws Exception {
    Fixture f = new Fixture();
    when(f.client.proposeWithUsage(any(PromptMessages.class)))
        .thenReturn(f.response(f.primaryJson()))
        .thenThrow(new InterruptedException("offline interrupt"));
    assertThrows(InterruptedException.class, f::run);
    assertThat(field(f.bridge, "lastValidation")).isEqualTo(f.primary.validation());
    assertThat(field(field(f.bridge, "pendingDump"), "rejections"))
        .isEqualTo(f.primary.rejections());
    verify(f.wall, times(2)).recordLlmCall(anyLong());
    verify(f.client, times(2)).proposeWithUsage(any(PromptMessages.class));
  }

  @Test
  public void noRepairForBackendOnlyFailure() throws Exception {
    Fixture f = new Fixture();
    when(f.pipeline.validateCandidates(eq(f.pack), anyList(), anyList()))
        .thenReturn(
            new PredicateValidationPipeline.CandidateValidationOutcome(
                f.primary.validation(),
                ImmutableList.of(
                    new CandidateRejection("", f.head.label(), "bad", "no_ssa_map", "missing SSA")),
                f.primary.rawStrings()));
    when(f.client.proposeWithUsage(any(PromptMessages.class)))
        .thenReturn(f.response(f.primaryJson()));
    f.run();
    verify(f.client).proposeWithUsage(any(PromptMessages.class));
    assertThat(field(f.bridge, "lastValidation")).isEqualTo(f.primary.validation());
  }

  @SuppressWarnings("unchecked")
  private static ArgumentCaptor<List<LoopHeadCandidate>> candidateCaptor() {
    return ArgumentCaptor.forClass(List.class);
  }

  private static Object field(Object object, String name) throws Exception {
    Field field = object.getClass().getDeclaredField(name);
    field.setAccessible(true);
    return field.get(object);
  }

  private static final class Fixture {
    final LogManager logger = mock(LogManager.class);
    final PredicateProposalClient client = mock(PredicateProposalClient.class);
    final PredicateValidationPipeline pipeline = mock(PredicateValidationPipeline.class);
    final WallClockBudget wall = mock(WallClockBudget.class);
    final LlmCallScheduler scheduler = mock(LlmCallScheduler.class);
    final LoopHeadInfo head = new LoopHeadInfo(CFANode.newDummyCFANode("main"), "", "main");
    final BooleanFormula formula = mock(BooleanFormula.class);
    final BlockFormulas blocks = new BlockFormulas(ImmutableList.of());
    final ContextPack pack =
        new ContextPack(
            1,
            "int x;",
            "",
            ImmutableList.of(head),
            ImmutableMap.of(),
            ImmutableSet.of(),
            blocks,
            ImmutableList.of(formula),
            "",
            "");
    final ValidatedPredicate accepted = predicate("accepted");
    final ValidatedPredicate replacement = predicate("replacement");
    final PredicateValidationPipeline.CandidateValidationOutcome primary =
        new PredicateValidationPipeline.CandidateValidationOutcome(
            new ValidationResult(ImmutableList.of(accepted)),
            ImmutableList.of(
                new CandidateRejection(
                    "",
                    head.label(),
                    "(= absent (_ bv0 32))",
                    "variable_not_in_scope",
                    "absent is not visible at this head")),
            ImmutableMap.of(accepted, "(= x (_ bv0 32))"));
    final VGuideRefinementBridge bridge;
    final ARGPath path = mock(ARGPath.class);
    final CounterexampleTraceInfo counterexample =
        CounterexampleTraceInfo.infeasible(ImmutableList.of(formula));

    Fixture() throws Exception {
      this(true);
    }

    Fixture(boolean repairEnabled) throws Exception {
      this(repairEnabled, 1);
    }

    Fixture(boolean repairEnabled, int samples) throws Exception {
      ContextPackBuilder context = mock(ContextPackBuilder.class);
      when(context.build(anyInt(), any(), any(), anyList(), anyList())).thenReturn(pack);
      when(path.asStatesList()).thenReturn(ImmutableList.<ARGState>of());
      when(wall.hasRemainingForLlm()).thenReturn(true);
      when(scheduler.shouldCall(anyInt(), anyInt())).thenReturn(true);
      when(scheduler.getLlmCallsDone()).thenReturn(0);
      when(pipeline.validateCandidates(eq(pack), anyList(), anyList())).thenReturn(primary);
      when(pipeline.validateCandidates(eq(pack), anyList(), anyList(), any()))
          .thenAnswer(
              i -> {
                var seed =
                    (PredicateValidationPipeline.CandidateValidationOutcome) i.getArgument(3);
                return new PredicateValidationPipeline.CandidateValidationOutcome(
                    new ValidationResult(ImmutableList.of(accepted, replacement)),
                    seed.rejections(),
                    ImmutableMap.of(accepted, "(= x (_ bv0 32))", replacement, "(= x (_ bv1 32))"));
              });
      VGuideOptions options =
          new VGuideOptions(
              Configuration.builder()
                  .setOption(
                      "vguide.enableValidationFeedbackRepair", Boolean.toString(repairEnabled))
                  .setOption("vguide.llmSamplesPerCall", Integer.toString(samples))
                  .setOption("vguide.minPredicatesPerCall", "1")
                  .setOption("vguide.maxPredicatesPerCall", "2")
                  .build());
      Constructor<VGuideRefinementBridge> ctor =
          VGuideRefinementBridge.class.getDeclaredConstructor(
              LogManager.class,
              VGuideOptions.class,
              PredicateProposalClient.class,
              CFA.class,
              FormulaManagerView.class,
              LoopHeadIndex.class,
              ContextPackBuilder.class,
              ProposalPromptBuilder.class,
              PredicateBudgetResolver.class,
              PredicateValidationPipeline.class,
              LoopHeadPrecisionInjector.class,
              FrozenPredicateLoader.class,
              WallClockBudget.class,
              LlmCallScheduler.class,
              CfaPrecisionCompiler.class,
              VGuideAnalysisDumper.class);
      ctor.setAccessible(true);
      LoopHeadIndex heads = new LoopHeadIndex(Optional.empty());
      bridge =
          ctor.newInstance(
              logger,
              options,
              client,
              null,
              mock(FormulaManagerView.class),
              heads,
              context,
              new ProposalPromptBuilder(heads, false),
              new PredicateBudgetResolver(),
              pipeline,
              mock(LoopHeadPrecisionInjector.class),
              mock(FrozenPredicateLoader.class),
              wall,
              scheduler,
              null,
              null);
    }

    private ValidatedPredicate predicate(String name) {
      return new ValidatedPredicate(
          mock(BooleanFormula.class, name),
          head.node(),
          ValidatedPredicate.Classification.PRECISION_ONLY,
          "",
          ImmutableList.of(),
          false,
          false);
    }

    private LlmProposalResult response(String content) {
      return new LlmProposalResult(content, "", null, 1, 1, "fixture", "fixture");
    }

    private String primaryJson() {
      return json("(= x (_ bv0 32))", "(= absent (_ bv0 32))");
    }

    private String repairJson() {
      return json("(= x (_ bv0 32))", "(= x (_ bv1 32))", "(= x (_ bv2 32))");
    }

    private String json(String... predicates) {
      return "{\"schema_version\":\"loop-head-candidate-v1\",\"candidates\":["
          + Arrays.stream(predicates)
              .map(p -> "{\"loop_head\":\"" + head.label() + "\",\"predicate\":\"" + p + "\"}")
              .collect(Collectors.joining(","))
          + "]}";
    }

    private void run() throws Exception {
      bridge.onSpuriousBeforeRefinement(1, path, ImmutableList.of(), blocks, counterexample, null);
    }
  }
}
