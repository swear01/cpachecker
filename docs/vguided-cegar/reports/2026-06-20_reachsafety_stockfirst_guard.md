# ReachSafety stock-first guard (A1) — schedule ablation (2026-06-20)

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

## Status

- Made `every_n_or_interval` (K=10/D=15s) the default in `config/vguide.properties`.
- Full 764-task `loops_reachsafety_unreach` both-arm run: see follow-up (net delta on the whole set).
