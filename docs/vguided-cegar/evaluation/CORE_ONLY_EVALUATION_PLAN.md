# Core-only hard-case evaluation plan

Status: planning only. Do not run the held-out set until every freeze gate below passes. This plan implements Issue [#2](https://github.com/swear01/cpachecker/issues/2).

## Fixed scope

- Dataset: Hard-case Dataset v2's frozen manifest of **224 distinct tasks**.
- Arms: **Stock-Core** and **Augmented-Core** only.
- Exploratory workload: each task runs once in each arm: **224 × 2 = 448 executions total**.
- Claim: Augmented-Core versus Stock-Core measures only the target PredicateCPA/CEGAR mechanism. It makes no full-portfolio claim.
- Dataset selection remains based on stock full-portfolio evidence; augmented results never alter the manifest.

The Dataset v2 release's 448 validation rows are historical dataset-construction evidence (224 tasks × two stock-full repetitions). They are not repetitions required for this core-only evaluation.

## Execution order and gates

### 1. Contract and runner foundation — **implemented (2026-08-10)**

- Target core configs: **Stock-Core** = `config/predicateAnalysis.properties`;
  **Augmented-Core** = `config/predicateAnalysis-vguide.properties`
  (= stock + `config/vguide.properties` + `useVocabularyGuide=true`).
- `scripts/vguided-cegar/run_core_only.sh --arm stock|augmented --manifest <json> --out <dir>`:
  hash-verifies all 224 sources against the frozen manifest (fail-closed on any
  mismatch), runs each task once (parallel, per-task timelimit), and emits one
  JSON record per task with task/property/source hashes, commit, config hash,
  solver version, wall/CPU/memory, verdict, refinements, LLM calls,
  validated/injected predicates (from the VGuide dump), and an explicit
  failure category. Interrupted/invalid runs are recorded, never silently
  retried. **Resume (since 2026-08-14):** restarting the harness on the same
  `--out` dir resumes — tasks with a valid (JSON-parseable) per-task record are
  skipped, corrupt records and partial augmented dumps are discarded and
  rerun, and the run refuses to start if `run_meta.json` provenance (arm,
  commit, config/manifest hashes, timelimit, model, thinking) differs from
  the invocation.
- `scripts/vguided-cegar/core_only_config_diff.py`: resolves both configs
  (including `#include` trees) and rejects any difference outside the
  augmentation allowlist (`vguide.*`, `cpa.predicate.refinement.useVocabularyGuide`).
  Verified: the two arms differ only by the 15 `vguide.*` options.
- Frozen 224-task list: `benchmark_sets/hard_case_core_224.list` (deterministic
  manifest order, with task/source SHA-256s).
- **Blocked prerequisite for any run**: the manifest pins sv-benchmarks at
  `9cf9198156e4c8a6c517e474770158e1bb0b566d`; the local checkout is not at that
  revision (153/224 hashes match). The pinned revision must be obtained
  (fleet checkout or fresh clone) before the smoke/holdout runs.
- Frozen resource limits (to confirm before section 4): parallelism 8,
  timelimit 300s, heap 6000M, model deepseek-v4-pro (from development
  evidence; prompt/context version = schema-9 dump + `loop-head-candidate-v1`).
  Schema 9 and earlier serialized `precision_local_before` and
  `precision_global_before` from an in-place-mutated reached set; those fields
  are invalid for native-overlap attribution. Corrected runs require schema 10
  or later ([#140](https://github.com/swear01/cpachecker/issues/140)).

### 2. Build and validate the augmentation on development data

Implement and test the research issues in dependency order:

1. [#3](https://github.com/swear01/cpachecker/issues/3): structured CE artifact.
2. [#4](https://github.com/swear01/cpachecker/issues/4), [#5](https://github.com/swear01/cpachecker/issues/5), and [#6](https://github.com/swear01/cpachecker/issues/6): per-loop-head candidates, bounded CE history, and native-predicate context.
3. [#7](https://github.com/swear01/cpachecker/issues/7) and [#8](https://github.com/swear01/cpachecker/issues/8): refinement outcomes and LLM-predicate lifecycle.
4. [#10](https://github.com/swear01/cpachecker/issues/10) phases 1–2: freeze the selected model only after the development capacity gate.
5. [#9](https://github.com/swear01/cpachecker/issues/9): role-based multi-agent portfolio; #10 phase 3 is allowed only after this architecture is frozen.

Each issue uses only its frozen development split for tests, ablations, and tuning. Any wrong verdict, untraceable artifact, provider failure misclassified as a result, or cross-task state leakage blocks progress.

### 3. Freeze review

Before the held-out run, create a freeze record containing the exact source commit, JAR, configs and nested configs, manifest, solver/model versions, prompts, hashes, resource limits, parallelism, output schema version, and the approved development-set decision. Run the config-diff validator and a manifest/hash validator. Review the runner's stop conditions and verify that no development artifact can write into held-out output.

### 3.5 CPU isolation & load management — **requirement (2026-08-11)**

All formal runs MUST follow the previous agents' protocol (Baseline-Protocol,
`docs/EXPERIMENT_PROTOCOL.md` on `research/vguide-upstream-reimpl`):

- taskset pin every CPA invocation to logical CPUs `0,2,4,6,8,10,12,14`
  (8 physical P-cores, no SMT sibling, no E-core);
- refuse to start when any P-core is ≥50% busy or has concurrent local
  processes (foreign_p_core_contention);
- record `cpu_isolation` + `load_check` in `run_meta.json`;
- machine selection via the fleet availability monitor
  (valkyrie/athena/cthulhu, `idle_ready`); 13900K/14900K P-cores are
  comparable and mixable.
- Contaminated runs are invalid for timing claims; verdict-only claims
  need an explicit caveat.

> Note: the 2026-08-11 stock+augmented 224 runs were executed WITHOUT this
> isolation (E-core placement, concurrent builds/probes); their data is a
> rough usefulness check only and must not be used for timing claims.

### 4. Development smoke — **in progress (2026-08-11)**

Run both arms on the frozen development smoke set once. Require complete records, matching task order, valid provenance, valid paired-comparison output, and zero wrong verdict before proceeding. This smoke may reveal infrastructure defects, but it may not change frozen method choices without returning to the freeze-review step.

Execution (background driver):

```bash
export SV_BENCHMARKS=/var/tmp/swear01-cpachecker-paper/sv-benchmarks/c   # pinned 9cf9198
export DEEPSEEK_API_KEY=...
nohup ./scripts/vguided-cegar/run_core_only_background.sh > /tmp/core-only-driver.out 2>&1 &
tail -f output/vguide/core_only/driver.log
```

Smoke set: 12 tasks (12 families, 2 expected-false) from the frozen manifest (`/tmp/smoke-manifest.json`, subset of `cap16-run/candidate-manifest.json`).

Harvest / gates (for the agent continuing this run):

- Per-arm products under `output/vguide/core_only/<arm>_core/` (or `smoke_<arm>/`): `records.jsonl` (one record per task: task/property/source hashes, commit, config/solver hashes, wall/CPU/memory, verdict, refinements, LLM calls, validated/injected predicates, failure category), `run_meta.json` (arm/commit/config+manifest hashes/limits/model), `logs/<task>.log`, and `dumps/` for the augmented arm (historical schema-9 VGuide dump; use schema 10 or later for corrected before/after precision attribution).
- Smoke gate: `python3 scripts/vguided-cegar/check_core_only_smoke.py output/vguide/core_only/smoke_stock/records.jsonl output/vguide/core_only/smoke_augmented/records.jsonl --expect-count 12` — complete records + 0 wrong verdicts; only then the driver proceeds to the held-out stage.
- Held-out gate: same checker with `--expect-count 224` on `stock_core` / `augmented_core`.
- Paired analysis (§6): join both arms' `records.jsonl` on `task`; per-task new/lost/disagreement/wrong; LLM metrics from the augmented dumps (`dumps/<task>/tasks/<stem>/llm_rounds.jsonl`, `refinements.jsonl` — validated/injected/rejections/ce_history/native_predicate_context).
- Fixed parameters: parallelism 8, timelimit 300 s, heap 6000M, model deepseek-v4-pro; ablation options all OFF (`vguide.ceHistoryMode=OFF`, `nativePredicateContext=false`, `refinementOutcomeContext=false`, `replaceLlmPredicates=false`).
- 0 wrong is a hard gate; interrupted/invalid runs are recorded as infrastructure failures, never silently retried. Whole-run recovery = restart the harness with the same `--out` dir (resume skips completed tasks; provenance is validated against `run_meta.json`).

### 5. Held-out core-only evaluation

Run Stock-Core once for all 224 tasks. Verify completion, manifest/config hashes, and verdict soundness before running Augmented-Core once for the same 224 tasks. Do not retry individual tasks as a hidden performance fallback. Interrupted or invalid runs are recorded as infrastructure failures and restarted under the whole-run recovery procedure: re-invoke the harness with the same `--out` dir and unchanged provenance (arm/commit/config/manifest/timelimit/model/thinking); the resume path skips finished tasks and reruns only tasks without a valid record.

Stop immediately on a wrong verdict, config/manifest mismatch, missing provenance, or provider failure that would otherwise be mistaken for an analysis result.

### 6. Analysis and close-out

Produce per-task paired new/lost/disagreement/wrong attribution and aggregate verdict/resource/refinement/LLM metrics. Publish raw records, hashes, commands, and negative results. The report must state the one-run limitation and must not make stability or full-portfolio claims. Close #2 through a PR linked to the final report.

## Deferred publication confirmation

After the method is frozen for submission, repeat both arms on the same frozen 224-task manifest using a pre-registered repetition count and aggregation rule. Only that later confirmation may report run-to-run stability.
