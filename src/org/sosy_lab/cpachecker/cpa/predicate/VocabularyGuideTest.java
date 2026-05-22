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

public class VocabularyGuideTest {

  private static VocabularyGuide createEmpty() {
    return new VocabularyGuide(null, LogManager.createTestLogManager());
  }

  @Test
  public void isEmpty_byDefault() {
    assertThat(createEmpty().isEmpty()).isTrue();
  }

  @Test
  public void addPredicateWithLocation_retrievableByLocation() {
    VocabularyGuide vg = createEmpty();
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
    VocabularyGuide vg = createEmpty();
    vg.addPredicate("loop L1", "i >= 0", 0);
    vg.addPredicate("loop L1", "i >= 0", 0); // duplicate: should be ignored
    vg.addPredicate("loop L1", "i < n", 0);

    assertThat(vg.size()).isEqualTo(2);
  }

  @Test
  public void removePredicates_removesByLocationAndText() {
    VocabularyGuide vg = createEmpty();
    vg.addPredicate("loop L1", "i >= 0", 0);
    vg.addPredicate("loop L1", "i < n", 0);
    vg.addPredicate("function foo", "x != NULL", 0);

    vg.removePredicate("loop L1", "i < n");
    assertThat(vg.size()).isEqualTo(2);
    assertThat(vg.getPredicateStringsForLocation("loop L1")).containsExactly("i >= 0");
  }

  @Test
  public void getAllLocations_returnsUniqueLocationsSorted() {
    VocabularyGuide vg = createEmpty();
    vg.addPredicate("loop L1", "i >= 0", 0);
    vg.addPredicate("loop L1", "i < n", 0);
    vg.addPredicate("function foo", "x != NULL", 0);
    vg.addPredicate("loop L2", "j > 0", 0);

    assertThat(vg.getAllLocations()).containsExactly("function foo", "loop L1", "loop L2");
  }

  @Test
  public void addPredicateBatch_addsMultipleForSameLocation() {
    VocabularyGuide vg = createEmpty();
    vg.addPredicates("loop L1", List.of("i >= 0", "i < n", "sum == 0"));

    assertThat(vg.size()).isEqualTo(3);
    assertThat(vg.getPredicateStringsForLocation("loop L1"))
        .containsExactly("i >= 0", "i < n", "sum == 0");
  }

  @Test
  public void clearAll_emptiesVocabulary() {
    VocabularyGuide vg = createEmpty();
    vg.addPredicate("loop L1", "i >= 0", 0);
    vg.clearAll();

    assertThat(vg.isEmpty()).isTrue();
    assertThat(vg.size()).isEqualTo(0);
  }

  @Test
  public void hasVariableOverlap_checksPredicateVariables() {
    VocabularyGuide vg = createEmpty();
    vg.addPredicate("loop L1", "i >= n", 0);
    vg.addPredicate("loop L2", "j > 10", 0);

    assertThat(vg.hasVariableOverlap("i >= 0")).isTrue();
    assertThat(vg.hasVariableOverlap("k < 5")).isFalse();
    assertThat(vg.hasVariableOverlap("i > j")).isTrue();
    assertThat(vg.getVariableNames()).containsExactly("i", "n", "j");
  }
}
