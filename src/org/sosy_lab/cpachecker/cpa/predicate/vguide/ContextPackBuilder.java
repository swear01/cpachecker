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
  private String readSourceSliced(List<? extends AbstractState> fullTrace) {
    try {
      StringBuilder sb = new StringBuilder();
      for (Path f : cfa.getFileNames()) {
        sb.append("// File: ").append(f.getFileName()).append('\n');
        String content = Files.readString(f);
        if (content.length() <= SourceSlicer.SLICE_THRESHOLD) {
          sb.append(content).append('\n');
          continue;
        }
        List<int[]> ranges = new ArrayList<>(SourceSlicer.topLevelDeclarationRanges(content));
        java.util.Optional<LoopStructure> loopStructure = cfa.getLoopStructure();
        if (loopStructure.isPresent()) {
          for (Loop loop : loopStructure.orElseThrow().getAllLoops()) {
            for (CFANode head : loop.getLoopHeads()) {
              collectNodeLines(f, head, ranges);
            }
          }
        }
        for (AbstractState state : fullTrace) {
          CFANode node = AbstractStates.extractLocation(state);
          if (node != null) {
            collectNodeLines(f, node, ranges);
          }
        }
        ranges.addAll(SourceSlicer.assertionRanges(content));
        if (ranges.isEmpty()) {
          // no loop heads / assertion / declarations detected: bounded head instead of the
          // full oversized payload
          sb.append(SourceSlicer.head(content));
        } else {
          sb.append(SourceSlicer.slice(content, ranges, 2));
        }
        sb.append('\n');
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
    if (edge instanceof CDeclarationEdge) {
      // global initializer edges span the whole initializer (e.g. a huge constant array);
      // the declaration itself is kept via the top-level declaration ranges
      return;
    }
    FileLocation location = edge.getFileLocation();
    if (location.isRealLocation()
        && location
            .getFileName()
            .toAbsolutePath()
            .normalize()
            .equals(file.toAbsolutePath().normalize())) {
      ranges.add(new int[] {location.getStartingLineNumber(), location.getEndingLineNumber()});
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
