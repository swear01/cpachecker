// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-FileCopyrightText: 2007-2020 Dirk Beyer <https://www.sosy-lab.org>
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.logging.Level;
import org.sosy_lab.common.log.LogManager;
import org.sosy_lab.cpachecker.cfa.model.CFAEdge;
import org.sosy_lab.cpachecker.cfa.model.CFANode;
import org.sosy_lab.cpachecker.cfa.model.c.CAssumeEdge;
import org.sosy_lab.cpachecker.core.interfaces.AbstractState;
import org.sosy_lab.cpachecker.core.interfaces.Precision;
import org.sosy_lab.cpachecker.cpa.arg.ARGReachedSet;
import org.sosy_lab.cpachecker.cpa.arg.ARGState;
import org.sosy_lab.cpachecker.cpa.arg.path.ARGPath;
import org.sosy_lab.cpachecker.cpa.arg.path.PathIterator;
import org.sosy_lab.cpachecker.cpa.predicate.BlockFormulaStrategy.BlockFormulas;
import org.sosy_lab.cpachecker.util.AbstractStates;
import org.sosy_lab.cpachecker.util.Precisions;
import org.sosy_lab.cpachecker.util.predicates.AbstractionPredicate;
import org.sosy_lab.cpachecker.util.predicates.interpolation.CounterexampleTraceInfo;
import org.sosy_lab.cpachecker.util.predicates.smt.FormulaManagerView;
import org.sosy_lab.java_smt.api.BooleanFormula;

public class B5ContextDumper {

  private final String dumpDir;
  private final int dumpLimit;
  private final LogManager logger;
  private final FormulaManagerView fmgr;

  public B5ContextDumper(String pDumpDir, int pDumpLimit, FormulaManagerView pFmgr, LogManager pLogger) {
    dumpDir = pDumpDir;
    dumpLimit = pDumpLimit;
    fmgr = pFmgr;
    logger = pLogger;
  }

  public boolean isEnabled() {
    return dumpDir != null && !dumpDir.isBlank();
  }

  public void dumpRefinement(
      int refinementIndex,
      ARGPath allStatesTrace,
      List<ARGState> abstractionStatesTrace,
      BlockFormulas formulas,
      CounterexampleTraceInfo counterexample,
      ARGReachedSet pReached,
      Map<CFANode, Set<BooleanFormula>> pendingCandidates,
      Map<CFANode, Set<BooleanFormula>> injectedPredicates,
      Map<CFANode, Set<BooleanFormula>> entailedPredicates) {
    if (!isEnabled()) return;
    if (refinementIndex > dumpLimit) return;

    try {
      List<String> missing = new ArrayList<>();
      StringBuilder json = new StringBuilder();
      json.append("{\n");

      json.append("  \"refinement_index\": ").append(refinementIndex).append(",\n");
      json.append("  \"verification_status\": \"in_progress\",\n");

      dumpTrace(json, allStatesTrace, missing);
      json.append(",\n");
      dumpEdgeDetails(json, allStatesTrace, missing);
      json.append(",\n");
      dumpBlockFormulas(json, formulas, missing);
      json.append(",\n");
      dumpAbstractionStates(json, abstractionStatesTrace, missing);
      json.append(",\n");
      dumpInterpolants(json, counterexample, missing);
      json.append(",\n");
      dumpPrecision(json, pReached, missing);
      json.append(",\n");
      dumpCandidateFates(json, pendingCandidates, injectedPredicates, entailedPredicates, missing);
      json.append(",\n");
      dumpMissingFields(json, missing);
      json.append("\n}\n");

      Path dir = Paths.get(dumpDir);
      Files.createDirectories(dir);
      Path file = dir.resolve("refinement_" + refinementIndex + ".json");
      Files.writeString(file, json.toString());
      logger.log(Level.INFO, "B5 context dumped to ", file.toString());
    } catch (Exception e) {
      logger.logDebugException(e, "B5 context dump failed");
    }
  }

  private void dumpTrace(StringBuilder json, ARGPath allStatesTrace, List<String> missing) {
    try {
      List<ARGState> states = allStatesTrace.asStatesList();
      json.append("  \"trace_locations\": [\n");
      boolean first = true;
      for (ARGState s : states) {
        CFANode node = AbstractStates.extractLocation(s);
        if (node == null) continue;
        if (!first) json.append(",\n");
        first = false;
        json.append("    {\"node\": \"N").append(node.getNodeNumber())
            .append("\", \"function\": \"").append(escapeJson(node.getFunctionName()))
            .append("\"}");
      }
      json.append("\n  ]");
    } catch (Exception e) {
      missing.add("trace_locations: " + e.getMessage());
      json.append("  \"trace_locations\": null");
    }
  }

  private void dumpEdgeDetails(StringBuilder json, ARGPath allStatesTrace, List<String> missing) {
    try {
      json.append("  \"cfa_edges\": [\n");
      PathIterator it = allStatesTrace.pathIterator();
      boolean first = true;
      while (it.hasNext()) {
        CFANode loc = it.getLocation();
        CFAEdge edge = it.getOutgoingEdge();
        if (loc == null) { it.advance(); continue; }
        if (!first) json.append(",\n");
        first = false;
        json.append("    {\"node\": \"N").append(loc.getNodeNumber()).append("\"");
        if (edge != null) {
          json.append(", \"edge_line\": ").append(edge.getLineNumber());
          json.append(", \"edge_type\": \"").append(escapeJson(edge.getEdgeType().toString())).append("\"");
          try {
            json.append(", \"edge_code\": \"").append(escapeJson(edge.getDescription())).append("\"");
          } catch (Exception e) {
            json.append(", \"edge_code\": null");
          }
          if (edge instanceof CAssumeEdge assume) {
            try {
              json.append(", \"branch_condition\": \"").append(escapeJson(assume.getExpression().toString())).append("\"");
              json.append(", \"branch_truth\": ").append(assume.getTruthAssumption());
            } catch (Exception e) {
              json.append(", \"branch_condition\": null");
            }
          }
        } else {
          json.append(", \"edge_type\": \"null\"");
        }
        json.append("}");
        it.advance();
      }
      json.append("\n  ]");
    } catch (Exception e) {
      missing.add("cfa_edges: " + e.getMessage());
      json.append("  \"cfa_edges\": null");
    }
  }

  private void dumpBlockFormulas(StringBuilder json, BlockFormulas formulas, List<String> missing) {
    try {
      json.append("  \"block_formulas\": [\n");
      List<BooleanFormula> fms = formulas.getFormulas();
      boolean first = true;
      for (int i = 0; i < fms.size(); i++) {
        if (!first) json.append(",\n");
        first = false;
        String smt = fmgr.dumpFormula(fms.get(i)).toString();
        json.append("    {\"index\": ").append(i)
            .append(", \"smt\": \"").append(escapeJson(smt)).append("\"}");
      }
      json.append("\n  ]");
    } catch (Exception e) {
      missing.add("block_formulas: " + e.getMessage());
      json.append("  \"block_formulas\": null");
    }
  }

  private void dumpAbstractionStates(StringBuilder json, List<ARGState> abstractionStatesTrace, List<String> missing) {
    try {
      json.append("  \"abstraction_states\": [\n");
      boolean first = true;
      for (int i = 0; i < abstractionStatesTrace.size(); i++) {
        ARGState s = abstractionStatesTrace.get(i);
        CFANode node = AbstractStates.extractLocation(s);
        if (node == null) continue;
        if (!first) json.append(",\n");
        first = false;
        json.append("    {\"index\": ").append(i)
            .append(", \"node\": \"N").append(node.getNodeNumber())
            .append("\", \"function\": \"").append(escapeJson(node.getFunctionName()))
            .append("\"}");
      }
      json.append("\n  ]");
    } catch (Exception e) {
      missing.add("abstraction_states: " + e.getMessage());
      json.append("  \"abstraction_states\": null");
    }
  }

  private void dumpInterpolants(StringBuilder json, CounterexampleTraceInfo counterexample, List<String> missing) {
    try {
      if (!counterexample.isSpurious()) {
        json.append("  \"interpolants\": []");
        return;
      }
      json.append("  \"interpolants\": [\n");
      List<BooleanFormula> itps = counterexample.getInterpolants();
      boolean first = true;
      for (int i = 0; i < itps.size(); i++) {
        if (!first) json.append(",\n");
        first = false;
        String smt = fmgr.dumpFormula(itps.get(i)).toString();
        json.append("    {\"index\": ").append(i)
            .append(", \"smt\": \"").append(escapeJson(smt)).append("\"}");
      }
      json.append("\n  ]");
    } catch (Exception e) {
      missing.add("interpolants: " + e.getMessage());
      json.append("  \"interpolants\": null");
    }
  }

  private void dumpPrecision(StringBuilder json, ARGReachedSet pReached, List<String> missing) {
    try {
      json.append("  \"precision\": {\n");
      AbstractState firstState = pReached.asReachedSet().getFirstState();
      if (firstState == null) {
        json.append("    \"global_predicates\": []\n  }");
        return;
      }
      Precision currentPrec = pReached.asReachedSet().getPrecision(firstState);
      PredicatePrecision predPrec = Precisions.extractPrecisionByType(currentPrec, PredicatePrecision.class);
      if (predPrec == null) {
        json.append("    \"global_predicates\": []\n  }");
        return;
      }
      json.append("    \"global_predicates\": [\n");
      Set<AbstractionPredicate> globals = predPrec.getGlobalPredicates();
      boolean first = true;
      for (AbstractionPredicate ap : globals) {
        if (!first) json.append(",\n");
        first = false;
        try {
          String atom = fmgr.dumpFormula(ap.getSymbolicAtom()).toString();
          json.append("      {\"smt\": \"").append(escapeJson(atom)).append("\"}");
        } catch (Exception e) {
          json.append("      {\"smt\": null, \"error\": \"").append(escapeJson(e.getMessage())).append("\"}");
        }
      }
      json.append("\n    ],\n");
      json.append("    \"global_count\": ").append(globals.size()).append("\n  }");
    } catch (Exception e) {
      missing.add("precision: " + e.getMessage());
      json.append("  \"precision\": null");
    }
  }

  private void dumpCandidateFates(
      StringBuilder json,
      Map<CFANode, Set<BooleanFormula>> pendingCandidates,
      Map<CFANode, Set<BooleanFormula>> injectedPredicates,
      Map<CFANode, Set<BooleanFormula>> entailedPredicates,
      List<String> missing) {
    try {
      json.append("  \"candidate_fates\": {\n");

      dumpFateGroup(json, "entailed", entailedPredicates);
      json.append(",\n");

      dumpFateGroup(json, "abstraction_candidates", pendingCandidates);
      json.append(",\n");

      dumpFateGroup(json, "injected", injectedPredicates);

      json.append("\n  }");
    } catch (Exception e) {
      missing.add("candidate_fates: " + e.getMessage());
      json.append("  \"candidate_fates\": null");
    }
  }

  private void dumpFateGroup(StringBuilder json, String label, Map<CFANode, Set<BooleanFormula>> group) {
    json.append("    \"").append(label).append("\": [\n");
    int total = 0;
    boolean first = true;
    for (var entry : group.entrySet()) {
      CFANode node = entry.getKey();
      for (BooleanFormula bf : entry.getValue()) {
        if (!first) json.append(",\n");
        first = false;
        String text;
        try {
          text = fmgr.dumpFormula(bf).toString();
        } catch (Exception e) {
          text = "<dump error>";
        }
        json.append("      {\"node\": \"N").append(node.getNodeNumber())
            .append("\", \"smt\": \"").append(escapeJson(text)).append("\"}");
        total++;
      }
    }
    json.append("\n    ],\n    \"").append(label).append("_count\": ").append(total);
  }

  private void dumpMissingFields(StringBuilder json, List<String> missing) {
    json.append("  \"missing_fields\": [\n");
    if (missing.isEmpty()) {
      json.append("  ]");
      return;
    }
    boolean first = true;
    for (String m : missing) {
      if (!first) json.append(",\n");
      first = false;
      json.append("    \"").append(escapeJson(m)).append("\"");
    }
    json.append("\n  ]");
  }

  private static String escapeJson(String s) {
    if (s == null) return "";
    return s.replace("\\", "\\\\").replace("\"", "\\\"")
            .replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t");
  }
}
