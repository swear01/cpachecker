// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-FileCopyrightText: 2026 SSU-WEI HUANG <https://github.com/swear01>
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.truth.Truth.assertThat;
import static org.mockito.Mockito.mock;

import java.util.Optional;
import org.junit.Test;
import org.sosy_lab.common.configuration.Configuration;
import org.sosy_lab.common.log.LogManager;
import org.sosy_lab.cpachecker.cpa.arg.ARGBasedRefiner;
import org.sosy_lab.cpachecker.util.LoopStructure;
import org.sosy_lab.cpachecker.util.predicates.AbstractionManager;
import org.sosy_lab.cpachecker.util.predicates.smt.FormulaManagerView;
import org.sosy_lab.cpachecker.util.test.TestCfaUtils;

public class VGuideRefinerTest {

  @Test
  public void disabledReturnsUnmodifiedDelegate() throws Exception {
    ARGBasedRefiner delegate = mock(ARGBasedRefiner.class);

    ARGBasedRefiner result =
        VGuideRefiner.wrapIfEnabled(
            delegate,
            Configuration.defaultConfiguration(),
            LogManager.createTestLogManager(),
            TestCfaUtils.makeCFA("int main() { return 0; }"),
            Optional.<LoopStructure>empty(),
            mock(AbstractionManager.class),
            mock(FormulaManagerView.class));

    assertThat(result).isSameInstanceAs(delegate);
  }
}
