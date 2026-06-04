# B5 Stability Evaluation Protocol

## 1. Motivation

Single-run B2 vs B5 comparisons are confounded by two sources of non-determinism:

1. **LLM output non-determinism**: Same prompt, different predicate quality (mitigated by record/replay caching).
2. **CPAchecker verification non-determinism**: Same predicates, different refinement counts due to BDD ordering, solver paths, memory state.

The replay evaluation (Section 27) showed that even with identical cached LLM output, CPAchecker produced different refinement counts across runs (sum04-2: record=7, replay=2).

A single point-comparison is unreliable. We need repeated runs and distributional comparison.

## 2. Protocol

### Targets

- sum04-2
- const_1-2
- functions_1-2
- nested_1-2

### Parameters

- K = 5 repeated runs per mode per benchmark
- B2 mode: standard source-only LLM precision (VGUIDE_PRECISION_TOP_K=5)
- B5 mode: B2 dump → B5 repair → validated injection → rerun
- Use cached LLM output where available (Java B2 only, since Python B5 prompt varies)
- 30s timelimit, 60s timeout wrapper
- HEAP=2000M

### Per-Run Data

```csv
benchmark, mode, run_id, result, refs, time, llm_cache_status, repair_predicates, notes
```

### Aggregate Statistics

```csv
benchmark, b2_median, b2_min, b2_max, b5_median, b5_min, b5_max, delta_median, improvement_frequency, regression_frequency, diagnosis
```

**improvement_frequency** = proportion of paired runs where B5_refs < B2_refs
**regression_frequency** = proportion of paired runs where B5_refs > B2_refs

### Diagnosis Labels

- `stable_improvement`: improvement_frequency > 0.5 AND regression_frequency < 0.2
- `unstable`: improvement_frequency < 0.5 OR regression_frequency > 0.3
- `stable_no_effect`: |delta_median| < 2 AND improvement_frequency < 0.3
- `stable_regression`: regression_frequency > 0.5

### Interpretation

A B5 gain is considered "stable" only if it appears in the majority of runs and regressions are rare. A split result (some runs improve, some regress) indicates that the gain depends on CPAchecker internal variability, not B5 predicate quality.

## 3. LLM Cache Strategy

### Java B2

- Use replay mode if cache exists for the benchmark.
- If no cache, record first run, replay subsequent runs.
- Cache directory: `VGUIDE_LLM_CACHE_DIR=<stability_eval>/cache`

### Python B5

- B5 prompt varies per run (CEGAR dump context changes).
- Record mode on each run to ensure consistent downstream processing.
- Mark B5 LLM calls as "context-dependent" in notes.
- Cache can be reused if the same prompt hash recurs (unlikely but possible).

## 4. Expected Duration

- 4 benchmarks × 2 modes × 5 runs = 40 CPAchecker runs
- ~4 B5 repair calls
- ~40s per run average × 40 = ~1600s (~27 min) minimum
- With overhead: ~40-60 minutes

## 5. Output Structure

```
results/vguided-cegar/stability_eval/
  cache/                          # LLM cache
  sum04-2/
    b2/
      run_1.log ... run_5.log     # B2 repeated runs
    b5/
      run_1/                      # B5 repair artifacts per run
      run_1_rerun.log ... run_5_rerun.log
    ...
  const_1-2/ ...
  summary.csv
  summary.md
```

## 6. Stop Conditions

Stop if:
- B2 or B5 fails on 3+ runs for the same benchmark
- LLM API errors occur on 3+ consecutive calls
- Results are wildly unstable (std dev > 50% of median)
- Time exceeds 90 minutes
