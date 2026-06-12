# VGuide × svcomp27 pilot calibration and full-set readiness（2026-06-13）

Branch：`svcomp-integration`

## Task A — sample workflow regression

Goal：prove that the svcomp27 integration branch does not change the existing single-analysis `predicateAnalysis-vguide.properties` workflow used by `./scripts/vguided-cegar/run.sh cpa --set sample`.

### Runs

| Run | Commit/source | Output | Dump |
|-----|---------------|--------|------|
| baseline | `main` worktree at `6b0046c44a` | `/home/swear01/cpachecker_main_baseline/output/vguide/experiments/sample_main_baseline_20260613/` | `/home/swear01/cpachecker_main_baseline/output/vguide/analysis_dumps/sample_main_baseline_20260613/` |
| branch | `svcomp-integration` | `output/vguide/experiments/sample_svcomp_integration_20260613/` | `output/vguide/analysis_dumps/sample_svcomp_integration_20260613/` |

Baseline build note：`main` at `6b0046c44a` required `ant -Dcompile.warn=true build-project` because an existing `PredicateScorer.fmgr` warning is promoted to error by `-Werror`; this is unrelated to the integration branch.

### Verdict comparison

| Task | Baseline | Branch | Match |
|------|----------|--------|-------|
| `array_3-1` | TRUE | TRUE | yes |
| `array_3-2` | UNKNOWN | UNKNOWN | yes |
| `array_4` | UNKNOWN | UNKNOWN | yes |
| `down` | UNKNOWN | UNKNOWN | yes |
| `heapsort` | TRUE | TRUE | yes |
| `large_const` | TRUE | TRUE | yes |
| `string_concat-noarr` | UNKNOWN | UNKNOWN | yes |
| `up` | UNKNOWN | UNKNOWN | yes |

Result：**8/8 verdicts match**. No behavioral regression was observed.

### Dump / CSV compatibility checks

- Summary CSV header is unchanged: `task,rel_path,result,refinements,wall_s,log`.
- Baseline dump task directories: `array_3-1`, `array_3-2`, `array_4`, `down`, `heapsort`, `large_const`, `string_concat-noarr`, `up`.
- Branch dump task directories are the same and contain **no `__bN` suffixes**, preserving single-analysis workflow compatibility.
- Branch `refinements.jsonl` rows include the new expected fields `task_base` and `bridge_index`.
- Branch logs contain no `process_round_cap` skip reason.

Verification command used for the comparison:

```bash
python3 - <<'PY'
# compared sample_summary.csv verdicts, checked dump task dirs, checked jsonl fields,
# and scanned branch logs for process_round_cap
PY
```

## Task B — portfolio verdict attribution tool

Tool：`scripts/vguided-cegar/attribute_svcomp_verdicts.py`

Inputs：single CPAchecker log, a runner `logs/<task>.log` directory, or a smoke-test directory containing `*/cpa.log` files.

CSV schema：

```text
task,verdict,selection_branch,restart_stage,deciding_component,vguide_fired,llm_rounds
```

Parser notes：

- `deciding_component` uses ParallelAlgorithm's `<config>.properties finished successfully.` log signal when present.
- `selection_branch` and `restart_stage` are inferred from nested log prefixes such as `Analysis <config>:` and `Parallel analysis <config>:`.
- Missing or ambiguous signals are reported as `unknown`; the tool does not crash.

Validation command：

```bash
python3 -m py_compile scripts/vguided-cegar/attribute_svcomp_verdicts.py
scripts/vguided-cegar/attribute_svcomp_verdicts.py \
  output/vguide/svcomp_integration_smoke \
  --out output/vguide/svcomp_integration_smoke/attribution.csv
```

Smoke-log attribution output:

| task | verdict | selection_branch | restart_stage | deciding_component | vguide_fired | llm_rounds |
|------|---------|------------------|---------------|--------------------|--------------|-----------:|
| routeA_count_up_down_1 | TRUE | single_loop | parallel_single_loop | svcomp27--singleLoop-predicateAnalysis.properties | true | 1 |
| routeA_count_up_down_2 | FALSE | single_loop | parallel_single_loop | svcomp27--singleLoop-predicateAnalysis.properties | true | 0 |
| routeA_recursive_addition01 | UNKNOWN | loop_free | recursion | svcomp27--recursion.properties | false | 0 |
| routeA_recursive_evenodd01 | UNKNOWN | loop_free | recursion | svcomp27--recursion.properties | false | 0 |
| routeA_up | UNKNOWN | multiple_loops | parallel_multiple_loops | parallel_multiple_loops | true | 1 |
| routeB_scoped_count_up_down_1 | TRUE | single_loop | parallel_single_loop | svcomp27-vguide--singleLoop-predicateAnalysis.properties | true | 1 |
| routeB_scoped_recursive_addition01 | UNKNOWN | loop_free | recursion | svcomp27--recursion.properties | false | 0 |

Important check：`routeB_scoped_recursive_addition01` has `vguide_fired=false`, matching the scoped-config requirement that recursion/BAM stays on the official non-VGuide config path.

## Task C — stock svcomp27 runner mode

Added `--mode svcomp27-stock` to `scripts/vguided-cegar/run.sh`.

Behavior:

- `VGUIDE_CONFIG=config/svcomp27.properties`
- `VGUIDE_SPEC=config/specification/sv-comp-reachability.spc`
- `VGUIDE_SVCOMP=1`
- `VGUIDE_USE_VOCABULARY_GUIDE=false` only for runner API-key gating; the svcomp-mode command path still does **not** pass any global `cpa.predicate.refinement.useVocabularyGuide` option.
- Default output directory: `output/vguide/experiments/<set>_svcomp27_stock`.

Verification:

```bash
bash -n scripts/vguided-cegar/run.sh scripts/vguided-cegar/run_benchmark_set.sh
unset DEEPSEEK_API_KEY
./scripts/vguided-cegar/run.sh cpa --set sample --mode svcomp27-stock \
  --parallel 1 --timelimit 5 --dry-run \
  --out output/vguide/experiments/taskC_stock_dryrun
```

The dry-run command used `--config config/svcomp27.properties` and `--spec config/specification/sv-comp-reachability.spc`; no `cpa.predicate.refinement.useVocabularyGuide` option appeared in the generated command.

## Task D — corrected 20-task pilot calibration

### Resource and timeout setup

Machine observed before pilot:

- CPU: `nproc = 32`
- RAM: `125GiB` total, `107GiB` available at start

Runner timeout behavior:

- `run.sh --timelimit N` forwards `TIMELIMIT=N`.
- `run_benchmark_set.sh` runs `timeout "$((TIMELIMIT + VGUIDE_TIMEOUT_GRACE))s" scripts/cpa.sh ... --timelimit "${TIMELIMIT}s"`.
- For this pilot, `--timelimit 900` and `VGUIDE_TIMEOUT_GRACE=180` were used, so CPAchecker had 900s CPU-time limit and the outer wall timeout was 1080s.

Heap / parallel choice:

- A 2-task heap probe with `--heap 4000M --parallel 2` showed each svcomp27 CPAchecker process using roughly 1.3--1.4GiB RSS early in the run and about 4 CPU cores.
- Pilot used `--heap 4000M --parallel 6`: at most about 30 internal analysis threads, and the measured batch peak RSS stayed near 6GiB, far below 70% of physical RAM.

### Selection correction

A first pilot selection accidentally classified expected verdicts using any property in the `.yml`, which mixed in `no-overflow.prp` FALSE labels. Because this svcomp27 runner uses reachability spec, the committed pilot list was corrected to use only `unreach-call.prp` expected verdicts from `full_scalar`.

Committed list: `docs/vguided-cegar/benchmark_sets/svcomp27_pilot_20.list`

| path | unreach expected | bytes |
| --- | --- | --- |
| `loop-acceleration/overflow_1-1.c` | TRUE | 476 |
| `loops-crafted-1/mono-crafted_1.c` | TRUE | 529 |
| `loop-invariants/const.c` | TRUE | 610 |
| `loop-acceleration/phases_2-2.c` | TRUE | 731 |
| `loops-crafted-1/sumt3.c` | TRUE | 814 |
| `loops-crafted-1/sumt8.c` | TRUE | 1024 |
| `loops/sum03-2.i` | TRUE | 1108 |
| `loop-invgen/up.i` | TRUE | 1163 |
| `loop-invgen/nest-if3.i` | TRUE | 1277 |
| `loop-invgen/apache-escape-absolute.i` | TRUE | 2865 |
| `loop-acceleration/simple_1-1.c` | FALSE | 477 |
| `loops-crafted-1/Mono5_1.c` | FALSE | 506 |
| `loops-crafted-1/Mono1_1-1.c` | FALSE | 520 |
| `loop-acceleration/simple_2-2.c` | FALSE | 556 |
| `loops/while_infinite_loop_4.c` | FALSE | 581 |
| `loop-invariants/linear-inequality-inv-b.c` | FALSE | 660 |
| `loops-crafted-1/nested3-2.c` | FALSE | 716 |
| `loops/trex01-1.c` | FALSE | 963 |
| `loops/sum01_bug02.i` | FALSE | 1075 |
| `loop-invgen/id_trans.i` | FALSE | 1434 |

Rationale: 10 TRUE + 10 FALSE reachability tasks, sampled across file-size quantiles from `full_scalar` to include tiny, medium, and larger scalar loop programs.

### Commands

Stock:

```bash
VGUIDE_TIMEOUT_GRACE=180 \
/usr/bin/time -v ./scripts/vguided-cegar/run.sh cpa \
  --set svcomp27_pilot_20 --mode svcomp27-stock \
  --parallel 6 --timelimit 900 --heap 4000M \
  --out output/vguide/experiments/svcomp27_pilot20_reach_stock_20260613
```

VGuide:

```bash
VGUIDE_TIMEOUT_GRACE=180 \
VGUIDE_ANALYSIS_DUMP_DIR=output/vguide/analysis_dumps/svcomp27_pilot20_reach_vguide_20260613 \
VGUIDE_ANALYSIS_BENCHMARK_SET=svcomp27_pilot_20 \
VGUIDE_ANALYSIS_TIMELIMIT_SEC=900 \
/usr/bin/time -v ./scripts/vguided-cegar/run.sh cpa \
  --set svcomp27_pilot_20 --mode svcomp \
  --parallel 6 --timelimit 900 --heap 4000M \
  --out output/vguide/experiments/svcomp27_pilot20_reach_vguide_20260613
```

Attribution CSVs:

- `output/vguide/experiments/svcomp27_pilot20_reach_stock_20260613/svcomp_attribution.csv`
- `output/vguide/experiments/svcomp27_pilot20_reach_vguide_20260613/svcomp_attribution.csv`

### Verdict / time / LLM comparison

`log rounds` is from `attribute_svcomp_verdicts.py` log parsing. `dump rounds` / `API calls` are from VGuide dump JSONL; a task can have a dump round even if another parallel component wins before the LLM-round summary log is emitted.

| task | exp | stock | stock_s | vguide | vguide_s | log rounds | dump rounds | API calls |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `overflow_1-1` | TRUE | UNKNOWN | 416.445 | TRUE | 5.809 | 1 | 1 | 2 |
| `mono-crafted_1` | TRUE | UNKNOWN | 327.052 | UNKNOWN | 326.533 | 1 | 1 | 2 |
| `const` | TRUE | TRUE | 2.617 | TRUE | 2.782 | 0 | 0 | 0 |
| `phases_2-2` | TRUE | TRUE | 6.861 | TRUE | 3.061 | 0 | 0 | 0 |
| `sumt3` | TRUE | TRUE | 5.180 | TRUE | 5.337 | 0 | 1 | 1 |
| `sumt8` | TRUE | UNKNOWN | 424.336 | UNKNOWN | 425.428 | 1 | 1 | 2 |
| `sum03-2` | TRUE | TRUE | 2.533 | TRUE | 2.074 | 0 | 0 | 0 |
| `up` | TRUE | UNKNOWN | 408.478 | UNKNOWN | 406.744 | 1 | 1 | 2 |
| `nest-if3` | TRUE | UNKNOWN | 469.691 | UNKNOWN | 466.450 | 1 | 1 | 2 |
| `apache-escape-absolute` | TRUE | TRUE | 3.463 | TRUE | 4.189 | 0 | 0 | 0 |
| `simple_1-1` | FALSE | UNKNOWN | 415.273 | UNKNOWN | 413.913 | 1 | 1 | 2 |
| `Mono5_1` | FALSE | UNKNOWN | 416.790 | UNKNOWN | 415.184 | 1 | 1 | 2 |
| `Mono1_1-1` | FALSE | UNKNOWN | 426.571 | UNKNOWN | 424.917 | 1 | 1 | 2 |
| `simple_2-2` | FALSE | FALSE | 1.358 | FALSE | 1.412 | 0 | 0 | 0 |
| `while_infinite_loop_4` | FALSE | FALSE | 1.069 | FALSE | 1.065 | 0 | 0 | 0 |
| `linear-inequality-inv-b` | FALSE | FALSE | 0.994 | FALSE | 1.054 | 0 | 0 | 0 |
| `nested3-2` | FALSE | UNKNOWN | 323.863 | UNKNOWN | 321.216 | 3 | 3 | 6 |
| `trex01-1` | FALSE | FALSE | 1.059 | FALSE | 1.503 | 0 | 0 | 0 |
| `sum01_bug02` | FALSE | FALSE | 1.429 | FALSE | 1.526 | 0 | 0 | 0 |
| `id_trans` | FALSE | FALSE | 1.322 | FALSE | 1.239 | 0 | 0 | 0 |

Summary against `unreach-call.prp` expected verdict:

| Arm | Correct | Unknown | Wrong |
|-----|--------:|--------:|------:|
| stock svcomp27 | 11 | 9 | 0 |
| scoped VGuide | 12 | 8 | 0 |

Pilot observation: VGuide solved `overflow_1-1` (TRUE) quickly where stock reached UNKNOWN under the 900s CPU limit. No wrong verdicts were observed in this pilot.

### Heuristic branch and deciding component distribution

Selection branches:

| Arm | single_loop | multiple_loops | loop_free | complex | recursion/concurrency |
|-----|------------:|---------------:|----------:|--------:|----------------------:|
| stock | 14 | 6 | 0 | 0 | 0 |
| VGuide | 14 | 6 | 0 | 0 | 0 |

Deciding components:

| Arm | Component | Count |
|-----|-----------|------:|
| stock | `parallel_single_loop` (no child finished) | 5 |
| stock | `parallel_multiple_loops` (no child finished) | 4 |
| stock | `svcomp27--singleLoop-IMC.properties` | 4 |
| stock | `svcomp27--singleLoop-predicateAnalysis.properties` | 3 |
| stock | `svcomp27--singleLoop-symbolicExecution.properties` | 2 |
| stock | `svcomp27--multipleLoops-predicateAnalysis.properties` | 2 |
| VGuide | `svcomp27--singleLoop-IMC.properties` | 6 |
| VGuide | `parallel_single_loop` (no child finished) | 4 |
| VGuide | `parallel_multiple_loops` (no child finished) | 4 |
| VGuide | `svcomp27-vguide--singleLoop-predicateAnalysis.properties` | 2 |
| VGuide | `svcomp27-vguide--multipleLoops-predicateAnalysis.properties` | 2 |
| VGuide | `svcomp27--singleLoop-symbolicExecution.properties` | 2 |

Predicate/VGuide components decided 4/20 tasks in the VGuide arm (`overflow_1-1`, `apache-escape-absolute`, `while_infinite_loop_4`, `trex01-1`).

### LLM behavior

- VGuide dump: 12 unique LLM rounds across 10 tasks, 23 API calls total.
- API latency from `llm_rounds.jsonl`: min 1209ms, median 1640ms, max 2372ms.
- `process_round_cap`: 0 log hits.
- `vguide.maxLlmRoundsPerProcess=10` was not reached by any pilot task.
- `llmMinIntervalSec=15` interval distribution: not exercised in a meaningful way. Most VGuide tasks had only one LLM round; the only multi-round task was `nested3-2` with 3 rounds, but current dump JSONL records per-call latency and refinement/round indices, not absolute timestamps. Therefore exact inter-call wall-clock intervals cannot be reconstructed from the dump alone.

### Memory and parallel recommendation

Measured `/usr/bin/time -v`:

| Arm | Batch elapsed | CPU utilization | Max RSS |
|-----|---------------|----------------:|--------:|
| stock | 14:04.87 | 974% | 6,071,508 KB |
| VGuide | 12:34.64 | 973% | 6,005,364 KB |

The peak RSS is the maximum observed child process, not total machine RSS. With `--heap 4000M`, `--parallel 6` ran stably and used about 10 effective CPU cores at batch level; individual active CPAchecker processes often used around 3--4 CPU cores.

Full-set recommendation:

- `--heap 4000M`
- `--parallel 6` default for the one-click full-set script. This maps to about 30 internal svcomp analysis threads and a conservative Java heap envelope of 24GiB, comfortably below 70% of the 125GiB machine RAM.
- If the machine is otherwise idle, `--parallel 8` is likely still memory-safe (32GiB heap envelope), but may oversubscribe CPU because each CPAchecker process runs a 5-analysis svcomp portfolio.

Parameter recommendation (do not change config defaults yet):

- Keep `vguide.maxLlmRoundsPerProcess=10` for svcomp scoped config: pilot never hit the cap.
- Keep `llmMinIntervalSec=15`: pilot API latency was low and the schedule rarely reached a second eligible round; no data supports reducing it.
- If full set shows many long UNKNOWN tasks with only one LLM round, consider lowering `every_n` or adding a second earlier scheduled call, but that is a future tuning decision after full-set attribution.

## Task E — full-set nohup launcher

Added launcher: `scripts/vguided-cegar/run_svcomp_full_nohup.sh`

Default behavior:

- Set: `full_scalar`
- Arms: `svcomp27-stock` then scoped `svcomp` VGuide
- Timelimit: 900s CPU per task
- Outer timeout grace: 180s
- Heap: `4000M`
- Parallel: `6` by default, based on Task D pilot
- VGuide dump root: `output/vguide/analysis_dumps/<set>_svcomp27_vguide_<stamp>`
- After each arm, run `attribute_svcomp_verdicts.py` and write `<out>/svcomp_attribution.csv`
- For real runs, default is detached `nohup` with a launcher log under `output/vguide/experiments/svcomp_full_logs/`
- `--foreground` is available for smoke tests; `--dry-run` prints commands without execution

### Dry-run verification

Command:

```bash
./scripts/vguided-cegar/run_svcomp_full_nohup.sh --dry-run --stamp DRYRUN_20260613
```

Output excerpt:

```text
set=full_scalar tasks=217 arm=both arm_count=2
timelimit=900s grace=180s heap=4000M parallel=6
estimated_wall_time=18h5m0s (tasks * timelimit * arms / parallel; pessimistic)
stock_out=output/vguide/experiments/full_scalar_svcomp27_stock_DRYRUN_20260613
vguide_out=output/vguide/experiments/full_scalar_svcomp27_vguide_DRYRUN_20260613
vguide_dump=output/vguide/analysis_dumps/full_scalar_svcomp27_vguide_DRYRUN_20260613
[dry-run] env VGUIDE_TIMEOUT_GRACE=180 ... run.sh cpa --set full_scalar --mode svcomp27-stock --parallel 6 --timelimit 900 --heap 4000M --out output/vguide/experiments/full_scalar_svcomp27_stock_DRYRUN_20260613
[dry-run] env VGUIDE_TIMEOUT_GRACE=180 VGUIDE_ANALYSIS_DUMP_DIR=output/vguide/analysis_dumps/full_scalar_svcomp27_vguide_DRYRUN_20260613 VGUIDE_ANALYSIS_BENCHMARK_SET=full_scalar VGUIDE_ANALYSIS_TIMELIMIT_SEC=900 ... run.sh cpa --set full_scalar --mode svcomp --parallel 6 --timelimit 900 --heap 4000M --out output/vguide/experiments/full_scalar_svcomp27_vguide_DRYRUN_20260613
```

No full-set run was launched by this dry-run.

### 2-task smoke verification

Committed smoke set: `docs/vguided-cegar/benchmark_sets/svcomp27_smoke_2.list`

Command:

```bash
./scripts/vguided-cegar/run_svcomp_full_nohup.sh \
  --foreground --arm both --set svcomp27_smoke_2 \
  --parallel 2 --timelimit 60 --heap 4000M --stamp SMOKE_20260613
```

Outputs:

- stock: `output/vguide/experiments/svcomp27_smoke_2_svcomp27_stock_SMOKE_20260613/`
- VGuide: `output/vguide/experiments/svcomp27_smoke_2_svcomp27_vguide_SMOKE_20260613/`
- VGuide dump: `output/vguide/analysis_dumps/svcomp27_smoke_2_svcomp27_vguide_SMOKE_20260613/`

Smoke attribution tables:

Stock:

| task | verdict | selection_branch | restart_stage | deciding_component | vguide_fired | llm_rounds |
|------|---------|------------------|---------------|--------------------|--------------|-----------:|
| `overflow_1-1` | UNKNOWN | single_loop | parallel_single_loop | parallel_single_loop | false | 0 |
| `simple_1-1` | UNKNOWN | single_loop | parallel_single_loop | parallel_single_loop | false | 0 |

VGuide:

| task | verdict | selection_branch | restart_stage | deciding_component | vguide_fired | llm_rounds |
|------|---------|------------------|---------------|--------------------|--------------|-----------:|
| `overflow_1-1` | TRUE | single_loop | parallel_single_loop | svcomp27-vguide--singleLoop-predicateAnalysis.properties | true | 1 |
| `simple_1-1` | UNKNOWN | single_loop | parallel_single_loop | parallel_single_loop | true | 1 |

End-to-end checks:

- Both arms ran sequentially from the launcher.
- Both arms produced summary CSVs.
- Both arms produced `svcomp_attribution.csv` via automatic post-processing.
- Scoped VGuide arm produced analysis dumps.

### Full-set launch command for user

To launch both full-set arms detached with default calibrated parameters:

```bash
cd /home/swear01/cpachecker
./scripts/vguided-cegar/run_svcomp_full_nohup.sh --arm both
```

The script prints the PID and log path. Monitor with:

```bash
tail -f output/vguide/experiments/svcomp_full_logs/full_scalar_both_<STAMP>.log
```

Optional arm-specific launches:

```bash
./scripts/vguided-cegar/run_svcomp_full_nohup.sh --arm stock
./scripts/vguided-cegar/run_svcomp_full_nohup.sh --arm vguide
```

Override defaults if needed:

```bash
./scripts/vguided-cegar/run_svcomp_full_nohup.sh --arm both --parallel 8 --heap 4000M
```

Reminder: full set was **not** launched as part of this preparation task.
