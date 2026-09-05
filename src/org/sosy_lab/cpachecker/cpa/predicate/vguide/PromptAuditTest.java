// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import static com.google.common.truth.Truth.assertThat;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableMap;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import org.junit.Rule;
import org.junit.Test;
import org.junit.rules.TemporaryFolder;
import org.sosy_lab.common.ShutdownNotifier;
import org.sosy_lab.common.configuration.Configuration;
import org.sosy_lab.common.configuration.FileOption;
import org.sosy_lab.common.configuration.converters.FileTypeConverter;
import org.sosy_lab.common.log.LogManager;
import org.sosy_lab.cpachecker.cfa.CFA;
import org.sosy_lab.cpachecker.cfa.CFACreator;
import org.sosy_lab.cpachecker.cfa.model.CFAEdge;
import org.sosy_lab.cpachecker.cfa.model.CFANode;
import org.sosy_lab.cpachecker.core.interfaces.AbstractStateWithLocation;
import org.sosy_lab.cpachecker.cpa.arg.ARGState;
import org.sosy_lab.cpachecker.cpa.predicate.BlockFormulaStrategy.BlockFormulas;
import org.sosy_lab.cpachecker.util.predicates.interpolation.CounterexampleTraceInfo;
import org.sosy_lab.cpachecker.util.predicates.smt.SolverViewBasedTest0;
import org.sosy_lab.java_smt.SolverContextFactory.Solvers;
import org.sosy_lab.java_smt.api.BooleanFormula;

/** Model-free, synthetic trace fixtures through the production context and request builders. */
public class PromptAuditTest extends SolverViewBasedTest0 {

  @Override
  protected Solvers solverToUse() {
    return Solvers.MATHSAT5;
  }

  @Rule public final TemporaryFolder tmp = new TemporaryFolder();

  @Test
  public void relationAndInterpolantCapsAreExplicitInAudit() {
    var interpolants = ImmutableList.<BooleanFormula>builder();
    for (int i = 0; i < 6; i++) {
      String name = "main::variable" + i + "x".repeat(300) + "@1";
      interpolants.add(
          mgrv.parse(
              "(declare-fun |"
                  + name
                  + "| () (_ BitVec 32))\n"
                  + "(assert (bvsle |"
                  + name
                  + "| (_ bv10 32)))"));
    }
    String summary =
        CeSummaryBuilder.build(
            mgrv,
            new BlockFormulas(ImmutableList.of()),
            interpolants.build(),
            ImmutableList.of(),
            ImmutableMap.of(),
            "",
            ImmutableList.of());
    assertThat(summary.lines().count()).isEqualTo(3);
    assertThat(summary).contains("...");
    assertThat(summary.length()).isAtMost(CeSummaryBuilder.MAX_TOTAL_CHARS);
    for (String line : summary.lines().toList()) {
      assertThat(line.strip().substring("interp: ".length()).length())
          .isAtMost(CeSummaryBuilder.MAX_REL_CHARS);
    }
  }

  @Test
  public void reproduceProductionMessages() throws Exception {
    String auditDir = System.getProperty("vguide.promptAuditDir");
    Path root =
        auditDir == null ? tmp.getRoot().toPath() : Files.createDirectories(Path.of(auditDir));
    String helper =
        "void reach_error(void);\nvoid __VERIFIER_assert(int cond) {\n"
            + "  if (!cond) reach_error();\n}\n";
    String small =
        helper
            + "// Unicode: 中文 😀\nint main() {\n  int i = 0;\n"
            + "  while (i < 10) { i++; }\n  __VERIFIER_assert((i + 1) > 10);\n}\n";
    String large = "const int weights[20000] = {\n" + "12345,\n".repeat(20000) + "};\n" + small;
    StringBuilder multi = new StringBuilder("void reach_error(void);\nint main() {\n");
    for (int i = 0; i < 6; i++) {
      multi
          .append("  int x")
          .append(i)
          .append(" = 0;\n  while (x")
          .append(i)
          .append(" < 10) { x")
          .append(i)
          .append("++; }\n");
    }
    multi.append("  if (x5 != 10) reach_error();\n}\n");
    String array =
        helper
            + "int main() {\n  int a[10];\n  int i = 0;\n"
            + "  while (i < 10) { a[i] = i; i++; }\n  __VERIFIER_assert(a[9] == 9);\n}\n";
    List<String> names = ImmutableList.of("small", "large", "multi_loop", "array");
    List<String> sources = ImmutableList.of(small, large, multi.toString(), array);
    ObjectMapper json = new ObjectMapper();
    for (int i = 0; i < names.size(); i++) {
      Path dir = Files.createDirectories(root.resolve(names.get(i)));
      Path source = dir.resolve("input.c");
      Files.writeString(source, sources.get(i));
      CFA cfa =
          new CFACreator(
                  Configuration.builder()
                      .addConverter(
                          FileOption.class,
                          FileTypeConverter.create(
                              Configuration.builder().setOption("output.disable", "true").build()))
                      .build(),
                  LogManager.createTestLogManager(),
                  ShutdownNotifier.createDummy())
              .parseFileAndCreateCFA(ImmutableList.of(source.toString()));
      LoopHeadIndex heads = new LoopHeadIndex(cfa.getLoopStructure());
      var formulas = ImmutableList.<BooleanFormula>builder();
      List<LocState> trace = new ArrayList<>();
      for (int h = 0; h < heads.getLoopHeads().size(); h++) {
        String name = i == 2 ? "x" + h : "i";
        formulas.add(
            mgrv.parse(
                "(declare-fun |main::"
                    + name
                    + "@1| () (_ BitVec 32))\n"
                    + "(assert (bvsle |main::"
                    + name
                    + "@1| (_ bv10 32)))"));
        trace.add(new LocState(heads.getLoopHeads().get(h).node()));
      }
      List<ARGState> argTrace = trace.stream().map(s -> new ARGState(s, null)).toList();
      BlockFormulas blocks = new BlockFormulas(formulas.build());
      ContextPack pack =
          new ContextPackBuilder(cfa, heads, mgrv)
              .build(
                  2,
                  blocks,
                  CounterexampleTraceInfo.infeasible(ImmutableList.of()),
                  argTrace,
                  argTrace);
      ProposalPromptBuilder builder = new ProposalPromptBuilder(heads, false);
      PromptMessages messages =
          builder.buildRepair(
              pack,
              ImmutableList.of("(= i (_ bv99 32))"),
              new PredicateBudget(4, 12),
              PromptProfile.SAFE,
              2,
              "synthetic prior CE\n",
              "synthetic refinement outcome\n",
              "synthetic native precision\n");
      String request =
          PredicateProposalClient.buildRequestBody(
              messages, "meta", "muse-spark-1.2-contributor", 1024, false, "minimal");
      var body = json.readTree(request);
      assertThat(body.path("messages").get(0).path("content").asText())
          .isEqualTo(messages.system());
      assertThat(body.path("messages").get(1).path("content").asText()).isEqualTo(messages.user());
      assertThat(messages.user()).contains("synthetic prior CE");
      assertThat(messages.user()).contains("branch_conditions");
      if (i == 2) {
        String relations = json.readTree(pack.ceSummary()).path("relations").asText();
        assertThat(relations.lines().filter(line -> line.stripLeading().startsWith("L@")).count())
            .isEqualTo(4);
        assertThat(json.readTree(pack.ceSummary()).path("trace").size()).isEqualTo(6);
        assertThat(pack.sourceCode()).contains("if (x5 != 10) reach_error()");
      }
      if (i == 3) {
        assertThat(messages.user()).contains("a[i] = i");
        assertThat(pack.assertion()).isEqualTo("a[9] == 9");
      }
      for (LoopHeadInfo head : heads.getLoopHeads()) {
        assertThat(messages.user()).contains(head.label() + " (function");
      }
      Files.writeString(dir.resolve("system.txt"), messages.system());
      Files.writeString(dir.resolve("user.txt"), messages.user());
      Files.writeString(dir.resolve("request.json"), request);
      Files.writeString(dir.resolve("source-retained.c"), pack.sourceCode());
      StringBuilder smt = new StringBuilder();
      for (BooleanFormula block : blocks.getFormulas()) {
        smt.append(mgrv.dumpFormula(block)).append('\n');
      }
      Files.writeString(dir.resolve("blocks.smt2"), smt);
      var report = json.createObjectNode();
      report.set("prompt_accounting", VGuideAnalysisDumper.promptAccounting(messages, 1024, null));
      report.put(
          "fixture_kind",
          "synthetic ARG-wrapped trace/formulas; real parsed CFA; no API call/verdict");
      report.put("raw_source_utf16_units", sources.get(i).length());
      report.put("retained_source_utf16_units", pack.sourceCode().length());
      report.put("extracted_assertion", pack.assertion());
      report.put("loop_heads", heads.getLoopHeads().size());
      report.put("messages_utf16_units", messages.charCount());
      report.put(
          "messages_utf8_bytes",
          messages.system().getBytes(StandardCharsets.UTF_8).length
              + messages.user().getBytes(StandardCharsets.UTF_8).length);
      report.put("dump_text_utf16_units", messages.fullText().length());
      report.put("reserved_completion_tokens", 1024);
      report.putNull("api_usage");
      report.putNull("provider_context_limit_tokens");
      Files.writeString(
          dir.resolve("audit.json"),
          json.writerWithDefaultPrettyPrinter().writeValueAsString(report));
    }
  }

  private record LocState(CFANode node) implements AbstractStateWithLocation {
    @Override
    public CFANode getLocationNode() {
      return node;
    }

    @Override
    public Iterable<CFAEdge> getOutgoingEdges() {
      return node.getLeavingEdges();
    }
  }
}
