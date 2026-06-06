// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.truth.Truth.assertThat;

import org.junit.Test;

public class PredicateContractValidatorTest {

  @Test
  public void acceptsSimpleRelationalPredicate() {
    assertThat(PredicateContractValidator.isValid("(= i j)")).isTrue();
  }

  @Test
  public void rejectsInternalSsaPipeName() {
    assertThat(PredicateContractValidator.isValid("(= |main::i@1| j)")).isFalse();
  }

  @Test
  public void rejectsBareSsaAtSuffix() {
    assertThat(PredicateContractValidator.isValid("(= i@3 j)")).isFalse();
  }

  @Test
  public void rejectsSelectStore() {
    assertThat(PredicateContractValidator.isValid("(select a i)")).isFalse();
    assertThat(PredicateContractValidator.isValid("(store a i v)")).isFalse();
  }

  @Test
  public void rejectsCArraySubscriptSyntax() {
    assertThat(PredicateContractValidator.isValid("(= A[i] 0)")).isFalse();
  }

  @Test
  public void rejectsEmptyOrNonSexp() {
    assertThat(PredicateContractValidator.isValid("")).isFalse();
    assertThat(PredicateContractValidator.isValid("i >= 0")).isFalse();
  }
}
