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
  public void allowsBareSsaAtSuffixForTranslator() {
    // Issue #70: leaked SSA versions are stripped by ArrayTermTranslator.
    assertThat(PredicateContractValidator.isValid("(= i@3 j)")).isTrue();
  }

  @Test
  public void allowsSelectStoreForTranslator() {
    // Issue #60: select/store are allowed at the contract level; the ArrayTermTranslator
    // owns the (c i) -> select translation and the parser types the heap variable.
    assertThat(PredicateContractValidator.isValid("(select a i)")).isTrue();
    assertThat(PredicateContractValidator.isValid("(store a i v)")).isTrue();
  }

  @Test
  public void allowsCSyntaxArraySubscripts() {
    // Issue #68: C-syntax array reads are translated by ArrayTermTranslator.
    assertThat(PredicateContractValidator.isValid("(= A[i] 0)")).isTrue();
  }

  @Test
  public void allowsVersionedSsaNamesForTranslator() {
    // Issue #70: leaked SSA versions are stripped by ArrayTermTranslator.
    assertThat(PredicateContractValidator.isValid("(= main::x@3 (_ bv0 32))")).isTrue();
  }

  @Test
  public void rejectsEmptyOrNonSexp() {
    assertThat(PredicateContractValidator.isValid("")).isFalse();
    assertThat(PredicateContractValidator.isValid("i >= 0")).isFalse();
  }
}
