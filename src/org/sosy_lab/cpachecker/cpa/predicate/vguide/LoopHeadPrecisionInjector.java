// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import com.google.common.base.Predicates;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.logging.Level;
import org.sosy_lab.common.log.LogManager;
import org.sosy_lab.cpachecker.core.interfaces.AbstractState;
import org.sosy_lab.cpachecker.core.interfaces.Precision;
import org.sosy_lab.cpachecker.cpa.arg.ARGReachedSet;
import org.sosy_lab.cpachecker.cpa.predicate.PredicateAbstractionManager;
import org.sosy_lab.cpachecker.cpa.predicate.PredicatePrecision;
import org.sosy_lab.cpachecker.cpa.predicate.VocabularyGuide;
import org.sosy_lab.cpachecker.util.Precisions;
import org.sosy_lab.cpachecker.util.predicates.AbstractionPredicate;
import org.sosy_lab.java_smt.api.BooleanFormula;

/** Injects validated predicates as local precision at loop heads only. */
public final class LoopHeadPrecisionInjector {

  private final LogManager logger;
  private final PredicateAbstractionManager predAbsManager;

  public LoopHeadPrecisionInjector(
      LogManager logger, PredicateAbstractionManager predAbsManager) {
    this.logger = logger;
    this.predAbsManager = predAbsManager;
  }

  public boolean inject(
      ARGReachedSet reached, List<ValidatedPredicate> precisionPredicates) {
    if (precisionPredicates.isEmpty() || predAbsManager == null) {
      return false;
    }
    AbstractState firstState = reached.asReachedSet().getFirstState();
    if (firstState == null) {
      return false;
    }
    Precision currentPrec = reached.asReachedSet().getPrecision(firstState);
    PredicatePrecision currentPredPrec =
        Precisions.extractPrecisionByType(currentPrec, PredicatePrecision.class);
    if (currentPredPrec == null) {
      return false;
    }

    List<Map.Entry<org.sosy_lab.cpachecker.cfa.model.CFANode, AbstractionPredicate>> entries =
        new ArrayList<>();
    Set<String> seen = new LinkedHashSet<>();
    for (ValidatedPredicate vp : precisionPredicates) {
      if (vp.classification() != ValidatedPredicate.Classification.PRECISION_ONLY) {
        continue;
      }
      String key = vp.loopHeadNode().getNodeNumber() + ":" + vp.formula().hashCode();
      if (!seen.add(key)) {
        continue;
      }
      try {
        entries.add(Map.entry(vp.loopHeadNode(), predAbsManager.getPredicateFor(vp.formula())));
      } catch (Exception e) {
        logger.logDebugException(e, "VGuide AbstractionPredicate failed");
      }
    }

    if (entries.isEmpty()) {
      return false;
    }

    PredicatePrecision newPredPrec = currentPredPrec.addLocalPredicates(entries);
    reached.updatePrecisionGlobally(newPredPrec, Predicates.instanceOf(PredicatePrecision.class));
    logger.log(Level.INFO, "VGuide precision-injected ", entries.size(), " local predicates");
    return true;
  }

  public void injectFrozen(
      ARGReachedSet reached,
      List<LoopHeadInfo> loopHeads,
      List<String> predicateTexts,
      org.sosy_lab.cpachecker.util.predicates.smt.FormulaManagerView fmgr) {
    if (predAbsManager == null || loopHeads.isEmpty() || predicateTexts.isEmpty()) {
      return;
    }
    List<Map.Entry<org.sosy_lab.cpachecker.cfa.model.CFANode, AbstractionPredicate>> entries =
        new ArrayList<>();
    for (LoopHeadInfo head : loopHeads) {
      for (String text : predicateTexts) {
        BooleanFormula f = VocabularyGuide.parsePredicate(text, fmgr, Set.of());
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
    AbstractState firstState = reached.asReachedSet().getFirstState();
    if (firstState == null) {
      return;
    }
    Precision currentPrec = reached.asReachedSet().getPrecision(firstState);
    PredicatePrecision currentPredPrec =
        Precisions.extractPrecisionByType(currentPrec, PredicatePrecision.class);
    if (currentPredPrec == null) {
      return;
    }
    PredicatePrecision newPredPrec = currentPredPrec.addLocalPredicates(entries);
    reached.updatePrecisionGlobally(newPredPrec, Predicates.instanceOf(PredicatePrecision.class));
    logger.log(Level.INFO, "VGuide FROZEN_SEED injected ", entries.size(), " predicates");
  }
}
