// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-FileCopyrightText: 2026 Dirk Beyer <https://www.sosy-lab.org>
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.core.algorithm.bmc.pdr;

import static com.google.common.truth.Truth.assertThat;

import com.google.common.collect.ImmutableSet;
import org.junit.Test;
import org.sosy_lab.cpachecker.cfa.model.CFANode;
import org.sosy_lab.cpachecker.core.algorithm.bmc.candidateinvariants.CandidateInvariant;
import org.sosy_lab.cpachecker.core.algorithm.bmc.candidateinvariants.SingleLocationFormulaInvariant;
import org.sosy_lab.cpachecker.core.algorithm.bmc.candidateinvariants.TargetLocationCandidateInvariant;

public class PdrAlgorithmOracleTest {

  @Test
  public void rootModePreservesSeparateOracleCandidates() {
    ImmutableSet<CandidateInvariant> candidates = oracleCandidates();

    ImmutableSet<CandidateInvariant> roots =
        PdrAlgorithm.selectRootCandidates(PdrAlgorithm.OracleMode.ROOT, candidates);

    assertThat(roots).contains(TargetLocationCandidateInvariant.INSTANCE);
    assertThat(roots).containsAtLeastElementsIn(candidates);
    assertThat(roots).hasSize(4);
  }

  @Test
  public void conjunctiveRootModeCombinesEachLocation() {
    ImmutableSet<CandidateInvariant> roots =
        PdrAlgorithm.selectRootCandidates(
            PdrAlgorithm.OracleMode.CONJUNCTIVE_ROOT, oracleCandidates());

    assertThat(roots).contains(TargetLocationCandidateInvariant.INSTANCE);
    assertThat(roots).hasSize(3);
  }

  @Test
  public void abstractionModeDoesNotAddTrustedRootCandidates() {
    ImmutableSet<CandidateInvariant> roots =
        PdrAlgorithm.selectRootCandidates(PdrAlgorithm.OracleMode.ABSTRACTION, oracleCandidates());

    assertThat(roots).containsExactly(TargetLocationCandidateInvariant.INSTANCE);
  }

  private static ImmutableSet<CandidateInvariant> oracleCandidates() {
    CFANode firstLocation = CFANode.newDummyCFANode("first");
    CFANode secondLocation = CFANode.newDummyCFANode("second");
    return ImmutableSet.of(
        SingleLocationFormulaInvariant.makeBooleanInvariant(firstLocation, true),
        SingleLocationFormulaInvariant.makeBooleanInvariant(firstLocation, false),
        SingleLocationFormulaInvariant.makeBooleanInvariant(secondLocation, true));
  }
}
