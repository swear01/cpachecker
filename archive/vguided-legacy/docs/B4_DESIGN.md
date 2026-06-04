# B4: CEGAR-Guided Iterative LLM Predicate Repair

## 1. Motivation

B2/V2 source-only methods prove that LLM predicates can work on `diamond_1-1` (76→2), but are not general. The 127-benchmark scan showed:

- 60 timeout-incomparable (stock UNKNOWN or timed out)
- ~55 too-easy (no room for improvement)
- 3 relational-positive, 3 bounds-dominated, 2 no-effect

Source-only one-shot predicate generation is insufficiently general. The LLM needs **CEGAR feedback** — spurious traces, current precision, interpolants, rejected predicates — to iteratively repair the predicate vocabulary.

## 2. Research Goal

Can LLMs improve CEGAR more generally when they receive refinement failure context such as spurious traces, current precision, interpolants, rejected predicates, and previous repair attempts?

## 3. Baselines (not final methods)

| Mode | Name | Description |
|------|------|-------------|
| B0 | Stock | Original CPAchecker |
| B1 | Entailed-only | LLM local facts → strengthen interpolant |
| B2 | Source-only LLM precision | One-shot abstraction candidates → inject |
| B3a | Assertion oracle | Assertion predicate → inject |
| V2 | Ranked top-k | LLM candidates → dedup/rank → top-k inject |

## 4. Method Overview

```
1. Run B2 initially (source-only one-shot).
2. If CEGAR still has high refinements, repeated spurious counterexamples,
   or timeout risk, collect failure context.
3. Append context to the repair transcript.
4. Ask LLM for repair predicates targeting the latest spurious traces.
5. Parse/type-check/dedup/rank repair predicates.
6. Inject top-k into PredicateCPA precision.
7. Continue for multiple rounds while progress is possible.
```

## 5. Append-Only Transcript Design

**Rules:**
- The transcript is append-only. Each round's section is immutable once written.
- Every later prompt must contain all earlier content byte-identically.
- Do not rewrite, summarize, reorder, or insert into previous sections.
- Only append new sections: `ROUND k REQUEST`, `ROUND k LLM OUTPUT`, `ROUND k FORMAL RESULT`.
- If context grows too long, create a checkpoint summary once and treat it as a new immutable prefix.

**Cache contract:** `prompt[k]` must be a strict prefix of `prompt[k+1]`, except after explicit checkpointing.

## 6. Transcript Format

```
=== STATIC CONTEXT BEGIN ===
Task rules: generate abstraction predicates, not necessarily invariants.
Source code: <original source>
Target assertion: <extracted assertion>
Abstraction locations: N19 (loop head), N14 (main entry), ...
Allowed grammar: =, >=, <=, >, <, +, -, *, mod, and, or, not
Output: JSON {"N19": ["(= (mod x 2) (mod y 2))", ...]}
=== STATIC CONTEXT END ===

=== ROUND 0 REQUEST BEGIN ===
Initial candidate request. Generate 3-5 predicates.
=== ROUND 0 REQUEST END ===

=== ROUND 0 LLM OUTPUT BEGIN ===
{"N19": ["(= (mod x 2) (mod y 2))", "(>= x 0)", "(< x 99)"]}
=== ROUND 0 LLM OUTPUT END ===

=== ROUND 0 FORMAL RESULT BEGIN ===
Parsed: 3, Injected: 3
ENTAILED: (>= x 0), (< x 99)
ABSTRACTION-CANDIDATE: (= (mod x 2) (mod y 2))
Refinements: 25 → still spurious, repeated trace at N19
=== ROUND 0 FORMAL RESULT END ===

=== ROUND 1 REQUEST BEGIN ===
Latest spurious trace summary: path from N14 to N19, branch y%2==1 taken
Current precision: x>=0, x<99
Already tried and rejected: none yet
Generate 5 new predicates that distinguish this trace.
=== ROUND 1 REQUEST END ===
```

## 7. CEGAR Feedback to Expose

- Target assertion
- Current precision predicates (summarized, not full dump)
- Latest spurious trace (path, branch decisions, key constraints)
- Abstraction locations on the trace
- Predicates already injected and their fate (entailed / abstraction-candidate / rejected)
- Rejected predicates and rejection reasons (parse error, duplicate, no improvement)
- Whether previous repair improved refinement count

## 8. Repair Prompt Requirements

The repair prompt must state:
- Generate abstraction predicates, not necessarily invariants.
- Do not repeat predicates already in the transcript.
- Prefer predicates that distinguish the latest spurious trace.
- Prefer auxiliary relational predicates, not just assertion copies.
- Avoid simple bounds already handled by B1.
- Output SMT-LIB-like prefix syntax in JSON.

## 9. Formal Filtering and Injection

- Parse/type-check with existing BV parser + encoded variable names
- Syntactic dedup against already-tried predicates
- Semantic/canonical dedup if available
- Rank (relational > arithmetic > bounds)
- Inject top-k into `PredicatePrecision` via `addGlobalPredicates` + `updatePrecisionGlobally`
- Never directly conjoin non-entailed predicates to interpolants

## 10. Stopping Conditions

Stop repair loop if:
- Verified TRUE/FALSE
- Formal timeout reached
- Max formal verification budget exceeded
- 3 consecutive rounds produce no new parseable predicates
- 3 consecutive rounds produce only duplicates
- 3 consecutive rounds show no refinement/time improvement
- Unsupported theory dominates failures

**Do not limit LLM rounds artificially.** Cache-hit calls are cheap. Control formal verification cost, not LLM call count.

## 11. Target Benchmark Set

From the 127-benchmark scan, select hard scalar-loop benchmarks:
- Stock timeout / UNKNOWN with partial progress
- Stock refinements >= 20
- B2 no-effect or weak-positive cases
- Assertion extractable
- No arrays, no pointers, no concurrency, no floating point

Exclude:
- Too-easy (stock < 10 refinements)
- Array-heavy
- Pointer-heavy
- Concurrency
- Parser-unsupported theory (unless explicitly testing parser extension)

## 12. Evaluation Plan

Compare:

| Mode | Description |
|------|-------------|
| B0 | Stock CPAchecker |
| B2 | Source-only LLM precision |
| B4-1 | 1 repair round after B2 |
| B4-3 | 3 repair rounds |
| B4-until-budget | Repair until solved or budget exhausted |

Metrics:
- TRUE/FALSE/UNKNOWN
- Refinement count
- Runtime
- LLM calls
- Approximate cache-hit ratio: static prefix tokens vs appended delta tokens
- Generated / parsed / rejected / injected predicates per round
- Improvement over B2

## 13. Success Criteria

**Primary:** B4 should solve or reduce refinements on a meaningful fraction of hard scalar-loop benchmarks where B2 is weak or ineffective.

**Secondary:** B4 should produce interpretable repair predicates tied to specific spurious traces.

Do not use `diamond_1-1` as the main success criterion — it is already solved by B2/V2.

## 14. Risks

- Spurious traces may be too low-level (SMT formulas) for LLM interpretation
- LLM may repeat predicates across rounds
- Repair predicates may not address the true refinement bottleneck
- Precision injection may be too late in the CEGAR process
- Parser may reject useful predicates (unsupported operators)
- Hard cases may fundamentally require arrays/pointers/quantifiers
- Formal reruns may dominate cost if repair predicates are unhelpful

## 15. Minimal Prototype Plan

**Phase 1 — Offline prototype:**
1. Run B2 until N refinements or timeout-near.
2. Dump context: assertion, current precision, last 3 spurious traces, rejected predicates.
3. Build append-only transcript (static context + round 0).
4. Append repair round(s) with trace feedback.
5. Call LLM for repair predicates.
6. Inject top-k repair predicates.
7. Rerun CPAchecker.
8. Compare B2 vs B4.

**Phase 2 — Online integration (future):**
- Run B4 inline during CEGAR refinement
- Trigger repair on repeated counterexample detection
- Update precision without full rerun
