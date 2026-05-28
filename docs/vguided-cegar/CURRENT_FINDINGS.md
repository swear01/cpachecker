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

## 14. V3 Validation: Diversified Prompting Is Not the Main Bottleneck

### What V3 Was

V3 = single-call diversified predicate proposal + bucket-aware ranking + top-k precision injection.

| Mode | LLM input | LLM output | Selection | Formal runs |
|------|-----------|------------|-----------|-------------|
| B2 | source + assertion | flat predicate list | all candidates | 1 |
| V3 | source + assertion + predicate buckets | structured candidate set (DIRECT, LOOP-RELATION, GUARD, BOUNDS) | bucket-aware ranking + top-k | 1 |

The hypothesis: asking the LLM proactively for different predicate classes (especially auxiliary loop-carried relations, accumulator-counter relations) would produce higher-quality predicate sets than B2's flat source-only prompt.

### Validation Set (8 benchmarks, VGUIDE_PRECISION_TOP_K=5)

| Benchmark | B2 | V3 | Interpretation |
|---|---:|---:|----|
| linear-ineq-inv-a | 1 | 1 | B2 already finds key predicate |
| diamond_1-1 | 1 | 2 | V3 no improvement |
| diamond_1-2 | 26 | 27 | bounds-dominated / no precision gain |
| sum01-1 | 11 | 12 | no improvement |
| sum04-2 | 6 | 7 | no improvement |
| const_1-2 | 48 | 38 | one positive case (+21%) |
| eureka_01-2 | LLM failed | LLM failed | API or unsupported benchmark |
| array-1 | 2 | 3 | no improvement |

### Conclusion

V3's bucketed prompt and accumulator emphasis do **not** systematically improve over B2.
The main bottleneck is **not prompt format alone**.

- On 6/8 benchmarks, V3 ≈ B2 (within ±1 refinement).
- On 1 benchmark (const_1-2), V3 shows modest improvement (48→38) — insufficient to claim generality.
- On 1 benchmark (eureka_01-2), both modes failed due to LLM/API issues.

Result classification:
- **V3 is negative/weak**: diversified prompting is not the next main method.
- **B2 remains the source-only baseline.**
- **B4 is not validated**: the linear-ineq-inv-a B4 rescue (89→2) was a B2 non-determinism artifact, not CEGAR feedback effect. Re-running B2 on linear-ineq-inv-a sometimes produces 1 refinement (when LLM non-deterministically generates `s>=255*i`).

### Actual Bottleneck Hypotheses

The question shifts from "how to prompt the LLM better" to **"how to use LLM predicates more effectively in CPAchecker"**:

1. **Location-specific precision injection** — predicates should be injected only at locations where they are likely true, not globally
2. **Stronger CEGAR feedback** — spurious traces and interpolants should guide which predicates are useful
3. **Predicate usefulness testing** — verify predicates before injection (e.g., test on concrete counterexample traces)
4. **Auxiliary predicate support** — beyond assertion copies, need predicates about intermediate program relations (e.g., relationship between loop variables before they reach the assertion)

### Safe Claim

The LLM can generate useful predicates, but current integration methods (global precision injection, simple entailment gate) do not yield broad improvement across benchmarks.

## 15. V4 Validation: Usefulness-Aware Scoring Is Also Not the Bottleneck

### What V4 Was

V4 = usefulness-aware predicate filtering before precision injection, using SAT-based scoring:

1. Reject trivial (TRUE/FALSE) and contradictory (blockFormula ∧ p UNSAT) predicates.
2. SAT-test each candidate: blockFormula ∧ p SAT and blockFormula ∧ ¬p SAT both needed.
   - Both SAT → non-constant → high value (base 5).
   - blockFormula ∧ ¬p UNSAT → entailed → lower value (base 1, B1 already handles).
3. Apply bonuses: relational +3, accumulator +3, modulo +2, concise +1, loop-head +1.
4. Select top-k by score, inject globally.

Injection: `VGUIDE_PRECISION_V4=1` + `VGUIDE_PRECISION_TOP_K=5`.

New class: `PredicateScorer` (with 12 unit tests, all passing).

### Validation Set (7 benchmarks)

| Benchmark | B2 | V4 | Interpretation |
|---|---:|---:|----|
| diamond_1-1 | 2 | 2 | no difference |
| diamond_1-2 | 27 | 27 | bounds-dominated, no difference |
| linear-ineq-inv-a | 1 | 1 | B2 already finds key predicate |
| sum01-1 | 12 | 12 | no difference |
| sum04-2 | 2 | **6** | V4 injected 0 predicates (all rejected/scored too low) |
| const_1-2 | 38 | **46** | V4 regression |
| eureka_01-2 | failed | failed | LLM/API failure |

### Observed V4 Behavior

- On sum04-2: V4 rejected all candidates (injected 0 predicates), while B2 injected some and achieved 2 refinements.
- On const_1-2: V4 degraded (38→46).
- On benchmarks where both B2 and V4 inject predicates (diamond_1-1, diamond_1-2, sum01-1): no difference.
- The SAT filter rejects candidates that B2's simple heuristic keeps and that turn out to be useful.

### Conclusion

V4's SAT-based usefulness filter does **not** improve over B2's simple heuristic.
On benchmarks where B2 already performs well (like sum04-2), V4 over-filters and causes regression.

The problem: blockFormula at the first loop-head visit is too weak as a context for SAT testing.
A predicate like `(= s (* i v))` is not true at the first visit (s=0, i=0, v=nondet),
so `blockFormula ∧ (s != i*v)` is SAT (s=0, i=0, v=5, s=0 != 0*5=0? Wait, 0==0 so s=i*v at the first visit if v=arbitrary...).

Actually the deeper issue: the blockFormula does not capture the **inductive structure** needed to evaluate whether a predicate is useful as an abstraction feature. What matters is whether the predicate helps track the relationship between variables across the loop, not whether it's non-trivial at one program point.

### Safe Claim

SAT-based predicate filtering using single-program-point block formulas is insufficient to identify useful abstraction predicates. The signal/noise discrimination requires context from the full CEGAR loop (interpolants, spurious traces), not just local SMT checks.

## 16. Updated Direction

- B2 remains the source-only baseline (simple heuristic, usable as reference).
- V3 is negative: diversified prompting does not help.
- V4 is negative: local SAT-based filtering does not help and can regress.
- B4 is not validated as a rescue mechanism.
- The predicate integration strategy (how CPAchecker uses LLM predicates) is the unresolved bottleneck.
- Next investigation: **stronger CEGAR feedback** — use interpolant predicates and spurious counterexample traces to guide predicate selection, not just pre-injection SAT scoring.
- Do not run large-scale evaluations until a new integration method is tested on a small set.
- Do not optimize individual benchmarks.
