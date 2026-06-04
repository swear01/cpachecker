# Case Study: Bootstrap Rescue — `up` (loop-invgen)

## 1. Benchmark Summary
- **Task**: `up` (loop-invgen)
- **Source**: SV-COMP 2026 ReachSafety-Loops (`/home/swear01/FMPA2/part2/sv-benchmarks/c/loop-invgen/up.i`)
- **Property**: `__VERIFIER_assert(k > 0)` — k is always positive after two-loop execution
- **Structure**: Two sequential loops. First loop increments `i` and `k` while `i < n`. Second loop decrements `k` while `j < n`. At the assertion site, `k = n - j`, so `k > 0` when `j < n`.
- **Why selected**: Initial ZERO_CONTEXT_TIMEOUT. Two-loop counter/accumulator pattern. Similar to the first rescue case.

## 2. Baseline Failure
- **Local no-LLM @300s**: UNKNOWN, ~65 refinements, 1 context dump
- **Classification**: B2 solves (with LLM vocabulary) but at high refinement count

Note: With `useVocabularyGuide=true`, the B2 LLM generates initial predicates that enable CEGAR but require many refinements. Without LLM vocabulary, this is a true ZERO_CONTEXT_TIMEOUT (as shown in the diagnostic scan).

## 3. Bootstrap Effect
Eight source-level predicates generated from source code:
- `i >= 0`, `k >= 0`, `i < n`, `k = i`, `n >= 0`, `k > 0`, `i <= n`, `k - i = 0`

After bootstrap injection: ~43-44 refinements (improvement from 65).

## 4. B5-MR Repair Effect
Four B5 repair predicates generated:
- `(= k i)` — k equals i after first loop
- `(bvsge k (_ bv0 32))` — k >= 0
- `(= k (bvsub n j))` — key: k = n - j, implies k > 0 when j < n
- `(bvsgt k (_ bv0 32))` — k > 0 (the assertion itself)

After combined injection: **TRUE**, 1-2 refinements. 3/3 reproductions successful.

## 5. Causal Analysis
- Bootstrap alone: not sufficient (UNKNOWN, 43 refs)
- Bootstrap + `k=i` alone: not sufficient (UNKNOWN, 43 refs)
- Bootstrap + `k=n-j` alone: not sufficient (UNKNOWN, 43 refs)
- Bootstrap + both: sufficient (TRUE, 1-2 refs)

**Both key predicates are needed together.** `k=i` tracks the first loop body, `k=n-j` tracks the second loop invariant. Together they prove `k>0`.

## 6. Soundness
LLM predicates are precision predicates only. CPAchecker proves TRUE. No LLM output is trusted as an invariant.

## 7. Pattern
**Counter/accumulator relation** — two-loop structure where `k` tracks both `i` and `n-j`.

## 8. Takeaway
This case shows that bootstrap can unlock CEGAR context, but the proof requires B5-MR to discover the key relational predicate `k = n - j`. No single predicate alone is sufficient; the combination proves the property.
