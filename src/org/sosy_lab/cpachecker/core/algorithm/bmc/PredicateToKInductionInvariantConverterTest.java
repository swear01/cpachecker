// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-FileCopyrightText: 2026 Dirk Beyer <https://www.sosy-lab.org>
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.core.algorithm.bmc;

import static com.google.common.truth.Truth.assertThat;

import com.google.common.collect.ImmutableSet;
import org.junit.Test;
import org.sosy_lab.cpachecker.cfa.model.CFANode;
import org.sosy_lab.cpachecker.core.algorithm.bmc.candidateinvariants.CandidateInvariant;
import org.sosy_lab.cpachecker.core.algorithm.bmc.candidateinvariants.SingleLocationFormulaInvariant;

public class PredicateToKInductionInvariantConverterTest {

  @Test
  public void combinesCandidatesAtEachLocation() {
    CFANode firstLocation = CFANode.newDummyCFANode("first");
    CFANode secondLocation = CFANode.newDummyCFANode("second");
    CandidateInvariant first =
        SingleLocationFormulaInvariant.makeBooleanInvariant(firstLocation, true);
    CandidateInvariant second =
        SingleLocationFormulaInvariant.makeBooleanInvariant(firstLocation, false);
    CandidateInvariant third =
        SingleLocationFormulaInvariant.makeBooleanInvariant(secondLocation, true);

    ImmutableSet<CandidateInvariant> result =
        PredicateToKInductionInvariantConverter.combineCandidatesPerLocation(
            ImmutableSet.of(first, second, third));

    assertThat(result).hasSize(2);
    assertThat(result.stream().filter(candidate -> candidate.appliesTo(firstLocation)).count())
        .isEqualTo(1);
    assertThat(result.stream().filter(candidate -> candidate.appliesTo(secondLocation)).count())
        .isEqualTo(1);
  }
}
