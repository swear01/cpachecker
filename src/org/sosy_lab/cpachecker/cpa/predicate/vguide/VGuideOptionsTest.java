// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-FileCopyrightText: 2026 SSU-WEI HUANG <https://github.com/swear01>
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.truth.Truth.assertThat;
import static org.junit.Assert.assertThrows;

import org.junit.Test;
import org.sosy_lab.common.configuration.Configuration;
import org.sosy_lab.common.configuration.InvalidConfigurationException;

public class VGuideOptionsTest {

  @Test
  public void enabledConfigurationRequiresEndpointAndModel() throws Exception {
    Configuration config = Configuration.builder().setOption("vguide.enable", "true").build();

    assertThrows(InvalidConfigurationException.class, () -> new VGuideOptions(config));
  }

  @Test
  public void endpointAcceptsOnlyCredentialFreeHttpUris() throws Exception {
    Configuration fileEndpoint =
        Configuration.builder()
            .setOption("vguide.enable", "true")
            .setOption("vguide.endpoint", "file:///tmp/provider")
            .setOption("vguide.model", "model")
            .build();
    Configuration httpEndpoint =
        Configuration.builder()
            .setOption("vguide.enable", "true")
            .setOption("vguide.endpoint", "http://127.0.0.1:8000/v1/chat/completions")
            .setOption("vguide.model", "model")
            .build();
    VGuideOptions fileOptions = new VGuideOptions(fileEndpoint);

    assertThrows(InvalidConfigurationException.class, fileOptions::endpoint);
    assertThat(new VGuideOptions(httpEndpoint).endpoint().getScheme()).isEqualTo("http");
  }
}
