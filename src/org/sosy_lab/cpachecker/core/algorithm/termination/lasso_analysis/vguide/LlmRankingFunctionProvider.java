// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-FileCopyrightText: 2026 Dirk Beyer <https://www.sosy-lab.org>
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.core.algorithm.termination.lasso_analysis.vguide;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.function.Supplier;
import java.util.logging.Level;
import org.checkerframework.checker.nullness.qual.Nullable;
import org.sosy_lab.common.log.LogManager;
import org.sosy_lab.cpachecker.cfa.CFA;
import org.sosy_lab.cpachecker.cfa.ast.c.CBinaryExpressionBuilder;
import org.sosy_lab.cpachecker.cfa.ast.c.CVariableDeclaration;
import org.sosy_lab.cpachecker.core.algorithm.termination.lasso_analysis.LassoAnalysisResult;
import org.sosy_lab.cpachecker.core.algorithm.termination.lasso_analysis.RankingRelation;
import org.sosy_lab.cpachecker.core.algorithm.termination.lasso_analysis.construction.LassoBuilder.StemAndLoop;
import org.sosy_lab.cpachecker.core.algorithm.termination.lasso_analysis.vguide.RankingFunctionVerifier.Candidate;
import org.sosy_lab.cpachecker.core.algorithm.termination.lasso_analysis.vguide.RankingTermParser.LinearTerm;
import org.sosy_lab.cpachecker.cpa.predicate.vguide.PredicateProposalClient;
import org.sosy_lab.cpachecker.cpa.predicate.vguide.PromptMessages;
import org.sosy_lab.cpachecker.util.LoopStructure.Loop;
import org.sosy_lab.cpachecker.util.predicates.smt.FormulaManagerView;
import org.sosy_lab.java_smt.api.BooleanFormula;
import org.sosy_lab.java_smt.api.NumeralFormula.IntegerFormula;
import org.sosy_lab.java_smt.api.ProverEnvironment;
import org.sosy_lab.java_smt.api.SolverException;

/**
 * VGuide fallback for termination: when LassoRanker's template synthesis fails for a lasso, asks an
 * LLM for candidate ranking functions (with optional supporting invariants), verifies each with
 * {@link RankingFunctionVerifier}, and returns the first verified one as a {@link RankingRelation}.
 *
 * <p>Enabled by environment {@code VGUIDE_TERMINATION_RANKING=on} (and requires {@code
 * DEEPSEEK_API_KEY}); otherwise {@link #isEnabled()} is false and {@link #tryProve} is never called.
 * The LLM is consulted at most {@code VGUIDE_TERMINATION_RANKING_MAX_PER_LOOP} times per loop and
 * {@code VGUIDE_TERMINATION_RANKING_MAX_TOTAL} times per run.
 */
public final class LlmRankingFunctionProvider {

  private static final ObjectMapper JSON = new ObjectMapper();

  private final LogManager logger;
  private final FormulaManagerView fmgr;
  private final RankingFunctionVerifier verifier;
  private final CBinaryExpressionBuilder cBuilder;
  private final @Nullable PredicateProposalClient client;
  private final CFA cfa;
  private @Nullable String sourceCode; // read lazily on first fire, then cached
  private final int maxPerLoop;
  private final int maxTotal;
  private final boolean repairEnabled;

  private final Map<Loop, Integer> callsPerLoop = new HashMap<>();
  private int totalCalls = 0;
  private int verifiedWins = 0;

  public LlmRankingFunctionProvider(
      LogManager pLogger,
      FormulaManagerView pFmgr,
      Supplier<ProverEnvironment> pProverSupplier,
      CFA pCfa) {
    logger = pLogger;
    fmgr = pFmgr;
    verifier = new RankingFunctionVerifier(pFmgr, pProverSupplier);
    cBuilder = new CBinaryExpressionBuilder(pCfa.getMachineModel(), pLogger);
    maxPerLoop = readPositiveIntEnv("VGUIDE_TERMINATION_RANKING_MAX_PER_LOOP", 1);
    maxTotal = readPositiveIntEnv("VGUIDE_TERMINATION_RANKING_MAX_TOTAL", 200);
    // Repair (verify->re-prompt) is OFF by default: on the 56-target subset it was neutral (+0),
    // because the dominant remaining failure is INITIATION_FAILED — the LLM cannot propose
    // loop-entry-valid invariants without the stem/precondition in context (the next lever).
    // Kept as opt-in scaffolding (VGUIDE_TERMINATION_RANKING_REPAIR=on) for that follow-up.
    repairEnabled = "on".equalsIgnoreCase(System.getenv("VGUIDE_TERMINATION_RANKING_REPAIR"));
    client = enabledFromEnv() ? PredicateProposalClient.createOptional(pLogger) : null;
    cfa = pCfa;
    logger.log(
        Level.INFO,
        "VGuide termination ranking hook:",
        client != null ? "ENABLED" : "disabled (no env flag or API key)");
  }

  /** Whether the hook is active (env flag set and API key present). */
  public boolean isEnabled() {
    return client != null;
  }

  public int getVerifiedWins() {
    return verifiedWins;
  }

  /**
   * Tries to prove termination of the given lasso via an LLM-proposed, SMT-verified ranking
   * function. Returns an unknown result if disabled, capped, the LLM call fails, or no candidate
   * verifies. Never throws on LLM/parse errors — a failure simply yields unknown.
   */
  public LassoAnalysisResult tryProve(
      Loop pLoop, StemAndLoop pStemAndLoop, Set<CVariableDeclaration> pRelevantVariables)
      throws InterruptedException {
    if (client == null || totalCalls >= maxTotal) {
      return LassoAnalysisResult.unknown();
    }
    int loopCalls = callsPerLoop.getOrDefault(pLoop, 0);
    if (loopCalls >= maxPerLoop) {
      return LassoAnalysisResult.unknown();
    }
    callsPerLoop.put(pLoop, loopCalls + 1);
    totalCalls++;

    Map<String, String> nameToQualified = new LinkedHashMap<>();
    Map<String, CVariableDeclaration> declsByQualified = new LinkedHashMap<>();
    for (CVariableDeclaration v : pRelevantVariables) {
      declsByQualified.put(v.getQualifiedName(), v);
      nameToQualified.put(v.getQualifiedName(), v.getQualifiedName());
      nameToQualified.putIfAbsent(v.getOrigName(), v.getQualifiedName());
      nameToQualified.putIfAbsent(v.getName(), v.getQualifiedName());
    }
    if (declsByQualified.isEmpty()) {
      return LassoAnalysisResult.unknown();
    }

    logger.logf(Level.INFO, "VGuide termination FIRED for %s", pLoop);
    String content;
    try {
      content = client.propose(buildPrompt(pLoop, pRelevantVariables));
    } catch (IOException e) {
      logger.logUserException(Level.INFO, e, "VGuide termination FIRED but LLM call failed");
      return LassoAnalysisResult.unknown();
    }

    RankingTermParser parser = new RankingTermParser(fmgr, nameToQualified);
    RankingRelationFactory factory = new RankingRelationFactory(fmgr, cBuilder, declsByQualified);

    List<Failure> failures = new ArrayList<>();
    RankingRelation rr = tryCandidates(content, parser, factory, pStemAndLoop, pLoop, "first", failures);
    if (rr != null) {
      return LassoAnalysisResult.fromTerminationArgument(rr);
    }

    // verify -> repair: feed the exact failing verification conditions back once. Most first-round
    // failures are BOUNDED/INITIATION (the LLM gave a measure but not the invariant that bounds it),
    // which the verifier pinpoints precisely, so a single targeted repair is the cheapest lever.
    if (repairEnabled && !failures.isEmpty()) {
      String repairContent = null;
      try {
        repairContent = client.propose(buildRepairPrompt(pLoop, pRelevantVariables, failures));
      } catch (IOException e) {
        logger.logUserException(Level.INFO, e, "VGuide termination repair call failed");
      }
      if (repairContent != null) {
        RankingRelation rr2 =
            tryCandidates(repairContent, parser, factory, pStemAndLoop, pLoop, "repair", failures);
        if (rr2 != null) {
          return LassoAnalysisResult.fromTerminationArgument(rr2);
        }
      }
    }
    logger.logf(Level.INFO, "VGuide termination NO WIN for %s: failures=%s", pLoop, failures);
    return LassoAnalysisResult.unknown();
  }

  /** A candidate that failed verification, kept for the repair prompt and diagnostics. */
  private record Failure(String rankingFunction, String supportingInvariant, String reason) {
    @Override
    public String toString() {
      return reason + "{" + rankingFunction + " | " + supportingInvariant + "}";
    }
  }

  /**
   * Parses + verifies the candidates in one LLM response; on the first verified candidate builds
   * and returns the ranking relation (logging the win). Otherwise returns {@code null} and appends
   * each failure (with the failing verification condition) to {@code failures}.
   */
  private @Nullable RankingRelation tryCandidates(
      String content,
      RankingTermParser parser,
      RankingRelationFactory factory,
      StemAndLoop sl,
      Loop loop,
      String round,
      List<Failure> failures)
      throws InterruptedException {
    for (Proposal proposal : parseCandidates(content)) {
      String rankStr = proposal.rankingFunction();
      String invStr = proposal.supportingInvariant();
      LinearTerm f = parser.parseLinear(rankStr);
      if (f == null || f.coefficients().isEmpty()) {
        failures.add(new Failure(rankStr, invStr, "PARSE_FAIL"));
        continue; // unparseable, non-linear, or constant (never a ranking function)
      }
      BooleanFormula invariant = parser.parseInvariant(invStr);
      if (invariant == null) {
        failures.add(new Failure(rankStr, invStr, "INV_PARSE_FAIL"));
        continue;
      }
      IntegerFormula fFormula = f.toFormula(fmgr.getIntegerFormulaManager(), "");
      RankingFunctionVerifier.Outcome outcome;
      try {
        outcome =
            verifier.verify(
                new Candidate(fFormula, invariant),
                sl.getStem(),
                sl.getLoop(),
                sl.getLoopInVars(),
                sl.getLoopOutVars());
      } catch (SolverException e) {
        failures.add(new Failure(rankStr, invStr, "VERIFY_ERROR"));
        continue;
      }
      if (outcome != RankingFunctionVerifier.Outcome.VALID) {
        failures.add(new Failure(rankStr, invStr, outcome.toString()));
        continue;
      }
      boolean hasInvariant = !fmgr.getBooleanFormulaManager().isTrue(invariant);
      RankingRelation rr = factory.create(f, invariant, hasInvariant);
      if (rr == null) {
        failures.add(new Failure(rankStr, invStr, "RELATION_BUILD_FAIL"));
        continue;
      }
      verifiedWins++;
      logger.logf(
          Level.INFO,
          "VGuide termination: verified LLM ranking function %s (invariant: %s) [%s] for %s",
          rankStr,
          hasInvariant ? invStr : "none",
          round,
          loop);
      return rr;
    }
    return null;
  }

  // ---- prompt -----------------------------------------------------------------

  private record Proposal(String rankingFunction, String supportingInvariant) {}

  private PromptMessages buildPrompt(Loop pLoop, Set<CVariableDeclaration> pRelevantVariables) {
    String user =
        "Source code:\n"
            + sourceCode()
            + "\n\nProve termination of the loop in function: "
            + loopFunction(pLoop)
            + "\nVariables you may use: "
            + varList(pRelevantVariables)
            + "\nReturn only the JSON object.";
    return new PromptMessages(systemPromptText(), user);
  }

  private PromptMessages buildRepairPrompt(
      Loop pLoop, Set<CVariableDeclaration> pRelevantVariables, List<Failure> failures) {
    StringBuilder fb = new StringBuilder();
    for (Failure f : failures) {
      fb.append("\n  - ranking_function=")
          .append(f.rankingFunction())
          .append("  supporting_invariant=")
          .append(f.supportingInvariant())
          .append("  -> ")
          .append(f.reason());
    }
    String user =
        "Source code:\n"
            + sourceCode()
            + "\n\nProve termination of the loop in function: "
            + loopFunction(pLoop)
            + "\nVariables you may use: "
            + varList(pRelevantVariables)
            + "\n\nYour previous candidates FAILED verification:"
            + fb
            + "\n\nFix the issues and propose NEW candidates as JSON:"
            + "\n- BOUNDED_FAILED: the measure is not provably >= 0 on this loop. Add a"
            + " supporting_invariant that establishes a lower bound (often the loop guard), or pick a"
            + " measure that is non-negative."
            + "\n- INITIATION_FAILED: your supporting_invariant does not hold when the loop is first"
            + " entered; weaken it to something the code establishes before the loop."
            + "\n- CONSECUTION_FAILED: your supporting_invariant is not preserved by the loop body."
            + "\n- DECREASE_FAILED: the measure does not strictly decrease each iteration; choose"
            + " another.\nReturn only the JSON object.";
    return new PromptMessages(systemPromptText(), user);
  }

  private static String varList(Set<CVariableDeclaration> vars) {
    StringBuilder sb = new StringBuilder();
    for (CVariableDeclaration v : vars) {
      if (sb.length() > 0) {
        sb.append(", ");
      }
      sb.append(v.getOrigName());
    }
    return sb.toString();
  }

  private static String loopFunction(Loop loop) {
    return loop.getLoopHeads().isEmpty()
        ? "(unknown)"
        : loop.getLoopHeads().iterator().next().getFunctionName();
  }

  private static String systemPromptText() {
    return """
        You are a termination-analysis assistant. Given C source code and a target loop, propose \
        candidate RANKING FUNCTIONS that prove the loop terminates. A ranking function f maps the \
        program state to an integer that is (a) bounded below by 0 and (b) strictly decreases on \
        every loop iteration. If f only decreases under a loop invariant, also give that invariant \
        (which must be inductive). Reply with ONLY a JSON object.

        Express f and invariants as prefix S-expressions using ONLY these constructs: integer \
        literals; the given variable names; (+ a b ...), (- a b), (- a), (* c a) where c is an \
        integer literal (multiplication must be linear). Invariants additionally allow \
        (and ...), (or ...), (not a), and relations (>= a b) (<= a b) (> a b) (< a b) (= a b). \
        Keep everything LINEAR and use ONLY the listed variable names.

        JSON schema:
        {"candidates":[{"ranking_function":"(- n i)","supporting_invariant":"(>= y 1)"}]}
        Use "true" for supporting_invariant when none is needed. Give 1 to 4 candidates, best first.""";
  }

  private Iterable<Proposal> parseCandidates(String content) {
    java.util.List<Proposal> out = new java.util.ArrayList<>();
    try {
      JsonNode root = JSON.readTree(content);
      JsonNode candidates = root.path("candidates");
      if (candidates.isArray()) {
        for (JsonNode c : candidates) {
          addProposal(out, c);
        }
      } else if (root.has("ranking_function")) {
        addProposal(out, root);
      }
    } catch (IOException e) {
      logger.logUserException(Level.FINE, e, "VGuide termination: bad LLM JSON");
    }
    return out;
  }

  private static void addProposal(java.util.List<Proposal> out, JsonNode c) {
    JsonNode rank = c.path("ranking_function");
    if (rank.isTextual() && !rank.asText().isBlank()) {
      String inv = c.path("supporting_invariant").asText("true");
      out.add(new Proposal(rank.asText(), inv));
    }
  }

  // ---- env / source -----------------------------------------------------------

  /** Static env check so callers can skip constructing the provider entirely when disabled. */
  public static boolean isEnabledByEnv() {
    return enabledFromEnv();
  }

  private static boolean enabledFromEnv() {
    String v = System.getenv("VGUIDE_TERMINATION_RANKING");
    if (v == null) {
      return false;
    }
    return switch (v.toLowerCase(Locale.ROOT)) {
      case "on", "true", "enabled", "1" -> true;
      default -> false;
    };
  }

  /** Reads (and caches) the source only on first use — never on tasks where the hook never fires. */
  private String sourceCode() {
    if (sourceCode == null) {
      sourceCode = readSource(cfa);
    }
    return sourceCode;
  }

  private String readSource(CFA pCfa) {
    StringBuilder sb = new StringBuilder();
    try {
      for (Path f : pCfa.getFileNames()) {
        sb.append(Files.readString(f)).append('\n');
      }
    } catch (IOException e) {
      logger.logUserException(Level.FINE, e, "VGuide termination: could not read source");
    }
    return sb.toString();
  }

  private static int readPositiveIntEnv(String name, int defaultValue) {
    String v = System.getenv(name);
    if (v == null || v.isBlank()) {
      return defaultValue;
    }
    try {
      int parsed = Integer.parseInt(v);
      return parsed > 0 ? parsed : defaultValue;
    } catch (NumberFormatException e) {
      return defaultValue;
    }
  }
}
