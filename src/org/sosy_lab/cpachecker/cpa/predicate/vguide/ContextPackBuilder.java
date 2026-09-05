// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import com.google.common.base.Splitter;
import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableSet;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.sosy_lab.cpachecker.cfa.CFA;
import org.sosy_lab.cpachecker.cfa.ast.FileLocation;
import org.sosy_lab.cpachecker.cfa.model.CFAEdge;
import org.sosy_lab.cpachecker.cfa.model.CFANode;
import org.sosy_lab.cpachecker.cfa.model.c.CDeclarationEdge;
import org.sosy_lab.cpachecker.core.interfaces.AbstractStateWithLocation;
import org.sosy_lab.cpachecker.cpa.arg.ARGState;
import org.sosy_lab.cpachecker.cpa.predicate.BlockFormulaStrategy.BlockFormulas;
import org.sosy_lab.cpachecker.util.AbstractStates;
import org.sosy_lab.cpachecker.util.LoopStructure.Loop;
import org.sosy_lab.cpachecker.util.predicates.interpolation.CounterexampleTraceInfo;
import org.sosy_lab.cpachecker.util.predicates.smt.FormulaManagerView;
import org.sosy_lab.java_smt.api.BooleanFormula;

/** Builds {@link ContextPack} from a spurious refinement event. */
public final class ContextPackBuilder {

  private static final Pattern ASSERTION = Pattern.compile("\\b__VERIFIER_assert\\s*\\(");

  private final CFA cfa;
  private final LoopHeadIndex loopHeadIndex;
  private final FormulaManagerView fmgr;

  public ContextPackBuilder(CFA cfa, LoopHeadIndex loopHeadIndex, FormulaManagerView fmgr) {
    this.cfa = cfa;
    this.loopHeadIndex = loopHeadIndex;
    this.fmgr = fmgr;
  }

  public ContextPack buildSourceOnly() {
    String source = readSourceSliced(ImmutableList.of());
    String assertion = extractAssertion(source);
    ImmutableList<LoopHeadInfo> loopHeads = loopHeadIndex.getLoopHeads();
    var varContract = VarContractBuilder.build(ImmutableSet.of());
    return new ContextPack(
        0,
        source,
        assertion,
        loopHeads,
        varContract,
        ImmutableSet.of(),
        new BlockFormulas(ImmutableList.of()),
        ImmutableList.of(),
        "",
        "");
  }

  public ContextPack build(
      int refinementIndex,
      BlockFormulas formulas,
      CounterexampleTraceInfo counterexample,
      List<ARGState> fullTrace,
      List<? extends org.sosy_lab.cpachecker.core.interfaces.AbstractState> abstractionTrace) {
    Set<String> encodedVars = new HashSet<>();
    for (BooleanFormula f : formulas.getFormulas()) {
      encodedVars.addAll(fmgr.extractVariableNames(f));
    }
    ImmutableList<BooleanFormula> itps =
        counterexample.isSpurious() && counterexample.getInterpolants() != null
            ? counterexample.getInterpolants()
            : ImmutableList.of();
    String source = readSourceSliced(fullTrace);
    String assertion = extractAssertion(source);
    var varContract = VarContractBuilder.build(encodedVars);
    ImmutableList<LoopHeadInfo> loopHeads = loopHeadIndex.getLoopHeads();
    String relationSummary =
        CeSummaryBuilder.build(
            fmgr, formulas, itps, loopHeads, varContract, assertion, abstractionTrace);
    String ceSummary =
        StructuredCounterexampleBuilder.build(
            assertion,
            loopHeads,
            abstractionTrace.stream()
                .map(s -> AbstractStates.extractStateByType(s, AbstractStateWithLocation.class))
                .filter(Objects::nonNull)
                .toList(),
            relationSummary);
    return new ContextPack(
        refinementIndex,
        source,
        assertion,
        loopHeads,
        varContract,
        ImmutableSet.copyOf(encodedVars),
        formulas,
        itps,
        ceSummary,
        "");
  }

  /** Source-only UTF-16 budget, including file headers, newlines and omission markers. */
  static final int PROMPT_BUDGET = 300_000;

  private String readSourceSliced(List<ARGState> fullTrace) {
    StringBuilder sb = new StringBuilder();
    List<Path> files = cfa.getFileNames();
    long rawTotal = 0;
    if (files.size() > 1) {
      for (Path file : files) {
        try {
          rawTotal +=
              Files.readString(file, StandardCharsets.UTF_8).length()
                  + ("// File: " + file.getFileName() + "\n\n").length();
        } catch (IOException e) {
          rawTotal +=
              ("// File: " + file.getFileName() + "\n// source unavailable: read failed\n")
                  .length();
        }
      }
    }
    for (int i = 0; i < files.size(); i++) {
      Path file = files.get(i);
      String header = "// File: " + file.getFileName() + "\n";
      String omitted = "// source omitted: file budget exhausted\n";
      int remaining = PROMPT_BUDGET - sb.length();
      int share = rawTotal <= PROMPT_BUDGET ? remaining : remaining / (files.size() - i);
      if (share < header.length() + omitted.length() + 1) {
        String marker = "// source omitted: " + (files.size() - i) + " remaining files (budget)\n";
        if (marker.length() <= remaining) {
          sb.append(marker);
        }
        break;
      }
      int limit = share - header.length() - 1;
      sb.append(header);
      try {
        String content = Files.readString(file, StandardCharsets.UTF_8);
        String part = content;
        if (content.length() > SourceSlicer.SLICE_THRESHOLD || content.length() > limit) {
          List<int[]> assertions = SourceSlicer.assertionRanges(content);
          List<int[]> essential = new ArrayList<>(assertions);
          Path target = file.toAbsolutePath().normalize();
          if (cfa.getLoopStructure().isPresent()) {
            for (Loop loop : cfa.getLoopStructure().orElseThrow().getAllLoops()) {
              for (CFANode head : loop.getLoopHeads()) {
                collectNodeLines(target, head, essential);
              }
            }
          }
          for (ARGState state : fullTrace) {
            CFANode node = AbstractStates.extractLocation(state);
            if (node != null) {
              collectNodeLines(target, node, essential);
            }
          }
          List<int[]> all = new ArrayList<>(SourceSlicer.topLevelDeclarationRanges(content));
          all.addAll(essential);
          part = all.isEmpty() ? SourceSlicer.head(content) : SourceSlicer.slice(content, all, 2);
          if (part.length() > limit) {
            part =
                "// source omitted: declarations (budget)\n"
                    + (essential.isEmpty()
                        ? SourceSlicer.head(content)
                        : SourceSlicer.slice(content, essential, 2));
          }
          if (part.length() > limit && !assertions.isEmpty()) {
            part =
                "// source omitted: non-assertion ranges (budget)\n"
                    + SourceSlicer.slice(content, assertions, 2);
          }
          if (part.length() > limit) {
            int headLimit = Math.min(limit, SourceSlicer.HEAD_LIMIT);
            int end = part.lastIndexOf('\n', headLimit - omitted.length() - 1);
            part = (end < 0 ? "" : part.substring(0, end + 1)) + omitted;
          }
        }
        sb.append(part).append('\n');
      } catch (IOException e) {
        sb.append("// source unavailable: read failed\n");
      }
    }
    return sb.toString();
  }

  /** Collects the line ranges of all entering and leaving edges of the node (its statements). */
  private static void collectNodeLines(Path file, CFANode node, List<int[]> ranges) {
    for (CFAEdge edge : node.getLeavingEdges()) {
      collectEdgeLine(file, edge, ranges);
    }
    for (CFAEdge edge : node.getEnteringEdges()) {
      collectEdgeLine(file, edge, ranges);
    }
  }

  private static void collectEdgeLine(Path file, CFAEdge edge, List<int[]> ranges) {
    if (edge instanceof CDeclarationEdge c && c.getDeclaration().isGlobal()) {
      // global initializer edges span the whole initializer (e.g. a huge constant array);
      // the declaration itself is kept via the top-level declaration ranges. Local
      // declarations on the path (e.g. int i = 0;) are retained.
      return;
    }
    FileLocation location = edge.getFileLocation();
    if (location.isRealLocation()
        && location.getFileName().toAbsolutePath().normalize().equals(file)) {
      // origin line numbers map to the original source even when preprocessing or line
      // directives changed the analysis-code line numbers
      ranges.add(new int[] {location.getStartingLineInOrigin(), location.getEndingLineInOrigin()});
    }
  }

  static String extractAssertion(String source) {
    List<String> lines = Splitter.on('\n').splitToList(source);
    for (int[] range : SourceSlicer.assertionRanges(source)) {
      String call = String.join("\n", lines.subList(range[0] - 1, range[1]));
      String masked = SourceSlicer.stripCommentsAndStrings(call);
      Matcher match = ASSERTION.matcher(masked);
      if (!match.find()) {
        continue;
      }
      int depth = 1;
      for (int i = match.end(); i < masked.length(); i++) {
        if (masked.charAt(i) == '(') {
          depth++;
        } else if (masked.charAt(i) == ')' && --depth == 0) {
          return call.substring(match.end(), i).trim();
        }
      }
    }
    return "";
  }
}
