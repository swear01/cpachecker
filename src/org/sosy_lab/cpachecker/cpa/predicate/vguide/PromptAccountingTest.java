// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.truth.Truth.assertThat;
import static org.junit.Assert.assertThrows;
import static org.mockito.Mockito.mock;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableMap;
import com.google.common.collect.ImmutableSet;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Optional;
import org.junit.Rule;
import org.junit.Test;
import org.junit.rules.TemporaryFolder;
import org.sosy_lab.common.configuration.Configuration;
import org.sosy_lab.common.log.LogManager;
import org.sosy_lab.cpachecker.cpa.predicate.BlockFormulaStrategy.BlockFormulas;
import org.sosy_lab.cpachecker.util.predicates.smt.FormulaManagerView;

public class PromptAccountingTest {
  @Rule public final TemporaryFolder tmp = new TemporaryFolder();

  @Test
  public void dumperPreservesExactMessagesForRepeatedCalls() throws Exception {
    ContextPack pack =
        new ContextPack(
            1,
            "int i;",
            "",
            ImmutableList.of(),
            ImmutableMap.of(),
            ImmutableSet.of(),
            new BlockFormulas(ImmutableList.of()),
            ImmutableList.of(),
            "",
            "");
    VGuideAnalysisDumper dumper =
        new VGuideAnalysisDumper(
            LogManager.createNullLogManager(),
            tmp.getRoot().toPath(),
            "task",
            "task",
            0,
            true,
            false,
            mock(FormulaManagerView.class),
            new VGuideOptions(Configuration.builder().build()));
    PromptMessages messages = new PromptMessages("system 😀", "USER:\n中文");
    LlmProposalResult result =
        new LlmProposalResult("{\"candidates\":[]}", "", null, 0, 0, "", "synthetic-test");
    for (int i = 0; i < 2; i++) {
      dumper.recordLlmApiCall(
          1,
          1,
          "safe_ensemble_extra",
          "safe",
          messages,
          pack,
          PromptProfile.SAFE,
          result,
          ImmutableList.of(),
          null);
    }
    Path task = tmp.getRoot().toPath().resolve("tasks/task");
    var rows = Files.readAllLines(task.resolve("llm_rounds.jsonl"), StandardCharsets.UTF_8);
    assertThat(rows).hasSize(2);
    ObjectMapper json = new ObjectMapper();
    var first = json.readTree(rows.get(0));
    var second = json.readTree(rows.get(1));
    assertThat(first.path("prompt_path").asText())
        .isNotEqualTo(second.path("prompt_path").asText());
    for (var row : ImmutableList.of(first, second)) {
      assertThat(
              Files.readString(
                  task.resolve(row.path("prompt_path").asText()), StandardCharsets.UTF_8))
          .isEqualTo(messages.fullText());
      var saved = json.readTree(task.resolve(row.path("prompt_messages_path").asText()).toFile());
      assertThat(saved.path("system").asText()).isEqualTo(messages.system());
      assertThat(saved.path("user").asText()).isEqualTo(messages.user());
      assertThat(row.path("prompt_accounting").path("messages_total").path("utf16_units").asInt())
          .isEqualTo(messages.charCount());
      assertThat(row.path("context_selection").path("assertion_summary").asText())
          .contains("inspect retained source");
    }
    Files.createDirectory(task.resolve("prompts/r001_safe_safe_ensemble_extra_c0003.prompt.txt"));
    dumper.recordLlmApiCall(
        1,
        1,
        "safe_ensemble_extra",
        "safe",
        messages,
        pack,
        PromptProfile.SAFE,
        result,
        ImmutableList.of(),
        null);
    var failed =
        json.readTree(
            Files.readAllLines(task.resolve("llm_rounds.jsonl"), StandardCharsets.UTF_8).get(2));
    assertThat(failed.path("prompt_dump_status").asText()).isEqualTo("write_failed");
    assertThat(failed.has("prompt_path")).isFalse();
    assertThat(failed.has("prompt_messages_path")).isFalse();
  }

  @Test
  public void accountsForEveryProductionBlockAndUnicodeUnit() throws Exception {
    ContextPack pack =
        new ContextPack(
            2,
            "int a[10]; // 中文 😀",
            "a[9] == 9",
            ImmutableList.of(),
            ImmutableMap.of("i", ImmutableSet.of("main::i@1")),
            ImmutableSet.of("main::i@1"),
            new BlockFormulas(ImmutableList.of()),
            ImmutableList.of(),
            "{\"trace\":[],\"unavailable\":[\"ssa_values\"]}",
            "not rendered");
    for (boolean minimal : ImmutableList.of(false, true)) {
      ProposalPromptBuilder builder =
          new ProposalPromptBuilder(new LoopHeadIndex(Optional.empty()), minimal);
      for (PromptProfile profile : PromptProfile.values()) {
        PromptMessages messages =
            builder.buildRepair(
                pack,
                ImmutableList.of("(= i 9)"),
                new PredicateBudget(4, 12),
                profile,
                2,
                "history\n",
                "outcomes\n",
                "native\n");
        assertThat(messages.userComponents().keySet())
            .containsExactly(
                "loop_heads",
                "contract",
                "source_hints",
                "source",
                "profile",
                "ce_summary",
                "ce_history",
                "refinement_outcomes",
                "native_precision",
                "repair")
            .inOrder();
        assertThat(String.join("", messages.userComponents().values())).isEqualTo(messages.user());
        assertThat(messages.user()).doesNotContain("not rendered");
        var usage = new ObjectMapper().readTree("{\"prompt_tokens\":123,\"completion_tokens\":7}");
        var audit = VGuideAnalysisDumper.promptAccounting(messages, 100, usage);
        assertThat(audit.path("reserved_completion_tokens").asInt()).isEqualTo(256);
        assertThat(audit.path("api_prompt_plus_reserved_completion_tokens").asInt()).isEqualTo(379);
        assertThat(audit.path("fits_context_window").isNull()).isTrue();
        for (String unit : ImmutableList.of("utf16_units", "unicode_code_points", "utf8_bytes")) {
          int sum = 0;
          for (var block : audit.path("user_components")) {
            sum += block.path(unit).asInt();
          }
          assertThat(sum).isEqualTo(audit.path("user").path(unit).asInt());
          assertThat(sum + audit.path("system").path(unit).asInt())
              .isEqualTo(audit.path("messages_total").path(unit).asInt());
        }
        assertThat(audit.path("messages_total").path("utf16_units").asInt())
            .isEqualTo(messages.charCount());
        assertThat(audit.path("messages_total").path("unicode_code_points").asInt())
            .isEqualTo(messages.charCount() - 1);
        assertThat(audit.path("messages_total").path("utf8_bytes").asInt())
            .isEqualTo(
                (messages.system() + messages.user()).getBytes(StandardCharsets.UTF_8).length);
        assertThat(messages.fullText().length()).isEqualTo(messages.charCount() + 15);
        var absent = VGuideAnalysisDumper.promptAccounting(messages, 1024, null);
        assertThat(absent.path("api_prompt_tokens").isNull()).isTrue();
        assertThat(absent.path("api_prompt_plus_reserved_completion_tokens").isNull()).isTrue();
      }
    }
  }

  @Test
  public void rejectsInconsistentComponentMetadata() {
    assertThrows(
        IllegalArgumentException.class,
        () -> new PromptMessages("system", "user", ImmutableMap.of("source", "wrong")));
  }
}
