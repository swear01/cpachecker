// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableSet;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.sosy_lab.cpachecker.cfa.CFA;
import org.sosy_lab.cpachecker.cfa.ast.FileLocation;
import org.sosy_lab.cpachecker.cfa.model.c.CDeclarationEdge;
import org.sosy_lab.cpachecker.cfa.model.CFAEdge;
import org.sosy_lab.cpachecker.cfa.model.CFANode;
import org.sosy_lab.cpachecker.core.interfaces.AbstractState;
import org.sosy_lab.cpachecker.cpa.arg.ARGState;
import org.sosy_lab.cpachecker.util.AbstractStates;
import org.sosy_lab.cpachecker.util.LoopStructure;
import org.sosy_lab.cpachecker.util.LoopStructure.Loop;
import org.sosy_lab.cpachecker.cpa.predicate.BlockFormulaStrategy.BlockFormulas;
import org.sosy_lab.cpachecker.util.predicates.interpolation.CounterexampleTraceInfo;
import org.sosy_lab.cpachecker.util.predicates.smt.FormulaManagerView;
import org.sosy_lab.java_smt.api.BooleanFormula;

/** Builds {@link ContextPack} from a spurious refinement event. */
public final class ContextPackBuilder {

  private static final Pattern ASSERTION =
      Pattern.compile("__VERIFIER_assert\\s*\\(\\s*(.+?)\\s*\\)");

  private final CFA cfa;
  private final LoopHeadIndex loopHeadIndex;
  private final FormulaManagerView fmgr;

  public ContextPackBuilder(CFA cfa, LoopHeadIndex loopHeadIndex, FormulaManagerView fmgr) {
    this.cfa = cfa;
    this.loopHeadIndex = loopHeadIndex;
    this.fmgr = fmgr;
  }

  public ContextPack buildSourceOnly() {
    String source = readSourceSliced(List.of());
    String assertion = extractAssertion(source);
    ImmutableList<LoopHeadInfo> loopHeads = loopHeadIndex.getLoopHeads();
    var varContract = VarContractBuilder.build(Set.of());
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
        StructuredCounterexampleBuilder.build(assertion, loopHeads, abstractionTrace, relationSummary);
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

  /**
   * Reads the source; for very large files (issue #74) slices each to the full counterexample
   * path, loop heads, top-level declarations and assertion so the prompt stays within the LLM
   * context budget. Slicing is per file so line numbers stay file-local.
   */
  /** Total prompt-source budget across all files. */
  private static final int PROMPT_BUDGET = 300_000;

  /**
   * Reads the source; for very large files (issue #74) slices each to the full counterexample
   * path, loop heads, top-level declarations and assertion so the prompt stays within the LLM
   * context budget. Slicing is per file so line numbers stay file-local; the cumulative total
   * is capped at {@link #PROMPT_BUDGET}.
   */
  private String readSourceSliced(List<ARGState> fullTrace) {
    try {
      StringBuilder sb = new StringBuilder();
      for (Path f : cfa.getFileNames()) {
        if (sb.length() >= PROMPT_BUDGET) {
          break; // budget exhausted: no more files
        }
        sb.append("// File: ").append(f.getFileName()).append('\n');
        String content = Files.readString(f);
        if (content.length() <= SourceSlicer.SLICE_THRESHOLD) {
          if (sb.length() + content.length() <= PROMPT_BUDGET) {
            sb.append(content).append('\n');
          } else {
            // only partial space left: keep the assertion sites so the property survives;
            // a file without assertions is bounded by its head instead of appended in full
            List<int[]> assertionRanges = SourceSlicer.assertionRanges(content);
            sb.append(
                    assertionRanges.isEmpty()
                        ? SourceSlicer.head(content)
                        : SourceSlicer.slice(content, assertionRanges, 2))
                .append('\n');
          }
          continue;
        }
        List<int[]> topLevelRanges = SourceSlicer.topLevelDeclarationRanges(content);
        List<int[]> essentialRanges = new ArrayList<>();
        Path target = f.toAbsolutePath().normalize();
        java.util.Optional<LoopStructure> loopStructure = cfa.getLoopStructure();
        if (loopStructure.isPresent()) {
          for (Loop loop : loopStructure.get().getAllLoops()) {
            for (CFANode head : loop.getLoopHeads()) {
              collectNodeLines(target, head, essentialRanges);
            }
          }
        }
        for (ARGState state : fullTrace) {
          CFANode node = AbstractStates.extractLocation(state);
          if (node != null) {
            collectNodeLines(target, node, essentialRanges);
          }
        }
        essentialRanges.addAll(SourceSlicer.assertionRanges(content));
        List<int[]> allRanges = new ArrayList<>(topLevelRanges);
        allRanges.addAll(essentialRanges);
        String part;
        if (allRanges.isEmpty()) {
          // no loop heads / assertion / declarations detected: bounded head instead of the
          // full oversized payload
          part = SourceSlicer.head(content);
        } else {
          part = SourceSlicer.slice(content, allRanges, 2);
        }
        if (sb.length() + part.length() > PROMPT_BUDGET) {
          // declarations crowd out the essentials: re-slice without them (path + loops +
          // assertion only), and fall back to a head for pathological oversized paths
          part = SourceSlicer.slice(content, essentialRanges, 2);
        }
        if (sb.length() + part.length() > PROMPT_BUDGET) {
          part = SourceSlicer.head(part);
        }
        sb.append(part).append('\n');
      }
      return sb.toString();
    } catch (IOException e) {
      return "// source unavailable";
    }
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
      ranges.add(
          new int[] {location.getStartingLineInOrigin(), location.getEndingLineInOrigin()});
    }
  }

  static String extractAssertion(String source) {
    Matcher m = ASSERTION.matcher(source);
    if (m.find()) {
      return m.group(1).trim();
    }
    return "";
  }
}
