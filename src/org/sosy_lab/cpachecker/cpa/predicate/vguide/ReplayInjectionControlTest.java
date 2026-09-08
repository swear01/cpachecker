// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.truth.Truth.assertThat;
import static org.junit.Assert.assertThrows;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.RETURNS_DEEP_STUBS;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoMoreInteractions;

import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableMap;
import com.google.common.collect.ImmutableSet;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.util.Map;
import org.junit.Test;
import org.mockito.ArgumentCaptor;
import org.sosy_lab.common.configuration.Configuration;
import org.sosy_lab.common.log.LogManager;
import org.sosy_lab.cpachecker.cfa.CFA;
import org.sosy_lab.cpachecker.cfa.model.CFANode;
import org.sosy_lab.cpachecker.cpa.arg.ARGReachedSet;
import org.sosy_lab.cpachecker.util.predicates.smt.FormulaManagerView;
import org.sosy_lab.cpachecker.util.predicates.smt.SolverViewBasedTest0;
import org.sosy_lab.java_smt.api.BooleanFormula;

public class ReplayInjectionControlTest extends SolverViewBasedTest0 {

  @Test
  public void fullReturnsValidatedPrecisionWithoutSelectorWork() {
    ValidatedPredicate first = predicate("first");
    ValidatedPredicate second = predicate("second");
    ValidationResult validation = new ValidationResult(ImmutableList.of(first, second));

    assertThat(
            VGuideRefinementBridge.selectReplayPredicates(
                VGuideOptions.ReplayInjectionMode.FULL,
                ImmutableSet.of("not parsed"),
                validation,
                ImmutableMap.of(),
                ImmutableMap.of(),
                this::canonical))
        .containsExactly(first, second);
  }

  @Test
  public void suppressAllRetainsValidationButSelectsNothing() {
    ValidatedPredicate first = predicate("first");
    ValidationResult validation = new ValidationResult(ImmutableList.of(first));

    assertThat(
            VGuideRefinementBridge.selectReplayPredicates(
                VGuideOptions.ReplayInjectionMode.SUPPRESS_ALL,
                ImmutableSet.of(),
                validation,
                ImmutableMap.of(),
                ImmutableMap.of(),
                this::canonical))
        .isEmpty();
    assertThat(validation.validated()).containsExactly(first);
  }

  @Test
  public void excludeUsesExactHeadFormulaAndProvenanceAndKeepsOtherBindings() {
    ValidatedPredicate excluded = predicate("excluded");
    ValidatedPredicate retained = predicate("retained");
    ValidationResult validation = new ValidationResult(ImmutableList.of(excluded, retained));
    var raw = ImmutableMap.of(excluded, "excluded-raw", retained, "retained-raw");
    var profiles = ImmutableMap.of("excluded-raw", "SAFE", "retained-raw", "SAFE");
    String selector =
        "head=N"
            + excluded.loopHeadNode().getNodeNumber()
            + ";formula="
            + canonical(excluded.formula())
            + ";provenance=SAFE";

    assertThat(
            VGuideRefinementBridge.selectReplayPredicates(
                VGuideOptions.ReplayInjectionMode.EXCLUDE,
                ImmutableSet.of(selector),
                validation,
                raw,
                profiles,
                this::canonical))
        .containsExactly(retained);
  }

  @Test
  public void unknownSelectorFailsClosed() {
    ValidatedPredicate first = predicate("first");
    ValidationResult validation = new ValidationResult(ImmutableList.of(first));
    var raw = ImmutableMap.of(first, "first-raw");
    var profiles = ImmutableMap.of("first-raw", "SAFE");
    assertThrows(
        IllegalStateException.class,
        () ->
            VGuideRefinementBridge.selectReplayPredicates(
                VGuideOptions.ReplayInjectionMode.EXCLUDE,
                ImmutableSet.of("head=N999;formula=unknown;provenance=SAFE"),
                validation,
                raw,
                profiles,
            this::canonical));
  }

  @Test
  public void productionRouteRetainsValidationAndAccumulatesReplaySelections() throws Exception {
    ValidatedPredicate first = predicate("first");
    ValidatedPredicate second = predicate("second");
    String firstSelector = selector(first, "SAFE");

    VGuideRefinementBridge full = bridge(VGuideOptions.ReplayInjectionMode.FULL, ImmutableSet.of());
    setValidation(full, ImmutableList.of(first, second), ImmutableMap.of(first, "first-raw", second, "second-raw"));
    setPendingDump(full, 1);
    full.onSpuriousAfterRefinement(1, mock(ARGReachedSet.class, RETURNS_DEEP_STUBS));
    assertInjected(full, ImmutableList.of(first, second));
    assertOutcome(full, "validated=2 injected=2");

    VGuideRefinementBridge suppressed =
        bridge(VGuideOptions.ReplayInjectionMode.SUPPRESS_ALL, ImmutableSet.of());
    setValidation(
        suppressed,
        ImmutableList.of(first, second),
        ImmutableMap.of(first, "first-raw", second, "second-raw"));
    setPendingDump(suppressed, 1);
    suppressed.onSpuriousAfterRefinement(1, mock(ARGReachedSet.class, RETURNS_DEEP_STUBS));
    assertInjected(suppressed, ImmutableList.of());
    assertOutcome(suppressed, "validated=2 injected=0");

    VGuideRefinementBridge subset =
        bridge(VGuideOptions.ReplayInjectionMode.EXCLUDE, ImmutableSet.of(firstSelector));
    setValidation(subset, ImmutableList.of(first), ImmutableMap.of(first, "first-raw"));
    setPendingDump(subset, 1);
    subset.onSpuriousAfterRefinement(1, mock(ARGReachedSet.class, RETURNS_DEEP_STUBS));
    setValidation(subset, ImmutableList.of(second), ImmutableMap.of(second, "second-raw"));
    setPendingDump(subset, 2);
    subset.onSpuriousAfterRefinement(2, mock(ARGReachedSet.class, RETURNS_DEEP_STUBS));
    subset.onAnalysisEnd(2, org.sosy_lab.cpachecker.core.CPAcheckerResult.Result.TRUE, null);
    assertInjected(subset, ImmutableList.of(), ImmutableList.of(second));
    assertOutcome(subset, "validated=1 injected=1");
  }

  @Test
  public void productionRouteRejectsUnknownSelectorAtAnalysisEnd() throws Exception {
    VGuideRefinementBridge bridge =
        bridge(
            VGuideOptions.ReplayInjectionMode.EXCLUDE,
            ImmutableSet.of("head=N999;formula=unknown;provenance=SAFE"));
    ValidatedPredicate first = predicate("first");
    setValidation(bridge, ImmutableList.of(first), ImmutableMap.of(first, "first-raw"));
    bridge.onSpuriousAfterRefinement(1, mock(ARGReachedSet.class));
    assertThrows(
        IllegalStateException.class,
        () ->
            bridge.onAnalysisEnd(
                1, org.sosy_lab.cpachecker.core.CPAcheckerResult.Result.TRUE, null));
  }

  private VGuideRefinementBridge bridge(
      VGuideOptions.ReplayInjectionMode mode, ImmutableSet<String> selectors) throws Exception {
    VGuideOptions options = new VGuideOptions(Configuration.defaultConfiguration());
    set(options, "replayInjectionMode", mode);
    set(options, "parsedReplayInjectionSelectors", ImmutableList.copyOf(selectors));
    set(options, "replayInjectionSelectorSet", selectors);
    Constructor<VGuideRefinementBridge> constructor =
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
    constructor.setAccessible(true);
    return constructor.newInstance(
        LogManager.createTestLogManager(),
        options,
        null,
        null,
        mgrv,
        mock(LoopHeadIndex.class),
        mock(ContextPackBuilder.class),
        mock(ProposalPromptBuilder.class),
        mock(PredicateBudgetResolver.class),
        mock(PredicateValidationPipeline.class),
        mock(LoopHeadPrecisionInjector.class),
        mock(FrozenPredicateLoader.class),
        mock(WallClockBudget.class),
        mock(LlmCallScheduler.class),
        null,
        null);
  }

  private void setValidation(
      VGuideRefinementBridge bridge,
      ImmutableList<ValidatedPredicate> predicates,
      Map<ValidatedPredicate, String> rawStrings)
      throws Exception {
    set(bridge, "lastValidation", new ValidationResult(predicates));
    set(bridge, "lastRawStrings", rawStrings);
    set(bridge, "lastProfiles", ImmutableMap.of("first-raw", "SAFE", "second-raw", "SAFE"));
  }

  private void setPendingDump(VGuideRefinementBridge bridge, int refinementIndex) throws Exception {
    Class<?> dumpClass =
        Class.forName(
            "org.sosy_lab.cpachecker.cpa.predicate.vguide.VGuideRefinementBridge$PendingRefinementDump");
    Constructor<?> dumpConstructor = dumpClass.getDeclaredConstructor();
    dumpConstructor.setAccessible(true);
    Object dump = dumpConstructor.newInstance();
    set(dump, "refinementIndex", refinementIndex);
    set(dump, "precisionBeforeSnapshot", ImmutableSet.of());
    set(bridge, "pendingDump", dump);
    RefinementOutcomeStore store = (RefinementOutcomeStore) get(bridge, "refinementOutcomeStore");
    store.recordStarted(refinementIndex, 0, 0, 0);
  }

  private void assertOutcome(VGuideRefinementBridge bridge, String expected) throws Exception {
    RefinementOutcomeStore store = (RefinementOutcomeStore) get(bridge, "refinementOutcomeStore");
    assertThat(store.buildContext()).contains(expected);
  }

  @SuppressWarnings("unchecked")
  private void assertInjected(
      VGuideRefinementBridge bridge,
      ImmutableList<ValidatedPredicate> firstExpected,
      ImmutableList<ValidatedPredicate> secondExpected)
      throws Exception {
    LoopHeadPrecisionInjector injector = (LoopHeadPrecisionInjector) get(bridge, "precisionInjector");
    ArgumentCaptor<ImmutableList<ValidatedPredicate>> captor = ArgumentCaptor.forClass(ImmutableList.class);
    verify(injector, org.mockito.Mockito.times(2)).inject(org.mockito.Mockito.any(), captor.capture());
    assertThat(captor.getAllValues().get(0)).containsExactlyElementsIn(firstExpected);
    assertThat(captor.getAllValues().get(1)).containsExactlyElementsIn(secondExpected);
    verifyNoMoreInteractions(injector);
  }

  @SuppressWarnings("unchecked")
  private void assertInjected(VGuideRefinementBridge bridge, ImmutableList<ValidatedPredicate> expected)
      throws Exception {
    LoopHeadPrecisionInjector injector = (LoopHeadPrecisionInjector) get(bridge, "precisionInjector");
    ArgumentCaptor<ImmutableList<ValidatedPredicate>> captor = ArgumentCaptor.forClass(ImmutableList.class);
    verify(injector).inject(org.mockito.Mockito.any(), captor.capture());
    assertThat(captor.getValue()).containsExactlyElementsIn(expected);
    verifyNoMoreInteractions(injector);
  }

  private String selector(ValidatedPredicate predicate, String profile) {
    return "head=N"
        + predicate.loopHeadNode().getNodeNumber()
        + ";formula="
        + canonical(predicate.formula())
        + ";provenance="
        + profile;
  }

  private static Object get(Object target, String name) throws Exception {
    Field field = target.getClass().getDeclaredField(name);
    field.setAccessible(true);
    return field.get(target);
  }

  private static void set(Object target, String name, Object value) throws Exception {
    Field field = target.getClass().getDeclaredField(name);
    field.setAccessible(true);
    field.set(target, value);
  }

  private ValidatedPredicate predicate(String name) {
    CFANode head = CFANode.newDummyCFANode("main");
    return new ValidatedPredicate(
        bmgrv.makeVariable(name),
        head,
        ValidatedPredicate.Classification.PRECISION_ONLY,
        "candidate",
        ImmutableList.of(name),
        false,
        false);
  }

  private String canonical(BooleanFormula formula) {
    return mgrv.dumpFormula(formula).toString().replace('\n', ' ');
  }
}
