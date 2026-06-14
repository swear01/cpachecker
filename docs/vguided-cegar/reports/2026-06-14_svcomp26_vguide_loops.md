# svcomp26-vguide Loops ReachSafety full-set results（v1.5.1, 2026-06-14）

- **Tag target**：`vguide-v1.5.1`
- **Branch**：`svcomp-integration`
- **Dataset**：`loops_reachsafety_unreach`，官方 SV-COMP `Loops.set` 中含 `unreach-call.prp` 的 764 個 property entries
- **Expected**：TRUE 532 / FALSE 232（來自 `docs/vguided-cegar/benchmark_sets/loops_reachsafety_unreach.list` 的 `expected=` metadata）
- **Timelimit**：300s per task
- **Main comparison**：`config/unmaintained/svcomp26-vguide.properties` vs `config/unmaintained/svcomp26.properties`

## Executive result

`svcomp26-vguide` 在同一個 764 題 Loops ReachSafety set、同一個 300s 時限下，
**小幅但確定地勝過既有 svcomp26 strong baseline**：

```text
svcomp26 baseline: 486 solved, 0 wrong
svcomp26-vguide:   493 solved, 0 wrong
net gain:          +7 solved
PAR-2 avg:         222.45s → 216.90s
```

這是目前最強且最乾淨的 v1.5.1 claim：

> **將 VGuide scoped 接進 svcomp26 portfolio 後，在官方 SV-COMP Loops ReachSafety 764 題上，
> 相對同一個 svcomp26 portfolio baseline 達成 +7 solved、0 wrong、PAR-2 改善；
> 其中 16 個 new solves 是由 VGuide predicate component 在有 LLM round 的情況下直接給出 verdict。**

邊界同樣重要：這不是 strict superset（有 10 個 lost solves），也不是正式 SV-COMP 競賽可提交設定
（線上 LLM 不符合離線競賽環境）。

## Runs

| Run | Config / mode | Parallel | Output |
|-----|---------------|---------:|--------|
| stock simple predicate | `--mode stock` | 8 | `output/vguide/experiments/loops_reachsafety_unreach_stock_20260612/` |
| svcomp26 baseline | `--mode svcomp26` | 1 | `output/vguide/experiments/loops_reachsafety_unreach_svcomp26_20260612/` |
| old v1.4 VGuide single-analysis | `--mode vguide` | 4 | `output/vguide/experiments/loops_reachsafety_unreach_v14_20260612/` |
| **svcomp26-vguide** | `--mode svcomp26-vguide` | 6 | `output/vguide/experiments/loops_reachsafety_unreach_svcomp26vguide_20260614/` |

Full-set command used for the new arm:

```bash
VGUIDE_TIMEOUT_GRACE=180 \
VGUIDE_ANALYSIS_DUMP_DIR=output/vguide/analysis_dumps/loops_reachsafety_unreach_svcomp26vguide_20260614 \
VGUIDE_ANALYSIS_BENCHMARK_SET=loops_reachsafety_unreach \
VGUIDE_ANALYSIS_TIMELIMIT_SEC=300 \
VGUIDE_LLM_THINKING=disabled \
./scripts/vguided-cegar/run.sh cpa --set loops_reachsafety_unreach --mode svcomp26-vguide \
  --parallel 6 --timelimit 300 --heap 4000M \
  --out output/vguide/experiments/loops_reachsafety_unreach_svcomp26vguide_20260614
```

## Topline

PAR-2 uses 600s for UNKNOWN or wrong verdicts.

| Run | TRUE | FALSE | UNKNOWN | Solved | Correct / Solved | Wrong | PAR-2 avg | Solved wall avg |
|-----|-----:|------:|--------:|-------:|-----------------:|------:|----------:|----------------:|
| stock simple predicate | 165 | 60 | 539 | 225 | 225 / 225 | 0 | 426.21s | 9.87s |
| svcomp26 baseline | 334 | 152 | 278 | 486 | 486 / 486 | 0 | 222.45s | 6.49s |
| old v1.4 VGuide | 202 | 60 | 502 | 262 | 262 / 262 | 0 | 399.72s | 15.97s |
| **svcomp26-vguide** | **341** | **152** | **271** | **493** | **493 / 493** | **0** | **216.90s** | **6.31s** |

Delta vs svcomp26 baseline:

| Metric | Delta |
|--------|------:|
| Solved | **+7** |
| TRUE | +7 |
| FALSE | 0 |
| UNKNOWN | -7 |
| Wrong verdicts | 0 |
| PAR-2 sum | **-4240.5s** |
| PAR-2 avg | **-5.55s** |

## Overlap vs svcomp26 baseline

| Comparison | Count | Notes |
|------------|------:|-------|
| New solves | 17 | 16 expected TRUE + 1 expected FALSE |
| Lost solves | 10 | 9 expected TRUE + 1 expected FALSE |
| Disagreements | 0 | no task solved with opposite TRUE/FALSE verdict |
| Both solved | 476 | same verdict |
| Both UNKNOWN | 261 | unchanged unknown |
| Net solved | **+7** | 493 − 486 |

Summary: **17 new solves / 10 lost solves / 0 disagreements / net +7 solved**.

### New solves

These were UNKNOWN under `svcomp26` and solved by `svcomp26-vguide`:

| Task | Expected / result | Deciding component | LLM rounds |
|------|-------------------|--------------------|-----------:|
| `benchmark19_conjunctive` | TRUE | `svcomp26-vguide--singleLoop-predicateAnalysis.properties` | 1 |
| `benchmark34_conjunctive` | TRUE | `svcomp26-vguide--singleLoop-predicateAnalysis.properties` | 1 |
| `bhmr2007` | TRUE | `svcomp26-vguide--singleLoop-predicateAnalysis.properties` | 1 |
| `count_by_2` | TRUE | `svcomp26-vguide--singleLoop-predicateAnalysis.properties` | 1 |
| `count_up_down-1` | TRUE | `svcomp26-vguide--singleLoop-predicateAnalysis.properties` | 1 |
| `divbin` | FALSE | `svcomp26--multipleLoops-symbolicExecution.properties` | 0 |
| `gj2007b` | TRUE | `svcomp26-vguide--singleLoop-predicateAnalysis.properties` | 1 |
| `heapsort` | TRUE | `svcomp26-vguide--multipleLoops-predicateAnalysis.properties` | 1 |
| `hhk2008` | TRUE | `svcomp26-vguide--singleLoop-predicateAnalysis.properties` | 1 |
| `jm2006_variant` | TRUE | `svcomp26-vguide--singleLoop-predicateAnalysis.properties` | 1 |
| `loopv1` | TRUE | `svcomp26-vguide--singleLoop-predicateAnalysis.properties` | 1 |
| `mono-crafted_1` | TRUE | `svcomp26-vguide--multipleLoops-predicateAnalysis.properties` | 1 |
| `mono-crafted_12` | TRUE | `svcomp26-vguide--singleLoop-predicateAnalysis.properties` | 1 |
| `mono-crafted_9` | TRUE | `svcomp26-vguide--singleLoop-predicateAnalysis.properties` | 1 |
| `nested9` | TRUE | `svcomp26-vguide--multipleLoops-predicateAnalysis.properties` | 1 |
| `nested_delay_nd` | TRUE | `svcomp26-vguide--multipleLoops-predicateAnalysis.properties` | 1 |
| `overflow_1-1` | TRUE | `svcomp26-vguide--singleLoop-predicateAnalysis.properties` | 1 |

Interpretation: **16/17 new solves are direct LLM/VGuide predicate wins**. `divbin` is a portfolio side effect
(the unchanged symbolic-execution component won), so it should not be counted as direct LLM contribution.

15 of these direct LLM wins overlap with the 33 old v1.4 VGuide-only TRUE solves from
[`2026-06-13_v1.5_loops_reachsafety_unreach.md`](2026-06-13_v1.5_loops_reachsafety_unreach.md).
The newly recovered direct LLM solve outside that old list is `heapsort`.

### Lost solves

These were solved by `svcomp26` and became UNKNOWN under `svcomp26-vguide`:

| Task | Expected / baseline result | Baseline deciding component | svcomp26-vguide component | LLM rounds |
|------|----------------------------|-----------------------------|---------------------------|-----------:|
| `divbin_unwindbound20` | FALSE | `svcomp26--multipleLoops-symbolicExecution.properties` | `parallel_multiple_loops` | 1 |
| `fermat2-ll_valuebound20` | TRUE | `svcomp26--singleLoop-symbolicExecution.properties` | `parallel_single_loop` | 1 |
| `freire1_valuebound50` | TRUE | `svcomp26--complexLoops-kInduction.properties` | `value_fallbacks` | 0 |
| `geo2-ll_valuebound10` | TRUE | `svcomp26--singleLoop-symbolicExecution.properties` | `parallel_single_loop` | 1 |
| `geo3-ll_valuebound10` | TRUE | `svcomp26--singleLoop-symbolicExecution.properties` | `parallel_single_loop` | 1 |
| `lcm2_valuebound20` | TRUE | `svcomp26--singleLoop-symbolicExecution.properties` | `parallel_single_loop` | 1 |
| `nested-3` | TRUE | `svcomp26--multipleLoops-predicateAnalysis.properties` | `parallel_multiple_loops` | 1 |
| `nested_5` | TRUE | `svcomp26--multipleLoops-symbolicExecution.properties` | `parallel_multiple_loops` | 1 |
| `prodbin-ll_valuebound100` | TRUE | `svcomp26--singleLoop-symbolicExecution.properties` | `parallel_single_loop` | 1 |
| `sum_by_3` | TRUE | `svcomp26--multipleLoops-predicateAnalysis.properties` | `parallel_multiple_loops` | 1 |

Interpretation: the integration is **not** a monotonic improvement. Most lost solves are portfolio races where the
parallel group timed out without a child finishing; two were baseline predicate-analysis wins (`nested-3`, `sum_by_3`)
that the VGuide predicate variant failed to preserve. This is the main v1.6 engineering target.

## Attribution and LLM behavior

`attribute_svcomp_verdicts.py` over the 764 `svcomp26-vguide` logs produced:

| Selection branch | Tasks | TRUE | FALSE | UNKNOWN | Solved |
|------------------|------:|-----:|------:|--------:|-------:|
| single_loop | 439 | 200 | 80 | 159 | 280 |
| multiple_loops | 229 | 103 | 34 | 92 | 137 |
| complex_loop | 95 | 37 | 38 | 20 | 75 |
| loop_free | 1 | 1 | 0 | 0 | 1 |

VGuide participation:

| Metric | Value |
|--------|------:|
| Tasks where VGuide fired | 668 |
| Tasks with `llm_rounds > 0` in log attribution | 254 |
| VGuide predicate component decided verdict | 39 |
| VGuide predicate decided TRUE/FALSE | 27 TRUE / 12 FALSE |
| New solves decided by VGuide predicate with LLM round | **16** |

LLM dump aggregate from `output/vguide/analysis_dumps/loops_reachsafety_unreach_svcomp26vguide_20260614/tasks`:

| Metric | Value |
|--------|------:|
| LLM JSON records | 529 |
| Task dump dirs with `llm_rounds.jsonl` | 273 |
| `safe_primary` calls | 274 |
| `bug_primary` calls | 255 |
| Parse OK | 529 / 529 |
| Median latency | 1963 ms |
| Avg latency | 1983.5 ms |
| p95 latency | 2548 ms |
| Max latency | 4328 ms |
| Total tokens | 782,672 |
| Prompt tokens | 730,688 |
| Completion tokens | 51,984 |

Note on interval analysis: dual SAFE/BUG prompts are issued back-to-back inside one scheduled LLM round, so adjacent
`call_start_epoch_ms` deltas in the raw JSON are mostly ~1.4–2.7s and should not be interpreted as violating
`vguide.llmMinIntervalSec=15`. The scheduler interval applies between LLM rounds, not between the paired SAFE and BUG
HTTP calls in a dual-prompt round.

## Soundness and known issue

No TRUE/FALSE mismatch against expected metadata was observed in any of the four compared runs.

One `svcomp26-vguide` task, `watermelon`, produced a Java exception and was post-processed to UNKNOWN:

```text
Identifier 'false' can not be used, because it is a keyword of SMT-LIB2.
```

`watermelon` was also UNKNOWN under the svcomp26 baseline, so this does not affect the net solved delta or soundness
claim. It is nevertheless a real robustness bug in the predicate parsing/identifier path and should be fixed before
claiming production readiness.

Other operational checks:

| Check | Result |
|-------|--------|
| Summary rows | 764 / 764 |
| Log files | 764 / 764 |
| Wrong verdicts | 0 |
| `process_round_cap` skips | 0 |
| Runner post-processed UNKNOWN logs | 1 (`watermelon`) |

## Claim guidance

Strong claim we can make:

> On a 764-task official SV-COMP Loops ReachSafety subset, scoped VGuide integration into the svcomp26 portfolio
> improves the strong svcomp26 baseline from 486 to 493 solved with zero wrong verdicts and better PAR-2; 16 of the
> 17 new solves are direct LLM-guided predicate-component wins.

Do **not** overclaim:

- Not a strict superset: 10 baseline solves became UNKNOWN.
- Not a full SV-COMP result: only Loops ReachSafety, not all categories/properties.
- Not a competition-submission configuration: online LLM calls are not allowed in normal SV-COMP offline runs.
- Not evidence that FALSE-oriented guidance is solved: net FALSE count stayed 152; VGuide’s direct new wins remain
  mostly TRUE-oriented.

## Artifacts

```text
output/vguide/experiments/loops_reachsafety_unreach_svcomp26vguide_20260614/loops_reachsafety_unreach_summary.csv
output/vguide/experiments/loops_reachsafety_unreach_svcomp26vguide_20260614/attribution.csv
output/vguide/analysis_dumps/loops_reachsafety_unreach_svcomp26vguide_20260614/tasks/
output/vguide/experiments/runner_logs/loops_reachsafety_unreach_svcomp26vguide_20260614.nohup.log
```
