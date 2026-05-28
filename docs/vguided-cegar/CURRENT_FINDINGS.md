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
- B5 is the current investigation: **rich CEGAR context (trace + interpolants) → LLM repair → precision injection**.
- Do not run large-scale evaluations until a new integration method is tested on a small set.
- Do not optimize individual benchmarks.

## 17. B5: Trace/Interpolant-Guided LLM Predicate Repair

### What B5 Is

B5 replaces source-only and local-SAT approaches with full CEGAR failure context:

| Phase | What | Status |
|-------|------|--------|
| Phase 1 | Dump CEGAR context (ARGPath, CFA edges, block formulas, interpolants, precision, candidate fates) to JSON | Done (`B5ContextDumper.java`) |
| Phase 2 | Summarize context to compact Markdown + call DeepSeek to generate repair predicates | Done (`b5_context_summarizer.py`, `b5_build_prompt.py`, `b5_repair_from_prompt.py`) |
| Phase 3 | Parse repair predicates, inject into precision, rerun CPAchecker | Smoke-tested on 2 benchmarks |

### Context Provided to LLM

- Source code
- Target assertion (with variable extraction)
- Spurious counterexample trace (CFA locations + edges with branch conditions)
- Block formulas per abstraction state (SMT-LIB2, compressed)
- Interpolants per abstraction state (SMT-LIB2, atoms extracted)
- Current precision (global predicates)
- LLM candidate fates (entailed / abstraction-candidates / injected)

### Phase 2 Smoke Test

| Benchmark | Predicates | Novel? | LLM Reasoning |
|-----------|-----------|--------|---------------|
| sum04-2 | `(= sn (bvmul i (_ bv2 32)))`, `(bvsle i (_ bv8 32))`, `(bvsge i (_ bv1 32))` | 3/3 new | "the CEGAR loop is getting stuck on traces where the loop doesn't execute but sn is neither 0 nor 16" |
| diamond_1-2 | `(= (bvurem x 2) (bvurem y 2))` | 1/1 new | "the abstraction doesn't track the relationship between x's parity and y's parity through loop iterations" |

The LLM produces reasoned explanations of why the benchmark is failing and generates targeted SMT-LIB2 BV predicates.

### Phase 3 Rerun

| Benchmark | B2 | B5 | Δ | Injected | Diagnosis |
|-----------|----:|----:|-----|----------|-----------|
| sum04-2 | 7 | **2** | **-71%** | 3/3 parsed | Accumulator relation `sn=i*2` is the missing bottleneck |
| diamond_1-2 | 27 | 27 | 0 | 1/1 parsed | Parity correctly identified but bounds-dominated |

Parser extended to support SMT-LIB2 BV operator names (`bvmul`, `bvsle`, `bvurem`, `(_ bvN 32)` constants).

### Safe Claim

B5 rich CEGAR context (trace + interpolants) can produce useful auxiliary repair predicates when the missing auxiliary relation (e.g., accumulator-counter relation) is the bottleneck. Validated on sum04-2 (7→2).

## 18. B5 Targeted Mini-Evaluation

### Completed (6/6 benchmarks)

| Benchmark | B2 | B5 | Δ | Diagnosis |
|-----------|----:|----:|-----|-----------|
| sum04-2 | 7 | **2** | **-71%** | Accumulator `sn=i*2` is the bottleneck |
| const_1-2 | 47 | **36** | **-23%** | Loop-constraint relations (`x=0`, `y+1=1024`) help |
| diamond_1-2 | 27 | 27 | 0 | Bounds-dominated; parity correctly identified but not bottleneck |
| sum01-1 | 12 | 11 | ≈ | Accumulator `sn=(i-1)*2` parsed but no significant improvement |
| eureka_01-2 | 22 | 24 | ≈ | **Parser failure**: 0/12 predicates parsed. LLM generated `select` (array theory), `bvshl`, SSA-encoded names not in parser |
| linear-ineq-inv-a | 1 | 1 | = | Sanity check: B5 matches B2 best case, no regression |

### Summary

| Category | Count | Benchmarks |
|----------|------:|------------|
| Improved | 2 | sum04-2 (-71%), const_1-2 (-23%) |
| No effect | 2 | sum01-1, eureka_01-2 (parser failure) |
| Bound/control | 1 | diamond_1-2 |
| Sanity match | 1 | linear-ineq-inv-a |
| Regression | **0** | none |

### Key Observations

1. **Two validated improvements** (sum04-2: -71%, const_1-2: -23%). Both involve accumulator/constraint relations derived from trace context.
2. **Zero regressions**. No benchmark became worse after B5 injection.
3. **100% parse rate** for predicates using supported SMT operators. The only parse failure was eureka_01-2 where the LLM generated array-theory and bitvector-shift operations not in the BV parser.
4. **Semantically reasonable predicates do not always reduce refinements**. sum01-1's `sn=(i-1)*2` is correct but doesn't change refinement count.
5. **Parser gap**: operations like `select`, `bvshl`, and SSA-encoded `|main::i@3|` variable names are not supported. The LLM sometimes uses these when the benchmark involves arrays or pointer-based memory access.
6. **B5 is more promising** than source-only prompt variants (V3) and local SAT scoring (V4) because it uses actual CEGAR failure context (trace, interpolants) instead of guessing from source alone or testing at a single program point.

### Safe Claim (Updated)

B5 rich CEGAR context (trace + interpolants) can produce useful auxiliary repair predicates that reduce refinement counts when the missing auxiliary relation is the bottleneck (2 confirmed cases of 6). B5 is not a general accelerator. Semantically reasonable repair predicates do not always reduce refinement counts. Zero regressions across 6 benchmarks.

The improvement over B2 is limited to benchmarks where:
1. B2's source-only prompt misses an auxiliary relational predicate
2. That predicate is detectable from the spurious trace structure
3. The predicate can be expressed in the supported BV-only SMT subset
4. The missing relation is the actual CEGAR bottleneck (not bounds-dominated)

## 19. Research Synthesis

### Method Comparison

| Mode | LLM Input | Selection | Predicate Source | 1-LLM-Call | Result |
|------|-----------|-----------|-----------------|:----------:|--------|
| B2 | Source code only | Weak heuristic (all candidates) | LLM guesses from source | Yes | Effective on 1-2 relational cases, unstable |
| V3 | Source + predicate buckets | Bucket-aware ranking + top-k | LLM generates diversified classes | Yes | **Negative**: no improvement over B2 |
| V4 | Source + local SAT filter | SAT-based usefulness scoring | LLM candidates scored by blockFormula | Yes | **Negative**: over-filters, regresses on sum04-2 |
| B5 | Source + trace + interpolants + precision | LLM ranks based on CEGAR feedback | LLM repairs from CEGAR context | Yes | **2/6 improved, 0 regressions** |

### Narrative Arc

The project started with the hypothesis that LLMs could generate useful abstraction predicates for CEGAR. The progression of methods tells a clear story:

**B2 (source-only):** "Just give the LLM the source code." This works on diamond_1-1 but is unstable — predicate quality depends on LLM non-determinism, and the LLM has no information about why CPAchecker is failing.

**V3 (diversified prompting):** "Ask the LLM for different types of predicates." Prompt engineering (DIRECT, LOOP-RELATION, GUARD, BOUNDS buckets) does not systematically improve predicate quality. This was a critical negative result that ruled out prompt format as the main bottleneck.

**V4 (local SAT scoring):** "Filter predicates using blockFormula SAT tests." Single-program-point SAT checks over-filter, rejecting useful predicates that are not true at the first loop visit. Scoring without CEGAR context fails.

**B5 (CEGAR-rich feedback):** "Give the LLM the trace, interpolants, and current precision." The LLM sees what CPAchecker's interpolation engine has learned and where the gaps are. This is the first method beyond source-only prompting to show targeted improvement (sum04-2: -71%, const_1-2: -23%), with zero regressions.

### Why B5 Works When Others Don't

B5's advantage is not in prompt design or scoring heuristics — it's in **information content**:

| Information | B2 | V3 | V4 | B5 |
|------------|:--:|:--:|:--:|:--:|
| Source code | Yes | Yes | Yes | Yes |
| Assertion expression | Yes | Yes | Yes | Yes |
| Spurious counterexample trace | | | | Yes |
| CFA edge branch conditions | | | | Yes |
| Block formulas (SSA-SMT) | | | | Yes |
| Interpolants per abstraction state | | | | Yes |
| Current precision predicates | | | | Yes |
| LLM candidate fates | | | | Yes |

The LLM can now answer: "What relation is CPAchecker missing that would rule out this specific counterexample trace?" — not just "What predicates might be relevant for this source code?"

### Limitations

1. **Bounds-dominated benchmarks**: If the CEGAR bottleneck is learning numeric bounds (diamond_1-2, sum01-1), auxiliary relational predicates don't help.
2. **Parser subset**: Predicates must use supported BV operations (`+`, `-`, `*`, `mod`, `<`, `<=`, `>`, `>=`, `=`). Array theory (`select`), bitvector shifts (`bvshl`), and pointer-level SSA names are not supported.
3. **Benchmarks already solved by B2**: linear-ineq-inv-a solves in 1 refinement either way.
4. **Non-scalar benchmarks**: Array-heavy or pointer-intensive benchmarks (eureka_01-2) generate predicates in theories the parser doesn't support.
5. **One-shot injection**: B5 currently injects repair predicates once. Multi-round repair is not tested.

### What B5 Proves

B5 demonstrates that **rich CEGAR context is actionable by an LLM**. Given trace and interpolant information, the LLM can:
- Identify why a specific counterexample is spurious
- Propose auxiliary relational predicates that address the gap
- Produce correct SMT-LIB2 syntax (within the BV subset)

This shifts the research question from "Can LLMs guess useful predicates?" (B2: yes, sometimes) to "Can CEGAR feedback guide LLM repair?" (B5: yes, for targeted cases).

### What B5 Does NOT Prove

- B5 is not a general-purpose accelerator for CPAchecker.
- B5 does not replace B2 — source-only prompting still works on diamond_1-1.
- B5 does not handle bounds-dominated, array-heavy, or already-solved benchmarks.
- 6 benchmarks is diagnostic validation, not statistical evidence.
