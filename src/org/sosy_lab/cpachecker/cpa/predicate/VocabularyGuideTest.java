// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-FileCopyrightText: 2007-2020 Dirk Beyer <https://www.sosy-lab.org>
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate;

import static com.google.common.truth.Truth.assertThat;

import java.util.List;
import org.junit.Test;
import org.sosy_lab.common.log.LogManager;
import org.sosy_lab.cpachecker.util.predicates.smt.BooleanFormulaManagerView;
import org.sosy_lab.cpachecker.util.predicates.smt.IntegerFormulaManagerView;
import org.sosy_lab.cpachecker.util.predicates.smt.SolverViewBasedTest0;
import org.sosy_lab.java_smt.api.BooleanFormula;

public class VocabularyGuideTest extends SolverViewBasedTest0 {

  private VocabularyGuide create() {
    return new VocabularyGuide(solver, LogManager.createTestLogManager());
  }

  @Test
  public void isEmpty_byDefault() {
    assertThat(create().isEmpty()).isTrue();
  }

  @Test
  public void addPredicateWithLocation_retrievableByLocation() {
    VocabularyGuide vg = create();
    vg.addPredicate("loop L1", "i >= 0", 0);
    vg.addPredicate("loop L1", "i < n", 0);
    vg.addPredicate("function foo", "x != NULL", 0);

    assertThat(vg.size()).isEqualTo(3);
    assertThat(vg.isEmpty()).isFalse();

    List<String> l1Preds = vg.getPredicateStringsForLocation("loop L1");
    assertThat(l1Preds).containsExactly("i >= 0", "i < n");

    List<String> fooPreds = vg.getPredicateStringsForLocation("function foo");
    assertThat(fooPreds).containsExactly("x != NULL");

    List<String> missingPreds = vg.getPredicateStringsForLocation("nonexistent");
    assertThat(missingPreds).isEmpty();
  }

  @Test
  public void addPredicates_withSameLocation_appendsNotReplaces() {
    VocabularyGuide vg = create();
    vg.addPredicate("loop L1", "i >= 0", 0);
    vg.addPredicate("loop L1", "i >= 0", 0);
    vg.addPredicate("loop L1", "i < n", 0);

    assertThat(vg.size()).isEqualTo(2);
  }

  @Test
  public void removePredicates_removesByLocationAndText() {
    VocabularyGuide vg = create();
    vg.addPredicate("loop L1", "i >= 0", 0);
    vg.addPredicate("loop L1", "i < n", 0);
    vg.addPredicate("function foo", "x != NULL", 0);

    vg.removePredicate("loop L1", "i < n");
    assertThat(vg.size()).isEqualTo(2);
    assertThat(vg.getPredicateStringsForLocation("loop L1")).containsExactly("i >= 0");
  }

  @Test
  public void getAllLocations_returnsUniqueLocationsSorted() {
    VocabularyGuide vg = create();
    vg.addPredicate("loop L1", "i >= 0", 0);
    vg.addPredicate("loop L1", "i < n", 0);
    vg.addPredicate("function foo", "x != NULL", 0);
    vg.addPredicate("loop L2", "j > 0", 0);

    assertThat(vg.getAllLocations()).containsExactly("function foo", "loop L1", "loop L2");
  }

  @Test
  public void addPredicateBatch_addsMultipleForSameLocation() {
    VocabularyGuide vg = create();
    vg.addPredicates("loop L1", List.of("i >= 0", "i < n", "sum == 0"));

    assertThat(vg.size()).isEqualTo(3);
    assertThat(vg.getPredicateStringsForLocation("loop L1"))
        .containsExactly("i >= 0", "i < n", "sum == 0");
  }

  @Test
  public void clearAll_emptiesVocabulary() {
    VocabularyGuide vg = create();
    vg.addPredicate("loop L1", "i >= 0", 0);
    vg.clearAll();

    assertThat(vg.isEmpty()).isTrue();
    assertThat(vg.size()).isEqualTo(0);
  }

  @Test
  public void hasVariableOverlap_withSolver() {
    VocabularyGuide vg = create();
    vg.addPredicate("loop L1", "i >= n", 0);
    vg.addPredicate("loop L2", "j > 10", 0);

    BooleanFormulaManagerView bfmgrv = bmgrv;
    IntegerFormulaManagerView ifmgrv = imgrv;

    assertThat(vg.hasVariableOverlap(parse("i >= 0", bfmgrv, ifmgrv))).isTrue();
    assertThat(vg.hasVariableOverlap(parse("k < 5", bfmgrv, ifmgrv))).isFalse();
    assertThat(vg.hasVariableOverlap(parse("i > j", bfmgrv, ifmgrv))).isTrue();
    assertThat(vg.getVariableNames()).containsExactly("i", "j", "n");
  }

  private static BooleanFormula parse(
      String expr,
      BooleanFormulaManagerView bfmgr,
      IntegerFormulaManagerView ifmgr) {
    return VocabularyGuide.parsePredicate(expr, bfmgr, ifmgr);
  }
}
