# Pure predicate base vs VGuide v1.7.1 — decomposition (2026-06-22)

Overnight follow-up to the 2026-06-21 pure-predicate arm run. Goal: isolate why the v1.7.1
default schedule (`every_n_or_interval` + peel=4) under-performs the old v14 schedule
(`every_n_and_interval`, fires at the first CE, no peel) on the **pure predicate analysis**
(Loops ReachSafety, 764 tasks, parallel-16, 300s), and produce the v1.7.1 number for the
paper's `tab:safety` top rows.

## Setup

Same codebase (HEAD `aa122912d1`), same 764-task set, parallel-16, 300s wall. Only the LLM
firing schedule and peel threshold differ across arms. Every verdict cross-checked against
the `.yml` `unreach-call` `expected_verdict`.

| arm | schedule | peel | source dir |
|-----|----------|------|------------|
| base (stock) | — (vocab guide off) | — | `full764_pure_stock` |
| A2 | `every_n_and_interval` | 0 | `full764_pure_vguide_oldsched` |
| B  | `every_n_or_interval`  | 0 | `full764_pure_vguide_skip1_nopeel` |
| C  | `first_spurious`       | 0 | `full764_pure_vguide_firstspurious` |
| v1.7.1 default | `every_n_or_interval` | 4 | `full764_pure_vguide_v171` |
| v14 (old code, 2026-06-12) | `every_n_and_interval` | 0 | `loops_reachsafety_unreach_v14_20260612` |

## Result

| arm | solved | PAR-2 (s) | wrong | NET vs base |
|-----|--------|-----------|-------|-------------|
| base (stock) | 224 | 428.4 | 0 | — |
| **A2** and_interval p0 | **253** | 406.5 | 0 | **+29** |
| B  or_interval  p0 | 252 | 407.4 | 0 | +28 |
| C  first_spur   p0 | 245 | 411.3 | 0 | +21 |
| v1.7.1 default (p4) | 236 | 418.8 | 0 | +12 |
| v14 0612 (old code) | 262 | 399.7 | 0 | +38 |

**Soundness: 0 wrong verdicts on every arm.** No flips (TRUE↔FALSE) between any pair.

## Decomposing the 262 → 236 gap (−26)

Same config on old vs new code, then schedule levers peeled one at a time:

| step | delta | cause |
|------|-------|-------|
| v14 (262) → A2 (253) | −9 | codebase drift (dual-prompt / predicate-budget changes, 06-12 → v1.7.1) |
| A2 (253) → B (252) | −1 | fire-at-#1 vs skip-#1 (the eager-vs-lazy lever — nearly inert here) |
| B (252) → v1.7.1 (236) | −16 | peel=4 trigger (misfires on divbin / hard-u / hard2 families) |
| **total** | **−26** | |

### Key finding: peel is the main regressor, not skip-#1

The paper's scheduling section motivates `every_n_or_interval` (skip-#1) and peel=4 together
as the +22 portfolio gain. Decomposed on the **pure predicate** path they behave very
differently:

- **fire-at-#1 is nearly inert here.** A2 vs B differ by 1 task. The "eager first-CE" win that
  lifted v14 to 262 is not from firing *at #1* per se; it is from *repeating* (every-N) and
  from the old codebase. On the pure predicate analysis, skipping #1 costs almost nothing.
- **peel=4 is the regressor.** The 23 lost tasks (divbin2_*, divbin_*, hard-u_*, hard2_*) all
  follow the same pattern confirmed in the logs: the CE passes loop heads **exactly 4 times**
  = the peel threshold, on tasks stock would solve in 2–15 s. peel fires at refinement #2–4,
  the injected predicates derail the converging analysis, refinement blows up to 8–40, and the
  SMT solver hangs into a 300 s timeout. The peel calibration (nested-3 peaks at 3 → never
  fire) did not cover the divbin/hard families, which are *converging but cross 4 loop-head
  visits*. 35 genuine-divergence wins minus 23 misfire losses ≈ net −16.

### Why the asymmetry vs the portfolio (+22 there, −16 here)

The portfolio runs symbolic execution, k-induction, and value analysis in parallel. Those
cover the "stock solves in 1–2 refinements" tasks, so on the portfolio peel never has the
chance to derail a task a parallel worker would already solve — peel only ever fires on
genuine divergence and is pure gain (+22). The pure predicate analysis has no safety net:
every task relies on the single predicate worker, so peel misfires land directly as losses.

This is a real configuration-dependent asymmetry, not a soundness issue (0 wrong on both).

## Paper update

`report/main.tex` updated to the v1.7.1 pure-predicate numbers (A2 = the faithful v1.7.1
reproduction of the v14 schedule):

- `tab:safety` top two rows: `225 / 426.2 → 224 / 428.4` (stock) and `262 (+37) / 399.7 → 253 (+29) / 406.5` (+VGuide).
- abstract: `225→262`, `37 more` → `224→253`, `29 more`.
- contributions / conclusion: `37/7/19` → `29/7/19`.
- Predicate Oracle prose: `$225\to262$, $+16.4\%$`, `426.2 to 399.7` → `$224\to253$, $+12.9\%$`, `428.4 to 406.5`.
- Ablation paragraph: source-prior `225` → `224` (identical-to-stock claim unchanged); the
  vguide arm label corrected from "first-spurious" to "every-N-and-interval, firing at the
  first CE" (what v14 actually ran, per `loops_reachsafety_unreach_v14_20260612` logs:
  `schedule= EVERY_N_AND_INTERVAL prompt= first`, 619 first-CE rounds, 0 peel lines).

svcomp26 portfolio (486→493), combined ReachSafety/NoOverflow (479→494 / 362→366), and the
scheduling table (482→504) are unchanged — those are portfolio-side numbers, not the pure
predicate isolation, and were re-confirmed on the same codebase in
`full764_baseline_oldsched` / `full764_new_orinterval` / `full764_peel4`.

## Verification

- `pdflatex -interaction=nonstopmode -halt-on-error main.tex` (×2): 0 errors, 0 undefined refs,
  11-page PDF.
- All six arms: 0 wrong verdicts, 0 TRUE↔FALSE flips.

## Open items

- The source-prior ablation's `224` (identical to stock) is carried over from the
  identical-to-stock claim; a v1.7.1 re-run of `--mode source-prior-loops` was not part of this
  overnight batch. If desired, run it to pin that number too.
- The peel=4 misfire on divbin/hard-u/hard2 is a real v1.7.1 calibration gap (threshold
  calibrated only on nested-3). Not addressed here; potential follow-up is a higher threshold
  or a convergence predicate on the peel trigger.
