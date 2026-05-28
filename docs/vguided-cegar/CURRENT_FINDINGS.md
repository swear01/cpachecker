# Current Findings — LLM-Guided Predicate Discovery for CEGAR

## 1. Project Goal

This project studies LLM-guided predicate discovery for CEGAR-based software model checking in CPAchecker. The long-term goal is to develop a general method where LLMs help hard scalar-loop benchmarks by generating useful abstraction predicates, not just to optimize one benchmark.

## 2. Baseline Modes

| Mode | Name | Description |
|------|------|-------------|
| B0 | Stock | Original CPAchecker PredicateCPA |
| B1 | Entailed-only | LLM local facts satisfying `blockFormula ⇒ p` → strengthen interpolants |
| B2 | LLM precision | Source-only LLM abstraction candidates → one-shot precision injection |
| B3a | Assertion oracle | Extracted assertion predicate → one-shot precision injection |
| V2 | Ranked top-k | LLM candidates deduped/ranked → top-k injected |
| B4 | CEGAR-guided repair | Offline repair pipeline using CEGAR failure context to generate repair predicates |

B0/B1/B2/B3a/V2 are baselines and diagnostics. **B4 is the next method intended to improve generality.**

## 3. Core Technical Insight

LLM-generated formulas should not all be treated as invariants or local facts. There are two classes:

**ENTAILED predicates** — satisfy `blockFormula ∧ ¬p` is UNSAT. These can safely strengthen interpolants. Example: `x >= 0`, `x < 99`.

**ABSTRACTION-CANDIDATE predicates** — not necessarily true at a location. They are Boolean features that PredicateCPA should track in precision. Example: `(= (mod x 2) (mod y 2))`. At the first loop-head visit, `x=0, y=nondet`, so parity equality is not yet established, but it is the exact assertion predicate and a critical abstraction feature.

**Soundness boundary:** LLM predicates are not trusted as facts. Non-entailed predicates are only injected into precision, so the verifier tracks their truth values instead of assuming them.

## 4. Current Evaluation Matrix

| Benchmark | B0 Stock | B1 Entailed | B2 LLM | B3a Oracle | V2 top-3 |
|-----------|---------:|------------:|-------:|-----------:|---------:|
| diamond_1-1 | 76 | 39 | 3 | 3 | **2** |
| diamond_1-2 | 51 | 26 | 27 | 27 | 27 |
| sum01-1 | 11 | 11 | 6 | 7 | 8 |
| sum04-2 | 10 | 6 | 2 | 6 | **2** |

- diamond_1-1 is the strongest relational-positive case (76→2 with V2).
- diamond_1-2 is bounds-dominated: entailed facts alone reduce refinements from 51 to 26; precision injection adds no further benefit.
- sum04-2 shows LLM candidates can outperform the direct assertion oracle (B2=2 vs B3a=6), indicating auxiliary predicates matter.
- V2 top-k helps diamond_1-1 (3→2) but regresses sum01-1 (6→8), showing ranking is not yet stable.

## 5. 127 Benchmark Scan

| Category | Count | Interpretation |
|----------|------:|----------------|
| relational-positive | 3 | Precision injection helps beyond entailed-only |
| bounds-dominated | 3 | Local facts explain most improvement |
| timeout-incomparable | 60 | Stock did not finish; refinement counts not directly comparable |
| too-easy | ~55 | Stock already needs <10 refinements |
| no-effect | 2 | LLM precision did not improve refinement count |

**Conclusion:** Source-only B2/V2 methods are not general-purpose accelerators. They are effective mainly when the bottleneck is a missing relational abstraction predicate.

## 6. Why B4 Is Needed

Source-only LLM predicate proposal works on diamond_1-1 but not on most benchmarks. To improve generality, the LLM must receive CEGAR failure context, not only source code.

B4 should use:
- Spurious counterexample traces
- Current precision / vocabulary
- Rejected predicates and rejection reasons
- Abstraction locations
- Interpolants or learned predicates
- Previous repair attempts

The goal: generate repair predicates that directly address why the current abstraction is failing.

## 7. B4 Offline Pipeline Status

B4 is end-to-end functional:

| Component | File | Role |
|-----------|------|------|
| Context dump | `b4_offline_dump.sh` + Java `dumpB4Context()` | Runs B2 partial, dumps context via `VGUIDE_B4_DUMP_CONTEXT` |
| LLM repair | `b4_offline_repair.py` | Reads context, calls DeepSeek, produces `repair_candidates.json` |
| Rerun | `b4_offline_rerun.sh` + Java `injectRepairPredicatesOnce()` | Injects repair predicates via `VGUIDE_INJECT_REPAIR_PREDICATES_ONCE` |

Java injection mode: reads `VGUIDE_REPAIR_CANDIDATES_FILE`, parses predicates with `lastEncodedVars`, injects top-K into `PredicatePrecision`.

## 8. B4 Smoke Test Results

| Benchmark | B2 | B4 repair | Diagnosis |
|-----------|----:|----------:|-----------|
| diamond_1-1 | 3 | 3 | B2 already optimal |
| sum04-2 | 2 | 7 | Repair predicates too noisy for easy B2 case |
| linear-ineq-inv-a | 89 (UNKNOWN) | **2 (TRUE)** | B4 rescued a B2-failed case |

Interpretation:
- `linear-ineq-inv-a` is the first evidence that CEGAR-guided repair may improve generality beyond source-only LLM precision.
- `sum04-2` regression shows B4 should target hard/failing cases, not already-easy B2 cases.

## 9. Immediate Next Validation

Before large-scale B4 evaluation, validate the `linear-ineq-inv-a` rescue:

1. Re-run B2 and B4 under the same timeout and heap settings.
2. Re-run B4 using the same fixed `repair_candidates.json`.
3. Re-run B4 with regenerated repair candidates.
4. Confirm B4 is injecting repair candidates, not assertion-oracle predicates.
5. Print selected repair predicates and explain why they plausibly help.
6. Confirm result TRUE is reproducible.

## 10. B4 Target Set Policy

B4 should target:
- B2 UNKNOWN / timeout cases
- B2 high-refinement cases
- B2 no-effect cases
- Weak-positive cases where B2 still needs many refinements

Exclude:
- Too-easy benchmarks
- B2 already solved in very few refinements
- Array/pointer/concurrency-heavy benchmarks
- Unsupported theories (unless explicitly testing parser extensions)

## 11. B4 Evaluation Plan

| Mode | Description |
|------|-------------|
| B2 | Source-only LLM precision |
| B4-1 | One repair round |
| B4-3 | Three repair rounds |
| B4-until-budget | Repair until solved, timeout, or no progress |

Metrics: TRUE/FALSE/UNKNOWN, refinement count, runtime, generated/parsed/injected predicates, duplicate/rejected rate, improvement over B2.

## 12. Append-Only Transcript Requirement

B4 repair should use an append-only transcript for prompt-cache reuse.

Rules:
- Each later LLM prompt must include previous information exactly as originally sent.
- Do not rewrite, summarize, reorder, or insert into previous sections.
- Append only: `ROUND k REQUEST`, `ROUND k LLM OUTPUT`, `ROUND k FORMAL RESULT`.

Cache contract: `prompt[k]` must be a strict prefix of `prompt[k+1]`, except after explicit checkpointing.

## 13. Safe Current Claims

**Allowed:**
- Source-only LLM precision injection is not generally effective across all scanned benchmarks.
- It is highly effective when the bottleneck is a missing relational abstraction predicate.
- B4 is motivated by the need to use CEGAR failure feedback.
- The `linear-ineq-inv-a` smoke test suggests B4 can rescue at least one B2-failed case (requires validation).

**Disallowed:**
- B4 is generally effective.
- LLM broadly accelerates CPAchecker.
- V2 ranking is uniformly better.
- Refinement reduction equals runtime speedup.
- One benchmark rescue proves generality.

## 14. Next Step

1. Validate the `linear-ineq-inv-a` B4 rescue (reproducibility).
2. Build a targeted B4 benchmark set from hard/B2-failed cases.
3. Run B4 only on the target set.
4. Compare B2 vs B4.
5. Update report with validated B4 results.

Do not continue optimizing diamond_1-1. Do not tune V2 further until B4 target evaluation is done.
