# svcomp26 portfolio deployment ladder — experiment plan (2026-06-23)

Paper target: unify Table 2 track **(ii)** on `svcomp26` only (no svcomp27). Track **(i)**
isolation rows are already recorded; this batch fills Steps 0–3 on the competition portfolio.

## Question

On Loops ReachSafety (764, 300s, 0-wrong gate), how does VGuide deploy on
`config/unmaintained/svcomp26-vguide.properties` when we (a) saturate against stock,
(b) stack stock-first scheduling, and (c) add the peel trigger — **on the same portfolio**?

Relates to the isolation asymmetry: v1.7.1 default (peel=4) scores **236 (+12)** on the
isolated predicate worker but is designed for portfolio use where parallel siblings absorb
peel misfires.

## Fixed conditions (all arms)

| Parameter | Value |
|-----------|-------|
| Set | `loops_reachsafety_unreach` (764) |
| Timelimit | 300s per task (+ 30s outer grace) |
| Parallel | 8 concurrent tasks **within** each arm |
| Config base | `svcomp26` / `svcomp26-vguide` |
| Spec | `sv-comp-reachability.spc` |
| LLM | DeepSeek V4 Pro, non-thinking (default) |
| Soundness gate | **0 wrong** vs `.yml` `expected_verdict` |

**Execution order:** arms run **sequentially** (Arm 0 finishes → Arm 1 → …). Do not start
two arms at once.

## Arms (Table 2 track ii)

| Arm | Step | Mode | Schedule overrides | Expected paper row |
|-----|------|------|--------------------|--------------------|
| 0 | Step 0 | `svcomp26` | (no LLM) | stock 486 baseline (**reuse** `loops_reachsafety_unreach_svcomp26_20260612`) |
| 1 | Step 1 | `svcomp26-vguide` | `every_n_and_interval`, `peelLoopHeadThreshold=0` | fire-at-#1; historical +7 → 493 |
| 2 | Step 2 | `svcomp26-vguide` | `every_n_or_interval`, `peelLoopHeadThreshold=0` | stock-first (skip #1; K=10/D=15s) |
| 3 | Step 3 | `svcomp26-vguide` | `every_n_or_interval`, `peelLoopHeadThreshold=4` | + peel (v1.7.1 default) |

Only the two options above differ between Arms 1–3; K/D/max rounds come from
`config/vguide.properties`.

## Output layout

```
output/vguide/experiments/svcomp26_deploy_20260623/
  run.log                 # master sequential log
  status.txt              # arm start/end + solved counts
  step0_stock/
  step1_fire1/
  step2_stockfirst/
  step3_peel4/
    loops_reachsafety_unreach_summary.csv
    logs/
```

## Launch

Arm 0 is **not re-run**; the batch symlinks
`output/vguide/experiments/loops_reachsafety_unreach_svcomp26_20260612` →
`svcomp26_deploy_<DATE>/step0_stock` (486 solved, PAR-2 222.5s, 0 wrong).

**2026-06-23 batch invalid** (nested vguide include swallowed `--option`). After config fix,
re-run with a fresh `SVCOMP26_DEPLOY_DATE` (default: today `YYYYMMDD`).

```bash
cd /home/swear01/cpachecker
export SVCOMP26_DEPLOY_DATE=20260624   # optional; default = date +%Y%m%d
nohup ./scripts/vguided-cegar/run_svcomp26_portfolio_deployment_sequential.sh \
  >> output/vguide/experiments/svcomp26_deploy_${SVCOMP26_DEPLOY_DATE:-$(date +%Y%m%d)}/nohup.out 2>&1 &
echo $! > output/vguide/experiments/svcomp26_deploy_${SVCOMP26_DEPLOY_DATE:-$(date +%Y%m%d)}/pid.txt
```

Resume from Arm 2 if Arm 1 already finished: `START_ARM=2 ./scripts/.../run_svcomp26_portfolio_deployment_sequential.sh`

Monitor:

```bash
tail -f output/vguide/experiments/svcomp26_deploy_20260623/run.log
wc -l output/vguide/experiments/svcomp26_deploy_20260623/step*/loops_reachsafety_unreach_summary.csv
```

## After completion (fill Table 2)

For each arm:

```bash
python3 scripts/vguided-cegar/summarize_arm.py \
  --out output/vguide/experiments/svcomp26_deploy_20260623/step1_fire1 \
  --set loops_reachsafety_unreach --timelimit 300
```

Record per arm: **solved** (TRUE+FALSE), **PAR-2**, **wrong**, **Δ vs Step 0**, **Δ vs Step 1**.

Update `report/main.tex` track (ii) Steps 2–3 (replace `---` placeholders).

## Risks

| Risk | Mitigation |
|------|------------|
| Wall time ~8–35 h total (4×764@300s/8) | Sequential start; status.txt for morning check |
| Step 1 refresh ≠ 493 | Report measured value; v1.5.1 493 is historical |
| Step 3 < Step 2 on svcomp26 | Report honestly; asymmetry story still holds if Step 2 > Step 1 |

## Docs

When numbers are final, update this file → `2026-06-23_svcomp26_portfolio_deployment.md` (results).
