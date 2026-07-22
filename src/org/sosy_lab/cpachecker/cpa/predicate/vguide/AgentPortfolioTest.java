// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-FileCopyrightText: 2026 SSU-WEI HUANG <https://github.com/swear01>
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.truth.Truth.assertThat;

import com.google.common.collect.ImmutableList;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import org.junit.Test;

public class AgentPortfolioTest {

  @Test
  public void invokesAllRolesAndDeduplicatesCandidates() throws Exception {
    List<String> roles = new ArrayList<>();
    CandidateProvider provider =
        (role, system, context) -> {
          roles.add(role);
          String response =
              """
              {"schema_version":"vguide-candidates-v1","candidates":[
                {"loop_head_id":"N1","predicate":"(assert true)"}
              ]}
              """;
          return new CandidateProvider.ProviderResponse(response, "test-model", "hash-" + role);
        };
    AgentPortfolio portfolio = new AgentPortfolio(provider, 2);

    AgentPortfolio.PortfolioResult result = portfolio.propose(emptyContext());

    assertThat(roles).containsExactly("invariant", "counterexample", "refinement").inOrder();
    assertThat(result.candidates()).hasSize(1);
    assertThat(result.providerCalls()).hasSize(3);
  }

  @Test
  public void providerFailureIsNotSilentlyIgnored() {
    CandidateProvider provider =
        (role, system, context) -> {
          throw new IOException("provider unavailable");
        };
    AgentPortfolio portfolio = new AgentPortfolio(provider, 2);

    IOException failure =
        org.junit.Assert.assertThrows(IOException.class, () -> portfolio.propose(emptyContext()));

    assertThat(failure).hasMessageThat().contains("provider unavailable");
  }

  private static ContextPack emptyContext() {
    return new ContextPack(
        ContextPack.SCHEMA_VERSION,
        1,
        ImmutableList.of(),
        ImmutableList.of(),
        ImmutableList.of(),
        ImmutableList.of(),
        new ContextPack.NativeRefinementOutcome(true, 0),
        ImmutableList.of());
  }
}
