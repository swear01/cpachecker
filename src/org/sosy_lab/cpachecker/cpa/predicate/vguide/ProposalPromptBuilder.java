// This file is part of CPAchecker,
// a tool for configurable software verification:
// https://cpachecker.sosy-lab.org
//
// SPDX-License-Identifier: Apache-2.0

package org.sosy_lab.cpachecker.cpa.predicate.vguide;

import java.util.List;

/** Builds LLM prompts for first and later spurious counterexamples. */
public final class ProposalPromptBuilder {

  private final LoopHeadIndex loopHeadIndex;
  private final PredicateBudget budget;

  public ProposalPromptBuilder(LoopHeadIndex loopHeadIndex, PredicateBudget budget) {
    this.loopHeadIndex = loopHeadIndex;
    this.budget = budget;
  }

  static int rulesCharCount(PredicateBudget budget) {
    return syntaxRules().length() + predicateBudgetBlock(budget).length();
  }

  public String buildFirstSpurious(ContextPack pack) {
    return commonHeader(pack)
        + """

        This is the FIRST spurious counterexample in this analysis.
        Propose abstraction predicates that help split similar spurious paths.
        Focus on loop-carried relations, guards, bounds, and assertion variables.
        """
        + buildOutputContract();
  }

  public String buildLaterSpurious(ContextPack pack) {
    return commonHeader(pack)
        + "\nSpurious counterexample summary:\n"
        + pack.traceSummary()
        + "\nPropose additional predicates to strengthen abstraction.\n"
        + buildOutputContract();
  }

  private String commonHeader(ContextPack pack) {
    String assertionPart =
        pack.assertion().isEmpty() ? "" : "Target assertion: " + pack.assertion() + "\n";
    return "You are helping a CEGAR-based predicate abstraction verifier.\n"
        + "Propose candidate abstraction predicates in SMT-LIB2 prefix notation.\n"
        + assertionPart
        + "\n"
        + loopHeadIndex.formatForPrompt()
        + "\n"
        + VarContractBuilder.formatForPrompt(pack.varContract())
        + SourceVariableHints.formatForPrompt(pack.sourceCode(), pack.varContract())
        + syntaxRules()
        + predicateBudgetBlock(budget)
        + taskExamples(pack.sourceCode(), pack.assertion())
        + "\nSource code:\n"
        + pack.sourceCode();
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

  private static String predicateBudgetBlock(PredicateBudget budget) {
    int min = budget.minPerCall();
    int max = budget.maxPerCall();
    return """
      PREDICATE BUDGET (single API response — array order = priority, best first):
      - Return between %d and %d predicates. Aim for %d–%d STRONG, mutually non-redundant candidates.
      - Prefer DISTINCT roles (one per line of thought), e.g.:
        (1) loop-carried relation or guard-tight bound (non-trivial)
        (2) cross-variable relation tied to the assertion or spurious path
        (3) optional strengthener only if clearly not implied by the loop header/guards
      - Do NOT pad to %d with obvious bounds (e.g. i>=0 in for(i=0;...)) or near-duplicate inequalities.
      - If fewer than %d strong candidates exist, return fewer rather than weak fillers.
      """
        .formatted(min, max, min, max, max, min);
  }

  private static String taskExamples(String source, String assertion) {
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
    return "";
  }

  public String buildRepair(ContextPack pack, List<String> rejectedPredicates) {
    return commonHeader(pack)
        + "\nYour previous reply included REJECTED predicates: "
        + rejectedPredicates
        + "\nRegenerate JSON only. Remove array subscripts, internal SSA names, select/store.\n"
        + buildOutputContract();
  }

  private String buildOutputContract() {
    return """

        Output ONLY valid JSON (no markdown, no commentary):
        {"predicates": ["(bvsge i (_ bv0 32))", "(bvslt i n)"]}
        Between %d and %d items (fewer allowed if only strong candidates). Do NOT use N* location keys; Java binds predicates to all loop heads.
        """
        .formatted(budget.minPerCall(), budget.maxPerCall());
  }
}
