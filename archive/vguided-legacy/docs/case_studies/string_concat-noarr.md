# Case Study: Unstable Rescue Candidate — `string_concat-noarr`

## 1. Benchmark Summary
- **Task**: `string_concat-noarr` (loop-invgen)
- **Source**: SV-COMP 2026 ReachSafety-Loops
- **Property**: String concatenation without arrays
- **Structure**: Loop-based string processing with counter/accumulator

## 2. Baseline Failure
- **Local no-LLM @300s**: UNKNOWN, 62-67 refinements

## 3. Bootstrap Effect
Bootstraps to 52-57 refinements (modest improvement).

## 4. B5-MR Repair — Observed Rescue
One run (run 3) solved: TRUE, 1 refinement, 6 accepted B5 predicates.
Two runs (1, 2) produced no valid B5 repair predicates — B5 repair generated candidates that were rejected or insufficient.

## 5. Instability Analysis

### Successful run (3): 6 B5 repair predicates accepted
### Failed runs (1, 2): 0 B5 repair predicates accepted

The instability appears to be **LLM repair predicate variance**: the B5 repair prompt produces different quality outputs across runs. When the LLM generates useful predicates, they solve. When it doesn't, there are no valid candidates.

### Likely cause: `llm_predicate_variance`
### Recommended fix: deterministic replay of successful B5 predicates

## 6. Reproduction Status
**1/3 — unstable rescue candidate.** Not confirmed rescue.

## 7. Takeaway
`string_concat-noarr` demonstrates that B5 repair predicate quality varies across runs. The method CAN rescue this benchmark (as shown in run 3), but the rescue is not yet stable. Deterministic replay of successful predicates would confirm whether the instability is purely LLM-side or also involves CPAchecker variance.

## 6. Fixed-Predicate Replay (Stabilization)

Replaying the exact successful predicates from run 3 (10 predicates: 8 bootstrap + 2 B5):
- **3/3 TRUE, 1 refinement** — fully stable with fixed predicates.

Root cause of original instability: LLM SSA-name contamination on runs 1-2 (B5 output used `|main::i|` instead of `i`). Run 3's LLM happened to use source-level names and produced valid predicates. With the same predicates, CPAchecker consistently proves TRUE.

**Final status: stabilized_rescue_via_fixed_predicates** (original 1/3 → fixed 3/3).
