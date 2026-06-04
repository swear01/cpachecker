# Case Study: Bootstrap Rescue — `down` (loop-invgen)

## 1. Benchmark Summary
- **Task**: `down` (loop-invgen)
- **Source**: SV-COMP 2026 ReachSafety-Loops (`/home/swear01/FMPA2/part2/sv-benchmarks/c/loop-invgen/down.i`)
- **Property**: `__VERIFIER_assert(k >= 0)` — k never goes negative
- **Structure**: Two sequential loops. First loop increments `k` while `i < n`. Second loop decrements `k` while `j < n`, with assertion that `k >= 0`.
- **Why selected**: ZERO_CONTEXT_TIMEOUT. Two-loop counter/accumulator pattern.

## 2. Baseline Failure
- **Local no-LLM @300s**: UNKNOWN, 89-94 refinements
- With `useVocabularyGuide=true`, B2 does many refinements but doesn't solve.

## 3. Bootstrap Effect
Eight source-level predicates generated. After bootstrap injection: 37 refinements (significant improvement from ~92).

## 4. B5-MR Repair Effect
B5 repair generates predicates including accumulator relations. After combined injection: **TRUE, 1-2 refs on 2/3 runs.** One run (run 2) didn't solve — B5 produced 8 repair predicates but they were insufficient.

## 5. Reproduction Status
**2/3 confirmed rescue.** Slightly less stable than `up` (3/3). Instability may be due to B5 repair predicate variance across runs.

## 6. Soundness
LLM predicates are precision predicates only. CPAchecker proves TRUE.

## 7. Pattern
**Counter/accumulator relation** — two-loop structure with accumulator variable `k` tracking increment/decrement.

## 8. Takeaway
`down` is the second confirmed rescue case. It shares the same pattern as `up`: bootstrap unlocks context, B5-MR adds proof-relevant predicates. The 2/3 reproduction rate is strong but not perfect, suggesting B5 repair quality has some run-to-run variance.
