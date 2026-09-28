// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import com.google.common.base.Predicates;
import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableSet;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.logging.Level;
import org.sosy_lab.common.log.LogManager;
import org.sosy_lab.cpachecker.cfa.model.CFANode;
import org.sosy_lab.cpachecker.cpa.arg.ARGReachedSet;
import org.sosy_lab.cpachecker.cpa.predicate.PredicateAbstractionManager;
import org.sosy_lab.cpachecker.cpa.predicate.PredicatePrecision;
import org.sosy_lab.cpachecker.cpa.predicate.VocabularyGuide;
import org.sosy_lab.cpachecker.util.predicates.AbstractionPredicate;
import org.sosy_lab.java_smt.api.BooleanFormula;

/** Injects validated predicates as local precision at loop heads only. */
public final class LoopHeadPrecisionInjector {

  public record PreparedInjection(
      PredicatePrecision precision,
      ImmutableList<ValidatedPredicate> predicates,
      ImmutableList<AbstractionPredicate> abstractions) {}

  private record ResolvedInjection(
      ImmutableList<Map.Entry<CFANode, AbstractionPredicate>> entries,
      ImmutableList<ValidatedPredicate> predicates,
      ImmutableList<AbstractionPredicate> abstractions) {}

  private final LogManager logger;
  private final PredicateAbstractionManager predAbsManager;

  public LoopHeadPrecisionInjector(LogManager logger, PredicateAbstractionManager predAbsManager) {
    this.logger = logger;
    this.predAbsManager = predAbsManager;
  }

  public PredicatePrecision mergePreCegarInto(
      PredicatePrecision base, List<ValidatedPredicate> preds) {
    if (preds.isEmpty() || predAbsManager == null) {
      return base;
    }
    List<Map.Entry<CFANode, AbstractionPredicate>> entries = new ArrayList<>();
    Set<Map.Entry<CFANode, BooleanFormula>> seen = new LinkedHashSet<>();
    for (ValidatedPredicate vp : preds) {
      var key = Map.entry(vp.loopHeadNode(), vp.formula());
      if (!seen.add(key)) {
        continue;
      }
      try {
        entries.add(Map.entry(vp.loopHeadNode(), predAbsManager.getPredicateFor(vp.formula())));
      } catch (Exception e) {
        logger.logDebugException(e, "VGuide source-prior AbstractionPredicate failed");
      }
    }
    if (entries.isEmpty()) {
      return base;
    }
    PredicatePrecision merged = base.addLocalPredicates(entries);
    logger.log(
        Level.INFO,
        "VGuide source-prior merged ",
        entries.size(),
        " predicates into initial precision");
    return merged;
  }

  public ImmutableList<ValidatedPredicate> inject(
      ARGReachedSet reached,
      List<ValidatedPredicate> precisionPredicates,
      boolean enableDiagnostics) {
    ResolvedInjection resolved = resolve(precisionPredicates);
    if (resolved.predicates().isEmpty()) {
      return ImmutableList.of();
    }
    PredicatePrecision currentPredPrec =
        PredicatePrecision.unionOf(ImmutableSet.copyOf(reached.asReachedSet().getPrecisions()));
    PreparedInjection prepared = prepare(currentPredPrec, resolved);
    reached.updatePrecisionGlobally(
        prepared.precision(), Predicates.instanceOf(PredicatePrecision.class));
    if (enableDiagnostics) {
      predAbsManager.enableVGuidePredicateDiagnostics(prepared.abstractions());
    }
    logger.log(
        Level.INFO, "VGuide precision-injected ", prepared.predicates().size(), " local predicates");
    return prepared.predicates();
  }

  /** Prepares only predicates not already available at their recovery head. */
  public PreparedInjection prepareForRecovery(
      PredicatePrecision base, List<ValidatedPredicate> precisionPredicates) {
    ResolvedInjection resolved = resolve(precisionPredicates);
    if (resolved.predicates().isEmpty()) {
      return new PreparedInjection(base, ImmutableList.of(), ImmutableList.of());
    }
    ImmutableList.Builder<Map.Entry<CFANode, AbstractionPredicate>> entries =
        ImmutableList.builder();
    ImmutableList.Builder<ValidatedPredicate> predicates = ImmutableList.builder();
    ImmutableList.Builder<AbstractionPredicate> abstractions = ImmutableList.builder();
    for (int i = 0; i < resolved.predicates().size(); i++) {
      ValidatedPredicate predicate = resolved.predicates().get(i);
      AbstractionPredicate abstraction = resolved.abstractions().get(i);
      if (isAvailableAtHead(base, predicate.loopHeadNode(), abstraction)) {
        continue;
      }
      entries.add(resolved.entries().get(i));
      predicates.add(predicate);
      abstractions.add(abstraction);
    }
    return prepare(
        base, new ResolvedInjection(entries.build(), predicates.build(), abstractions.build()));
  }

  private PreparedInjection prepare(PredicatePrecision base, ResolvedInjection resolved) {
    if (resolved.predicates().isEmpty()) {
      return new PreparedInjection(base, ImmutableList.of(), ImmutableList.of());
    }
    return new PreparedInjection(
        base.addLocalPredicates(resolved.entries()), resolved.predicates(), resolved.abstractions());
  }

  private static boolean isAvailableAtHead(
      PredicatePrecision precision, CFANode head, AbstractionPredicate predicate) {
    return precision.getGlobalPredicates().contains(predicate)
        || precision.getFunctionPredicates().get(head.getFunctionName()).contains(predicate)
        || precision.getLocalPredicates().get(head).contains(predicate);
  }

  private ResolvedInjection resolve(List<ValidatedPredicate> precisionPredicates) {
    if (precisionPredicates.isEmpty() || predAbsManager == null) {
      return new ResolvedInjection(ImmutableList.of(), ImmutableList.of(), ImmutableList.of());
    }
    List<Map.Entry<CFANode, AbstractionPredicate>> entries = new ArrayList<>();
    Set<Map.Entry<CFANode, BooleanFormula>> seen = new LinkedHashSet<>();
    ImmutableList.Builder<ValidatedPredicate> injected = ImmutableList.builder();
    for (ValidatedPredicate vp : precisionPredicates) {
      if (vp.classification() != ValidatedPredicate.Classification.PRECISION_ONLY) {
        continue;
      }
      var key = Map.entry(vp.loopHeadNode(), vp.formula());
      if (!seen.add(key)) {
        continue;
      }
      try {
        entries.add(Map.entry(vp.loopHeadNode(), predAbsManager.getPredicateFor(vp.formula())));
        injected.add(vp);
      } catch (Exception e) {
        logger.logDebugException(e, "VGuide AbstractionPredicate failed");
      }
    }

    if (entries.isEmpty()) {
      return new ResolvedInjection(ImmutableList.of(), ImmutableList.of(), ImmutableList.of());
    }
    return new ResolvedInjection(
        ImmutableList.copyOf(entries),
        injected.build(),
        entries.stream().map(Map.Entry::getValue).collect(ImmutableList.toImmutableList()));
  }

  public void enableDiagnostics(PreparedInjection prepared) {
    if (predAbsManager != null && !prepared.abstractions().isEmpty()) {
      predAbsManager.enableVGuidePredicateDiagnostics(prepared.abstractions());
    }
  }

  public void injectFrozen(
      ARGReachedSet reached,
      List<LoopHeadInfo> loopHeads,
      List<String> predicateTexts,
      org.sosy_lab.cpachecker.util.predicates.smt.FormulaManagerView fmgr) {
    if (predAbsManager == null || loopHeads.isEmpty() || predicateTexts.isEmpty()) {
      return;
    }
    List<Map.Entry<CFANode, AbstractionPredicate>> entries = new ArrayList<>();
    for (LoopHeadInfo head : loopHeads) {
      for (String text : predicateTexts) {
        BooleanFormula f = VocabularyGuide.parsePredicate(text, fmgr, ImmutableSet.of());
        if (f == null) {
          continue;
        }
        try {
          entries.add(Map.entry(head.node(), predAbsManager.getPredicateFor(f)));
        } catch (Exception e) {
          logger.logDebugException(e, "VGuide frozen predicate failed");
        }
      }
    }
    if (entries.isEmpty()) {
      return;
    }
    PredicatePrecision currentPredPrec =
        PredicatePrecision.unionOf(ImmutableSet.copyOf(reached.asReachedSet().getPrecisions()));
    PredicatePrecision newPredPrec = currentPredPrec.addLocalPredicates(entries);
    reached.updatePrecisionGlobally(newPredPrec, Predicates.instanceOf(PredicatePrecision.class));
    logger.log(Level.INFO, "VGuide FROZEN_SEED injected ", entries.size(), " predicates");
  }
}
