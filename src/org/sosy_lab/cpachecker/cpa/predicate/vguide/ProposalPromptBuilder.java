// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import java.util.List;
import java.util.Locale;

/** Builds LLM prompts for spurious counterexamples (SAFE and BUG_HUNT profiles). */
public final class ProposalPromptBuilder {

  private final LoopHeadIndex loopHeadIndex;

  /**
   * Minimal prompt style (VGUIDE_PROMPT_MINIMAL=1): concise instructions per DeepSeek best
   * practices. The minimal branches intentionally paraphrase the full-mode strings (they are an
   * experiment variant, #89) — keep semantics in sync when editing either.
   */
  private final boolean minimalPrompt;

  public ProposalPromptBuilder(LoopHeadIndex loopHeadIndex) {
    this(loopHeadIndex, isMinimalPrompt());
  }

  ProposalPromptBuilder(LoopHeadIndex loopHeadIndex, boolean minimalPrompt) {
    this.loopHeadIndex = loopHeadIndex;
    this.minimalPrompt = minimalPrompt;
  }

  static boolean isMinimalPrompt() {
    String v = System.getenv("VGUIDE_PROMPT_MINIMAL");
    if (v == null) {
      return false;
    }
    return switch (v.trim().toLowerCase(Locale.ROOT)) {
      case "1", "true", "on", "yes", "enabled", "y" -> true;
      default -> false;
    };
  }

  static int rulesCharCount(PredicateBudget budget, boolean minimalPrompt) {
    return buildSystemMessage(budget, minimalPrompt).length();
  }

  public PromptMessages buildPrompt(
      ContextPack pack, PredicateBudget budget, PromptProfile profile, int refinementIndex) {
    return buildPrompt(pack, budget, profile, refinementIndex, "");
  }

  public PromptMessages buildPrompt(
      ContextPack pack,
      PredicateBudget budget,
      PromptProfile profile,
      int refinementIndex,
      String ceHistory) {
    return buildPrompt(pack, budget, profile, refinementIndex, ceHistory, "", "");
  }

  public PromptMessages buildPrompt(
      ContextPack pack,
      PredicateBudget budget,
      PromptProfile profile,
      int refinementIndex,
      String ceHistory,
      String refinementOutcomes,
      String nativePredicateContext) {
    String user =
        buildSharedUserPrefix(pack)
            + buildSourceBlock(pack)
            + buildProfileBlock(pack, profile, refinementIndex)
            + buildDynamicTail(pack, ceHistory, refinementOutcomes, nativePredicateContext);
    return new PromptMessages(buildSystemMessage(budget, minimalPrompt), user);
  }

  public PromptMessages buildRepair(
      ContextPack pack,
      List<String> rejectedPredicates,
      PredicateBudget budget,
      PromptProfile profile,
      int refinementIndex) {
    return buildRepair(pack, rejectedPredicates, budget, profile, refinementIndex, "", "", "");
  }

  public PromptMessages buildRepair(
      ContextPack pack,
      List<String> rejectedPredicates,
      PredicateBudget budget,
      PromptProfile profile,
      int refinementIndex,
      String ceHistory,
      String refinementOutcomes,
      String nativePredicateContext) {
    String user =
        buildSharedUserPrefix(pack)
            + buildSourceBlock(pack)
            + buildProfileBlock(pack, profile, refinementIndex)
            + buildDynamicTail(pack, ceHistory, refinementOutcomes, nativePredicateContext)
            + buildRepairTail(rejectedPredicates, profile);
    return new PromptMessages(buildSystemMessage(budget, minimalPrompt), user);
  }

  /** Legacy string API for tests. */
  public String buildFirstSpurious(ContextPack pack, PredicateBudget budget) {
    return buildPrompt(pack, budget, PromptProfile.SAFE, 1).fullText();
  }

  public String buildLaterSpurious(ContextPack pack, PredicateBudget budget) {
    return buildPrompt(pack, budget, PromptProfile.SAFE, 2).fullText();
  }

  private static String buildSystemMessage(PredicateBudget budget, boolean minimalPrompt) {
    if (minimalPrompt) {
      return "You help a CEGAR verifier. Propose SMT-LIB2 predicates (prefix notation, each starts"
                 + " with '(').\n"
                 + "Source vars only. Prefer bv ops: bvsge/bvslt/bvsle/bvsgt/bvadd/bvsub.\n"
                 + "No select/store, no |main::|, no @suffix, no .def_N, no quantifiers, no"
                 + " bvshl/lshr/ashr; arrays as a[i].\n"
          + buildJsonContract(budget);
    }
    return "You help a CEGAR-based predicate abstraction verifier.\n"
        + "Propose candidate abstraction predicates in SMT-LIB2 prefix notation.\n"
        + syntaxRules()
        + buildJsonContract(budget);
  }

  private String buildSharedUserPrefix(ContextPack pack) {
    return loopHeadIndex.formatForPrompt()
        + "\n"
        + VarContractBuilder.formatForPrompt(pack.varContract())
        + SourceVariableHints.formatForPrompt(pack.sourceCode(), pack.varContract());
  }

  private static String buildSourceBlock(ContextPack pack) {
    return "\nSource code:\n" + pack.sourceCode() + "\n";
  }

  private String buildProfileBlock(ContextPack pack, PromptProfile profile, int refinementIndex) {
    String assertionLine = formatAssertionLine(pack.assertion(), profile);
    String role = profileRole(profile);
    String task = refinementIndex == 1 ? profileFirstTask(profile) : profileLaterTask(profile);
    return assertionLine + "\n" + role + "\n" + task;
  }

  private static String buildDynamicTail(
      ContextPack pack,
      String ceHistory,
      String refinementOutcomes,
      String nativePredicateContext) {
    String historyBlock =
        ceHistory == null || ceHistory.isBlank()
            ? ""
            : "\nPRIOR CE HISTORY (bounded, read-only):\n" + ceHistory;
    String outcomeBlock =
        refinementOutcomes == null || refinementOutcomes.isBlank()
            ? ""
            : "\nREFINEMENT PROGRESS (read-only):\n" + refinementOutcomes;
    String nativeBlock =
        nativePredicateContext == null || nativePredicateContext.isBlank()
            ? ""
            : "\nNATIVE CEGAR PRECISION (read-only):\n" + nativePredicateContext;
    return "\nSTRUCTURED SPURIOUS COUNTEREXAMPLE (read-only):\n"
        + pack.ceSummary()
        + "\n"
        + historyBlock
        + outcomeBlock
        + nativeBlock;
  }

  private static String formatAssertionLine(String assertion, PromptProfile profile) {
    if (assertion.isEmpty()) {
      return "";
    }
    if (profile == PromptProfile.BUG_HUNT) {
      return "Assertion (may FAIL on real paths): " + assertion + "\n";
    }
    return "Target assertion: " + assertion + "\n";
  }

  private String profileRole(PromptProfile profile) {
    if (minimalPrompt) {
      return profile == PromptProfile.BUG_HUNT
          ? "Goal: reach or refine toward assertion FAILURE if reachable.\n"
          : "Goal: split spurious paths; strengthen the abstraction.\n";
    }
    if (profile == PromptProfile.BUG_HUNT) {
      return "Goal: help the verifier reach or refine toward assertion FAILURE if reachable.\n";
    }
    return "Goal: split spurious counterexample paths and strengthen safe abstraction.\n";
  }

  private String profileFirstTask(PromptProfile profile) {
    if (minimalPrompt) {
      return profile == PromptProfile.BUG_HUNT
          ? "First spurious CE: propose predicates distinguishing states toward assertion FAILURE"
                + " (not only safe-proofs).\n"
          : "First spurious CE: propose loop-carried relations, guards, bounds, assertion"
                + " variables.\n";
    }
    if (profile == PromptProfile.BUG_HUNT) {
      return """
      This is the FIRST spurious counterexample in this analysis.
      Propose predicates that distinguish states that can lead to assertion failure.
      Do NOT only propose predicates that imply the assertion always holds.
      """;
    }
    return """
    This is the FIRST spurious counterexample in this analysis.
    Propose abstraction predicates that help split similar spurious paths.
    Focus on loop-carried relations, guards, bounds, and assertion variables.
    """;
  }

  private String profileLaterTask(PromptProfile profile) {
    if (minimalPrompt) {
      return profile == PromptProfile.BUG_HUNT
          ? "More predicates toward failure states in the CE summary (not only safe-proofs).\n"
          : "More predicates to strengthen the abstraction.\n";
    }
    if (profile == PromptProfile.BUG_HUNT) {
      return """
      Propose additional predicates toward assertion failure states shown in the CE summary.
      Do NOT only strengthen predicates that imply the assertion always holds.
      """;
    }
    return "Propose additional predicates to strengthen abstraction.\n";
  }

  private static String buildRepairTail(List<String> rejectedPredicates, PromptProfile profile) {
    String hint =
        profile == PromptProfile.BUG_HUNT
            ? "Rejected predicates may have been too aligned with proving safe; try failing-state"
                  + " predicates from the CE summary.\n"
            : "";
    return "\nYour previous reply included REJECTED predicates: "
        + rejectedPredicates
        + "\n"
        + hint
        + "Regenerate JSON only. Keep array reads in the a[i] C-syntax form; do not write"
        + " select/store or SSA names.\n";
  }

  private static String syntaxRules() {
    return """
    RULES (violations are discarded automatically):
    - Use ONLY source variable names from the contract / allowed list.
    - SMT-LIB2 prefix notation; each predicate must start with '('.
    - Prefer bitvector ops for 32-bit ints: bvsge, bvslt, bvsle, bvsgt, bvadd, bvsub, = .
    - Do NOT use: |main::...|, @suffix, .def_N, select, store, quantifiers, bvshl/lshr/ashr.
    - Arrays: write element reads in C syntax a[i] (a = array name from the contract,
      i = index expression over source variables, e.g. b[4*j+1]); the system translates
      them. NEVER write select/store or @versioned names yourself.
    """;
  }

  private static String buildJsonContract(PredicateBudget budget) {
    return """

    Output ONLY valid JSON (no markdown, no commentary):
    {"schema_version":"loop-head-candidate-v1","candidates":[]}
    - Every candidate MUST name a loop head from the LOOP HEADS list (\"N*\" label).
    - Use \"loop_heads\":[...] only when the predicate is meaningful at every named head.
    - Candidates without a loop head are discarded; Java never broadcasts predicates.
    - role (optional): initiation, supporting, relational, or bound.
    CANDIDATE POLICY (array order = priority, best first):
    - Return at most %d candidates; an empty candidates array is valid. Stop when no new grounded split remains.
    - Add a candidate only if source, transition, assertion, or counterexample evidence supports it and it
      separates a relevant state pair not already separated by an earlier candidate at that head.
    - Logically equivalent predicates and logical negations are the same split, including algebraic rewrites, swapped operands, and shifted integer bounds. Keep only the better-ranked representative.
    - Do not enumerate syntax, constants, roles, or loop heads. Name multiple heads only when evidence
      supports the predicate independently at every named head.
    - A split may be initiation-only, exit-only, threshold, violation-state, or path-specific; it need not
      hold at every loop-head visit.
    """
        .formatted(budget.maxPerCall());
  }
}
