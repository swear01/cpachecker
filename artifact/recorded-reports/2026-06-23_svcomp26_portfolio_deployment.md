# svcomp26 portfolio deployment — complete (2026-06-23)

**Status:** Valid sequential batch finished **2026-06-23 14:12** in
`output/vguide/experiments/svcomp26_deploy_20260623/`. Step 0 reuses stock
`loops_reachsafety_unreach_svcomp26_20260612`. Arms 1–3: config verified (schedule/peel, 0
`vguide.` mismatch), 764 tasks each, **0 wrong**.

| Step | Dir | Schedule | peel | Solved | Δ vs stock | PAR-2 |
|------|-----|----------|------|--------|------------|-------|
| 0 | `step0_stock` (reuse) | — | — | 486 | — | 222.5 |
| 1 | `step1_fire1` | `every_n_and_interval` | 0 | 493 | +7 | 217.9 |
| 2 | `step2_stockfirst` | `every_n_or_interval` | 0 | **505** | +19 | **209.0** |
| 3 | `step3_peel4` | `every_n_or_interval` | 4 | 505 | +19 | 211.3 |

**Paper:** `report/main.tex` Table 2 track (ii) cites this batch.

**Invalid (do not cite):** first 2026-06-23 batch (500/501/500) and dirs under `*.invalid.*`.
Root cause: nested `#include vguide.properties` in predicate components overrode CLI `--option`
(fixed: include only at portfolio top-level).

See [`2026-06-20_reachsafety_stockfirst_guard.md`](2026-06-20_reachsafety_stockfirst_guard.md) and
[`2026-06-20_reachsafety_peel_trigger.md`](2026-06-20_reachsafety_peel_trigger.md).
