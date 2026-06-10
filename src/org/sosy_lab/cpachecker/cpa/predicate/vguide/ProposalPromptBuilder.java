// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import java.util.List;

/** Builds LLM prompts for spurious counterexamples (SAFE and BUG_HUNT profiles). */
public final class ProposalPromptBuilder {

  private final LoopHeadIndex loopHeadIndex;

  public ProposalPromptBuilder(LoopHeadIndex loopHeadIndex) {
    this.loopHeadIndex = loopHeadIndex;
  }

  static int rulesCharCount(PredicateBudget budget) {
    return buildSystemMessage(budget).length();
  }

  public PromptMessages buildPrompt(
      ContextPack pack, PredicateBudget budget, PromptProfile profile, int refinementIndex) {
    String user =
        buildSharedUserPrefix(pack)
            + buildSourceBlock(pack)
            + buildProfileBlock(pack, profile, refinementIndex)
            + buildDynamicTail(pack, budget, profile);
    return new PromptMessages(buildSystemMessage(budget), user);
  }

  public PromptMessages buildRepair(
      ContextPack pack,
      List<String> rejectedPredicates,
      PredicateBudget budget,
      PromptProfile profile,
      int refinementIndex) {
    String user =
        buildSharedUserPrefix(pack)
            + buildSourceBlock(pack)
            + buildProfileBlock(pack, profile, refinementIndex)
            + buildDynamicTail(pack, budget, profile)
            + buildRepairTail(rejectedPredicates, profile);
    return new PromptMessages(buildSystemMessage(budget), user);
  }

  /** Legacy string API for tests. */
  public String buildFirstSpurious(ContextPack pack, PredicateBudget budget) {
    return buildPrompt(pack, budget, PromptProfile.SAFE, 1).fullText();
  }

  public String buildLaterSpurious(ContextPack pack, PredicateBudget budget) {
    return buildPrompt(pack, budget, PromptProfile.SAFE, 2).fullText();
  }

  private static String buildSystemMessage(PredicateBudget budget) {
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
    String task =
        refinementIndex == 1 ? profileFirstTask(profile) : profileLaterTask(profile);
    return assertionLine + "\n" + role + "\n" + task + profileExamples(pack.sourceCode(), pack.assertion(), profile);
  }

  private static String buildDynamicTail(ContextPack pack, PredicateBudget budget, PromptProfile profile) {
    return "\nSPURIOUS CE SUMMARY (source variable names only, read-only):\n"
        + pack.ceSummary()
        + "\n"
        + predicateBudgetBlock(budget, profile);
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

  private static String profileRole(PromptProfile profile) {
    if (profile == PromptProfile.BUG_HUNT) {
      return "Goal: help the verifier reach or refine toward assertion FAILURE if reachable.\n";
    }
    return "Goal: split spurious counterexample paths and strengthen safe abstraction.\n";
  }

  private static String profileFirstTask(PromptProfile profile) {
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

  private static String profileLaterTask(PromptProfile profile) {
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
            ? "Rejected predicates may have been too aligned with proving safe; try failing-state predicates from the CE summary.\n"
            : "";
    return "\nYour previous reply included REJECTED predicates: "
        + rejectedPredicates
        + "\n"
        + hint
        + "Regenerate JSON only. Remove array subscripts, internal SSA names, select/store.\n";
  }

  private static String syntaxRules() {
    return """
      RULES (violations are discarded automatically):
      - Use ONLY source variable names from the contract / allowed list.
      - SMT-LIB2 prefix notation; each predicate must start with '('.
      - Prefer bitvector ops for 32-bit ints: bvsge, bvslt, bvsle, bvsgt, bvadd, bvsub, = .
      - Do NOT use: |main::...|, @suffix, .def_N, select, store, quantifiers, bvshl/lshr/ashr.
      - Do NOT use C syntax: A[i], *p, struct fields.
      """;
  }

  private static String predicateBudgetBlock(PredicateBudget budget, PromptProfile profile) {
    int min = budget.minPerCall();
    int max = budget.maxPerCall();
    if (profile == PromptProfile.BUG_HUNT) {
      return """
        PREDICATE BUDGET (single API response — array order = priority, best first):
        - Return between %d and %d predicates (aim for at least %d strong, mutually non-redundant candidates).
        - Prefer DISTINCT roles, e.g.:
          (1) assertion-failure or violation-state discriminator
          (2) loop-carried relation or guard-tight bound on the spurious path
          (3) optional spurious-path splitter (not proving assertion always true)
        - Do NOT pad to %d with obvious bounds or predicates that only imply the assertion holds.
        """
          .formatted(min, max, min, max);
    }
    return """
      PREDICATE BUDGET (single API response — array order = priority, best first):
      - Return between %d and %d predicates (aim for at least %d strong, mutually non-redundant candidates).
      - Prefer DISTINCT roles (one per line of thought), e.g.:
        (1) loop-carried relation or guard-tight bound (non-trivial)
        (2) cross-variable relation tied to the assertion or spurious path
        (3) optional strengthener supporting the assertion or cross-loop coupling
      - Do NOT pad to %d with obvious bounds (e.g. i>=0 in for(i=0;...)) or near-duplicate inequalities.
      - Cover assertion support and cross-loop relations when multiple loops exist.
      """
        .formatted(min, max, min, max);
  }

  private static String profileExamples(String source, String assertion, PromptProfile profile) {
    if (profile == PromptProfile.BUG_HUNT) {
      if (assertion.contains("x") && source.contains("x = 0")) {
        return """

            Examples (violation / assert-failure states):
              (= x (_ bv0 32))
              (not (= x (_ bv1 32)))
              (= y (_ bv1024 32))
            """;
      }
      if (assertion.contains("bvand") || assertion.contains("bvurem")) {
        return """

            Examples (parity violation states):
              (= (bvand x (_ bv1 32)) (_ bv0 32))
              (not (= (bvurem x (_ bv2 32)) (_ bv0 32)))
            """;
      }
      return """

          Examples (assertion-failure oriented):
            (not (= x (_ bv1 32)))
            (= x (_ bv0 32))
          """;
    }
    return taskExamplesSafe(source, assertion);
  }

  private static String taskExamplesSafe(String source, String assertion) {
    if (source.contains("int k") && source.contains("int i") && source.contains("int n")) {
      return """

          Examples (scalar loop / counter — match your assertion):
            (bvsge i (_ bv0 32))
            (bvsge k (_ bv0 32))
            (bvslt i n)
            (= k i)
            (bvsle i n)
          """;
    }
    if (SourceVariableHints.hasArrayDecl(source)) {
      return """

          Examples (array search loop — index scalars ONLY):
            (bvsge i (_ bv0 32))
            (bvsle i (_ bv1024 32))
            (bvslt i (_ bv1024 32))
          NEVER output: (= A[i] 0) or any predicate mentioning array names.
          """;
    }
    if (assertion.contains("i") && assertion.contains("j")) {
      return """

          Examples (multi-index / string style):
            (bvsge i (_ bv0 32))
            (bvsge j (_ bv0 32))
            (bvslt i (_ bv100 32))
          """;
    }
    if (assertion.contains("bvand") || assertion.contains("bvurem")) {
      return """

          Examples (parity / modular):
            (= (bvand x (_ bv1 32)) (_ bv1 32))
            (not (= (bvurem x (_ bv2 32)) (_ bv0 32)))
            (bvsgt x (_ bv0 32))
          """;
    }
    return "";
  }

  private static String buildJsonContract(PredicateBudget budget) {
    return """

        Output ONLY valid JSON (no markdown, no commentary):
        {"predicates": ["(bvsge i (_ bv0 32))", "(bvslt i n)"]}
        Between %d and %d items. Do NOT use N* location keys; Java binds predicates to all loop heads.
        """
        .formatted(budget.minPerCall(), budget.maxPerCall());
  }

}
