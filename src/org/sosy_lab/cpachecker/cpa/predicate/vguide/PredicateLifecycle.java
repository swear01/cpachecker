// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-FileCopyrightText: 2026 SSU-WEI HUANG <https://github.com/swear01>
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import com.google.common.collect.ImmutableList;
import java.util.Map;
import org.sosy_lab.cpachecker.cfa.model.CFANode;
import org.sosy_lab.cpachecker.cpa.predicate.PredicatePrecision;
import org.sosy_lab.cpachecker.util.predicates.AbstractionPredicate;

/** Replaces, rather than accumulates, the predicates owned by the preceding model round. */
final class PredicateLifecycle {

  private PredicatePrecision owned = PredicatePrecision.empty();

  PredicatePrecision nativeOnly(PredicatePrecision precision) {
    return (PredicatePrecision) precision.subtract(owned);
  }

  Replacement beginReplacement(Iterable<Map.Entry<CFANode, AbstractionPredicate>> replacements) {
    ImmutableList<Map.Entry<CFANode, AbstractionPredicate>> replacementList =
        ImmutableList.copyOf(replacements);
    PredicatePrecision previous = owned;
    PredicatePrecision next = PredicatePrecision.empty().addLocalPredicates(replacementList);
    owned = next;
    return new Replacement(previous, next);
  }

  PredicatePrecision owned() {
    return owned;
  }

  record Replacement(PredicatePrecision previous, PredicatePrecision next) {

    PredicatePrecision apply(PredicatePrecision precision) {
      return ((PredicatePrecision) precision.subtract(previous)).mergeWith(next);
    }
  }
}
