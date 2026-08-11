# svcomp26-vguide case studies and improvement opportunities（2026-06-14）

Follow-up to [`2026-06-14_svcomp26_vguide_loops.md`](2026-06-14_svcomp26_vguide_loops.md).
Goal: explain where the +7 net gain comes from, why 10 baseline solves were lost in the full-set run,
and what changes are most likely to improve `svcomp26-vguide` on SV-COMP Loops ReachSafety.

## Summary

The full-set result is real but not yet saturated:

```text
svcomp26 baseline: 486 solved
svcomp26-vguide:   493 solved
full-set delta:    17 new solves - 10 lost solves = +7
```

Case-study reruns show two extra facts:

1. **The wins are mechanistically strong.** Representative new solves collapse from 50–86s / many refinements
   to 4–8s / 2–4 refinements after one LLM round.
2. **Several losses are not stable semantic regressions.** A targeted rerun of the 10 lost tasks recovered 5/10 with
   the same default svcomp26-vguide config. This points to portfolio resource/race sensitivity, not only bad predicates.
3. **Adaptive predicate budget is promising for the old VGuide-only pool.** A targeted `freq12 + adaptive` rerun
   recovered 5/18 old v1.4 VGuide-only tasks that the v1.5.1 full-set did not recover. A default rerun of those 5
   recovered only `in-de41`, so at least 4/5 appear tied to the adaptive-budget setting rather than pure nondeterminism.

Practical next target: **high 490s / low 500s solved** is plausible, but requires a full-set ablation because gains and
losses are not additive under the shared SV-COMP portfolio CPU budget.

## Evidence runs

| Run | Purpose | Output |
|-----|---------|--------|
| full-set v1.5.1 | primary 764-task result | `output/vguide/experiments/loops_reachsafety_unreach_svcomp26vguide_20260614/` |
| lost10 default rerun | stability check for 10 full-set lost solves | `output/vguide/experiments/case_lost10_svcomp26vguide_default_20260614/` |
| unrecovered18 adaptive rerun | test old v1.4 VGuide-only tasks not recovered by v1.5.1 | `output/vguide/experiments/case_unrecovered18_svcomp26vguide_freq12_adaptive_20260614/` |
| unrec5 default rerun | distinguish adaptive-budget signal from nondeterminism | `output/vguide/experiments/case_unrec5_svcomp26vguide_default_20260614/` |

The adaptive rerun used:

```bash
--option vguide.llmEveryNSpuriousRefinements=12 \
--option vguide.maxLlmRoundsPerAnalysis=20 \
--option vguide.enableAdaptivePredicateBudget=true \
--option vguide.llmMaxCompletionTokens=2048
```

Attribution CSVs were produced with `scripts/vguided-cegar/attribute_svcomp_verdicts.py` for the targeted runs.

## Case study A — direct LLM wins

### `count_up_down-1`

| Run | Result | Refinements | Wall | Deciding component |
|-----|--------|------------:|-----:|--------------------|
| svcomp26 | UNKNOWN | 69 | 75.383s | `parallel_single_loop` |
| svcomp26-vguide | TRUE | 2 | 3.936s | `svcomp26-vguide--singleLoop-predicateAnalysis.properties` |

LLM predicates included the exact relation and bounds needed at the loop head:

```text
(= y (bvsub n x))
(bvsge x (_ bv0 32))
(bvsle y n)
(bvsgt x (_ bv0 32))
```

Interpretation: this is the canonical VGuide win. The stock predicate component keeps refining for dozens of rounds;
one LLM round supplies the missing loop relation and turns the task into a 2-refinement proof.

### `overflow_1-1`

| Run | Result | Refinements | Wall | Deciding component |
|-----|--------|------------:|-----:|--------------------|
| svcomp26 | UNKNOWN | 86 | 58.519s | `parallel_single_loop` |
| svcomp26-vguide | TRUE | 2 | 4.829s | `svcomp26-vguide--singleLoop-predicateAnalysis.properties` |

LLM predicates captured both the threshold and parity structure:

```text
(bvsge x (_ bv10 32))
(bvsle x (_ bv10 32))
(= (bvurem x (_ bv2 32)) (_ bv0 32))
```

Interpretation: again, a small semantic predicate set replaces a long unsuccessful refinement sequence.

### `heapsort`

| Run | Result | Refinements | Wall | Deciding component |
|-----|--------|------------:|-----:|--------------------|
| svcomp26 | UNKNOWN | 9 | 71.021s | `parallel_multiple_loops` |
| svcomp26-vguide | TRUE | 4 | 7.184s | `svcomp26-vguide--multipleLoops-predicateAnalysis.properties` |

LLM predicates were simple index bounds:

```text
(bvsge j (_ bv1 32)), (bvsle j n)
(bvsge i (_ bv1 32)), (bvsle i n)
(bvsge l (_ bv1 32)), (bvsle l n)
```

Interpretation: VGuide does not only help toy arithmetic loops. For a larger multi-loop task, bounded index predicates
are enough to let predicate analysis finish before the portfolio CPU budget is exhausted.

### `nested9`

| Run | Result | Refinements | Wall | Deciding component |
|-----|--------|------------:|-----:|--------------------|
| svcomp26 | UNKNOWN | 10 | 51.200s | `parallel_multiple_loops` |
| svcomp26-vguide | TRUE | 3 | 7.724s | `svcomp26-vguide--multipleLoops-predicateAnalysis.properties` |

Representative LLM predicates:

```text
(bvsle (bvsub k i) (bvmul (_ bv2 32) n))
(bvslt j (bvmul (_ bv3 32) i))
(bvsge i (_ bv0 32))
(bvslt i n)
```

Interpretation: the LLM is useful when it proposes relational arithmetic summaries that interpolation did not find
within the portfolio budget.

## Case study B — lost solves and resource sensitivity

The full-set had 10 tasks solved by svcomp26 but UNKNOWN under svcomp26-vguide. A targeted default rerun recovered 5:

| Task | Full-set vguide | Targeted default rerun | Baseline | Rerun decider |
|------|-----------------|------------------------|----------|---------------|
| `divbin_unwindbound20` | UNKNOWN | FALSE | FALSE | `svcomp26--multipleLoops-symbolicExecution.properties` |
| `sum_by_3` | UNKNOWN | TRUE | TRUE | `svcomp26-vguide--multipleLoops-predicateAnalysis.properties` |
| `nested_5` | UNKNOWN | TRUE | TRUE | `svcomp26--multipleLoops-symbolicExecution.properties` |
| `prodbin-ll_valuebound100` | UNKNOWN | TRUE | TRUE | `svcomp26--singleLoop-symbolicExecution.properties` |
| `freire1_valuebound50` | UNKNOWN | TRUE | TRUE | `svcomp26--complexLoops-kInduction.properties` |

The remaining 5 stayed UNKNOWN in the targeted default rerun:

```text
fermat2-ll_valuebound20
geo2-ll_valuebound10
geo3-ll_valuebound10
lcm2_valuebound20
nested-3
```

Interpretation:

- Some full-set losses are **portfolio race / resource sensitivity**. The unchanged symbolic-execution or k-induction
  component can still win when rerun in a smaller batch.
- Some losses are **VGuide predicate regressions**. `nested-3` is the clearest: baseline stock predicate solves TRUE in
  2 refinements / 1.278s, but VGuide injects first-spurious predicates and then reaches 41–42 refinements and UNKNOWN.
- Because SV-COMP parallel configs share a global CPU budget across portfolio children, extra predicate work can starve
  components that would otherwise finish near the limit.

### `nested-3` — stock predicate fast, VGuide slow

| Run | Result | Refinements | Wall | Deciding component |
|-----|--------|------------:|-----:|--------------------|
| svcomp26 | TRUE | 2 | 1.278s | `svcomp26--multipleLoops-predicateAnalysis.properties` |
| svcomp26-vguide full-set | UNKNOWN | 42 | 55.865s | `parallel_multiple_loops` |
| svcomp26-vguide targeted rerun | UNKNOWN | 41 | 56.339s | `parallel_multiple_loops` |

LLM predicates included mutually incompatible state facts such as both `(= st (_ bv0 32))` and `(= st (_ bv1 32))`
as separate predicates. They are not conjoined, but they expand the predicate vocabulary in a way that changes the
refinement trajectory dramatically.

This is the strongest evidence for a **stock-first or rollback guard**.

### `sum_by_3` — recoverable VGuide loss

| Run | Result | Refinements | Wall | Deciding component |
|-----|--------|------------:|-----:|--------------------|
| svcomp26 | TRUE | 8 | 2.236s | `svcomp26--multipleLoops-predicateAnalysis.properties` |
| svcomp26-vguide full-set | UNKNOWN | 6 | 61.319s | `parallel_multiple_loops` |
| svcomp26-vguide targeted rerun | TRUE | 6 | 11.196s | `svcomp26-vguide--multipleLoops-predicateAnalysis.properties` |

This is not a stable semantic regression; the same VGuide config can solve it. It should be treated as evidence that
full-set portfolio results need repeat or controlled-resource validation for borderline tasks.

## Case study C — adaptive budget rescues old VGuide-only tasks

The v1.5.1 full-set recovered 15/33 old v1.4 VGuide-only TRUE solves. The remaining 18 all still fired one LLM round
but ended UNKNOWN. A targeted `freq12 + adaptive` rerun recovered 5/18:

```text
count_by_nondet
 down
 functions_1-1
 in-de41
 up
```

A default rerun of exactly those 5 recovered only `in-de41`; the other 4 stayed UNKNOWN. Thus the improvement signal is
not just nondeterminism. Since attribution still showed only one LLM round for these tasks, the likely cause is
**adaptive predicate budget / larger first-round predicate budget**, not the later-round frequency setting.

Evidence:

| Task | Full-set default | Adaptive rerun | Default rerun of same 5 | Interpretation |
|------|------------------|----------------|--------------------------|----------------|
| `count_by_nondet` | UNKNOWN | TRUE | UNKNOWN | adaptive-budget signal |
| `down` | UNKNOWN | TRUE | UNKNOWN | adaptive-budget signal |
| `functions_1-1` | UNKNOWN | TRUE | UNKNOWN | adaptive-budget signal |
| `up` | UNKNOWN | TRUE | UNKNOWN | adaptive-budget signal |
| `in-de41` | UNKNOWN | TRUE | TRUE | likely nondeterminism / retry-sensitive |

This suggests that `svcomp26-vguide` should test a scoped adaptive-budget variant before changing Java.

## Corrected note on `watermelon`

The v1.5.1 report initially treated `watermelon` as a possible VGuide parser robustness bug. The stack trace shows a
more precise root cause:

```text
KInductionProver.extractCTIs -> FormulaManagerView.uninstantiate -> makeVariable("false")
```

The same exception appears in the svcomp26 baseline log. Therefore `watermelon` is an existing k-induction / MathSAT
identifier issue in the portfolio, not a VGuide-specific parser bug. It remains a caveat, but it should not be counted
as VGuide-caused.

## Improvement opportunities


### Adaptive predicate budget means

Default VGuide asks for and keeps 3–6 predicates per LLM call. Adaptive budget scores the ContextPack and uses larger
tiers: low 4–8, medium 6–12, high 8–16 predicates, with `llmMaxCompletionTokens=2048`. In the targeted old
VGuide-only pool, `freq12 + adaptive` recovered 5/18 tasks; rerunning those 5 with default recovered only `in-de41`.
Thus the signal is: larger/adaptive first-round predicate budgets can solve tasks default budget misses. It is not yet
a full-set proof, and it may increase lost solves if predicates pollute precision.

### 1. Low-risk config ablation: adaptive budget for svcomp26-vguide

Rationale: targeted rerun recovered 4 tasks that default did not (`count_by_nondet`, `down`, `functions_1-1`, `up`).
Because each still used only one LLM round, the likely useful part is adaptive predicate budget, not necessarily
`every_n=12`.

Suggested arms:

1. `svcomp26-vguide-default` — current v1.5.1 config.
2. `svcomp26-vguide-adaptive-budget` — add:
   ```properties
   vguide.enableAdaptivePredicateBudget = true
   vguide.llmMaxCompletionTokens = 2048
   ```
3. Optional `svcomp26-vguide-freq12-adaptive` — also add:
   ```properties
   vguide.llmEveryNSpuriousRefinements = 12
   vguide.maxLlmRoundsPerAnalysis = 20
   ```

Expected upside: recover some of the 18 old VGuide-only tasks not recovered by v1.5.1. Must be full-set tested because
larger predicate budgets may also increase losses.

### 2. Stock-first / delayed-first-LLM guard

Rationale: `nested-3` and similar tasks show stock predicate can solve quickly, while first-spurious LLM changes the
trajectory and causes UNKNOWN.

Candidate design:

- In svcomp portfolio mode only, delay the first LLM call until after `N` stock refinements, e.g. `N=3` or `N=8`.
- Or add a rollback guard: if LLM-injected predicates cause refinement count or solver time to spike without progress,
  stop injecting LLM predicates and continue with stock interpolation-only refinement.

Expected upside: preserve baseline predicate wins (`nested-3`, potentially `sum_by_3`) without losing the hard cases
where baseline needs dozens of refinements (`count_up_down-1`, `overflow_1-1`).

Risk: delaying too much may lose the fast 4–8s direct VGuide wins. This needs a targeted new/lost ablation before a
full-set run.

### 3. Predicate-quality filters for portfolio mode

Rationale: harmful cases often include broad, mutually competing, or bug-oriented predicates that are useful as
hypotheses but expensive as precision seeds.

Candidate filters:

- SAFE-only injection in svcomp portfolio mode; keep BUG prompt for diagnostics but do not inject BUG predicates by default.
- Reject or down-rank mutually exclusive same-variable equalities from the same round, e.g. `st == 0` and `st == 1`.
- Penalize very large constants or high-complexity nonlinear bit-vector formulas unless they appear in the program slice.
- Keep only predicates that mention loop-head variables and pass a cheap relevance score.

Expected upside: reduce precision pollution and CPU starvation, especially on baseline-easy predicate tasks.

### 4. Resource-aware evaluation and single-run strategy

Rationale: 5/10 full-set lost solves recovered in a smaller default rerun. This proves retry/resource sensitivity, but
realistic SV-COMP-style execution has no external retry. Targeted reruns are diagnostic only.

Suggested practice:

- For reports: rerun `new ∪ lost` only to classify stable / retry-sensitive / config-sensitive deltas.
- For runtime: convert the lesson into single-run mechanisms — stock-first guards, in-run probes, adaptive budget, and
  portfolio resource allocation.
- Use BenchExec or lower outer parallelism for final measurement if wall/CPU contention becomes a concern.
- Broader plan: [`../SVCOMP26_PORTFOLIO_LLM_PLAN.md`](../SVCOMP26_PORTFOLIO_LLM_PLAN.md).

### 5. Keep svcomp26-vguide claim, but target v1.5.2 at 500+

A conservative next target:

- Current full-set: 493 solved.
- Convert retry-sensitive lost-solve diagnostics into single-run guards / resource policy: up to +5 observed in targeted reruns, but not claimable without full-set validation.
- Recover adaptive-budget old VGuide-only tasks observed here: +4 to +5 possible.

These are not automatically additive and cannot be claimed as runtime retry gains. They justify a v1.5.2 target around **500 solved** on the same 764-task set, with the key acceptance criterion remaining **0 wrong verdicts** and fewer lost baseline solves in a single full-set run.
