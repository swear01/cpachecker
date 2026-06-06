// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.truth.Truth.assertThat;

import com.google.common.collect.ImmutableSet;
import org.junit.Test;

public class VarContractBuilderTest {

  @Test
  public void mapsSourceNamesToEncodedSsa() {
    var contract =
        VarContractBuilder.build(
            ImmutableSet.of("|main::i@2|", "|main::n@1|", "unrelated"));
    assertThat(contract).containsKey("i");
    assertThat(contract.get("i")).containsExactly("|main::i@2|");
    assertThat(contract.get("n")).containsExactly("|main::n@1|");
    assertThat(contract).doesNotContainKey("unrelated");
  }
}
