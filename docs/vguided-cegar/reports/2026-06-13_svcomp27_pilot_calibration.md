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
