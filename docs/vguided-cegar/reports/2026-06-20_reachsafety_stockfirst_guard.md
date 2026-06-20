# ReachSafety stock-first guard (A1, v1.7.0) — schedule ablation (2026-06-20)

Validates A1 of [`../REACHSAFETY_IMPROVEMENT_PLAN.md`](../REACHSAFETY_IMPROVEMENT_PLAN.md): the
`every_n_or_interval` LLM-call schedule (fire only when stock is not converging — by refinement
count **or** wall-clock — never at refinement #1) recovers baseline solves the old fire-at-#1
schedule loses, with no regressions and no wrong verdicts.

## Setup

- Engine: `svcomp27-vguide` portfolio (identical both arms). Only `vguide.llmCallSchedule` differs.
  - **baseline**: `every_n_and_interval`, everyN=72 — fires at refinement #1 (old default).
  - **new**: `every_n_or_interval`, K=10 / D=15s — stock-first guard.
- Tasks: `benchmark_sets/reachsafety_lost_set.list` — the 15 case-study losses from
  [`2026-06-14_svcomp26_vguide_case_studies.md`](2026-06-14_svcomp26_vguide_case_studies.md)
  (10 lost + 5 adaptive-recovered). `timelimit=300`, `parallel=8`, live DeepSeek.
- Controlled: same portfolio, same tasks, same timelimit; only the schedule changes.

## Result: +4 recovered, 0 lost, 0 wrong

| task | expected | baseline (old) | new (`every_n_or_interval`) | |
|------|----------|----------------|------------------------------|---|
| nested-3 | true | UNKNOWN (33 ref, 60s) | **TRUE** (2 ref, 2.7s) | ✅ recovered |
| nested_5 | true | UNKNOWN (33 ref, 67s) | **TRUE** (11 ref, 8.0s) | ✅ recovered |
| functions_1-1 | true | UNKNOWN (31 ref, 59s) | **TRUE** (51 ref, 25s) | ✅ recovered |
| in-de41 | true | UNKNOWN (36 ref, 70s) | **TRUE** (11 ref, 7.6s) | ✅ recovered |
| sum_by_3 | true | TRUE (6 ref, 16s) | TRUE (8 ref, 5.4s) | retained |
| freire1_valuebound50 | true | TRUE (208s) | TRUE (181s) | retained |
| divbin_unwindbound20 | **false** | FALSE (7.4s) | FALSE (5.9s) | correct (FALSE task) |
| geo2/geo3/prodbin/lcm2_valuebound* | true | UNKNOWN | UNKNOWN | still lost (nonlinear) |
| fermat2_valuebound20 | true | UNKNOWN | UNKNOWN | still lost |
| count_by_nondet / down / up | true | UNKNOWN | UNKNOWN | still lost (churn, LLM fired late) |

Correct solves: baseline **3** → new **7** (= **+4**). 0 baseline solves lost. **0 wrong verdicts**
(divbin is a genuine FALSE task per its `.yml`; both arms correct).

## Interpretation

- **`nested-3` is the headline**: the documented portfolio regression reproduces under the old
  fire-at-#1 schedule (UNKNOWN, 33 refinements) and is **fixed** by the stock-first schedule
  (TRUE, 2 refinements) — stock converges before either trigger fires, so the LLM never perturbs it.
- The recovered tasks are ones stock can finish if the LLM doesn't derail/starve the first
  refinement; the still-lost ones are mostly `nla-digbench` nonlinear arithmetic (structurally hard)
  or churners where the LLM fires but the predicates don't converge in time.
- Standalone (non-portfolio) smoke earlier showed the same mechanism: on `nested-3`/`sum_by_3` the
  new schedule skips the LLM (stock solves ~7–10× faster); on `count_up_down-1` it fires at
  refinement 10 and still wins.

## Full 764-task result (both arms, controlled)

Same setup scaled to the whole `loops_reachsafety_unreach` set (764 tasks), both arms
`svcomp27-vguide`, only the schedule differs. Every solved verdict cross-checked against the
task `.yml` `unreach-call` `expected_verdict`.

| | baseline (old, fire-#1) | new (`every_n_or_interval`) |
|---|---|---|
| solved | 482 | **493** |
| TRUE / FALSE | 334 / 148 | 346 / 147 |
| UNKNOWN | 282 | 271 |
| **wrong verdicts** | **0** | **0** |

**Net +11 = +17 new − 6 lost, 0 wrong, 0 TRUE↔FALSE flips.**

- **+17 new** (UNKNOWN→solved): incl. `nested-3`, `nested_5`, `functions_1-1`, `in-de41`, `down`,
  `hhk2008`, `loopv1/2`, `mono-crafted_1/13`, `nested3-1`, `nested_6`, `lcm1_unwindbound2` (FALSE), …
- **−6 lost** (solved→UNKNOWN): `heapsort`, `nested9` (both **case-study direct-LLM-#1 wins** — they
  genuinely needed the LLM at refinement #1, which the stock-first schedule no longer provides),
  `iftelse`, `sumt4`, `array_1-1` (FALSE), `array_3-2` (FALSE).

The 6 regressions are the honest cost of never firing at #1, and they point directly at the next
step: the **peel-based trigger ①** (fire early when the refinement sequence is *diverging*, not at a
fixed count) would recover the churn-but-few-refinement wins like `heapsort`/`nested9` without
re-introducing the `nested-3`-type regressions. Tuning K/D is the cheaper lever to try first.

## Status

- `every_n_or_interval` (K=10/D=15s) is the default in `config/vguide.properties`. **Net +11 / 0 wrong
  on full 764** vs the old fire-at-#1 schedule.
- Next: peel-based trigger ① (recover the 6 early-need losses) + K/D tuning. See plan A1.2/A1.5.
