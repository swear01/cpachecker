# svcomp26 portfolio deployment — re-run in progress (2026-06-23)

**Status:** Clean re-run of arms 1–3 started **2026-06-23 10:21** after config fix and archiving
invalid dirs (`step*.invalid.*`). Step 0 reuses stock `loops_reachsafety_unreach_svcomp26_20260612`
(486 solved, PAR-2 222.5). Monitor:

```bash
tail -f output/vguide/experiments/svcomp26_deploy_20260623/run.log
wc -l output/vguide/experiments/svcomp26_deploy_20260623/step*/loops_reachsafety_unreach_summary.csv
```

**Invalid (do not cite):** first 2026-06-23 batch (500/501/500) and partial 10:15 re-run into same
dirs (duplicate summary rows). Root cause: nested `#include vguide.properties` in predicate components
overrode CLI `--option` for `vguide.llmCallSchedule` / `peelLoopHeadThreshold` (fixed: include only at
portfolio top-level).

**Paper interim:** Steps 2–3 still cite controlled `full764_*` arms until this re-run completes.

| Arm | Output dir | Schedule | peel |
|-----|------------|----------|------|
| 1 fire@#1 | `step1_fire1` | `every_n_and_interval` | 0 |
| 2 stock-first | `step2_stockfirst` | `every_n_or_interval` | 0 |
| 3 peel=4 | `step3_peel4` | `every_n_or_interval` | 4 |

Historical Step 1 (competition): **493 (+7 vs stock 486)** from `loops_reachsafety_unreach_svcomp26vguide_20260614`.

See [`2026-06-20_reachsafety_stockfirst_guard.md`](2026-06-20_reachsafety_stockfirst_guard.md) and
[`2026-06-20_reachsafety_peel_trigger.md`](2026-06-20_reachsafety_peel_trigger.md).
