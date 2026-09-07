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
  skipped only when their captured command matches the current invocation.
  Corrupt records and partial evidence are preserved and require a fresh output
  root; the run refuses to start if `run_meta.json` provenance (arm,
  commit, config/manifest hashes, timelimit, model, thinking) differs from
  the invocation.
- Owner-authorized exploratory checkpoints can add `--exploratory --cpu-list 8,10
  --parallel 2`. They record the five-sample CPU window, host load, memory and memory
  pressure without requiring an idle host. Only allocated physical P-cores are used,
  concurrency cannot exceed their count, and resume rejects changed allocation or
  evidence tier. `timing_claims_allowed=false` excludes formal timing/PAR-2 claims.
  The default remains the strict performance policy.
- Task semantics map ILP32 to `analysis.machineModel=Linux32` and LP64 to
  `Linux64`. Exact executed arguments and process status are separate artifacts;
  verifier logs are never prefixed or given synthetic UNKNOWN summaries. The
  smoke and paired-harvest gates check the captured model and paired resources.
  `check_core_only_smoke.py` requires `--manifest <frozen-smoke-manifest.json>`;
  `analyze_core_only_pair.py` retains official-label wrongs, failures and new/lost
  correct results, with no dispute exemptions.
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
  timelimit 300s, heap 6000M, model muse-spark-1.2-contributor with minimal reasoning
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
- take five consecutive one-second `mpstat` samples; load-based refusal applies only when any
  selected P-core has median busy ≥50%; do not veto from cumulative process
  `%CPU` or a process's last `PSR`;
- treat process snapshots as diagnostics, except for an explicit conflicting
  CPAchecker/solver/BenchExec owner on the selected CPU set;
- record `cpu_isolation`, all load-window samples, and the pool claim in
  `run_meta.json`;
- machine selection via the fleet availability monitor: atomically claim the
  first `idle_ready` valkyrie/athena/cthulhu host, then immediately recheck it;
  13900K/14900K P-cores are comparable and mixable.
- Contaminated runs are invalid for timing claims; verdict-only claims
  need an explicit caveat.

> Note: the 2026-08-11 stock+augmented 224 runs were executed WITHOUT this
> isolation (E-core placement, concurrent builds/probes); their data is a
> rough usefulness check only and must not be used for timing claims.

### 4. Development smoke — **in progress (2026-08-11)**

Run both arms on the frozen development smoke set once. Require complete records, matching task order, valid provenance, valid paired-comparison output, and zero wrong verdict before proceeding. This smoke may reveal infrastructure defects, but it may not change frozen method choices without returning to the freeze-review step.

Execution must be launched from a claimed HAPI worktree with a session-attached job. The exact
task-specific command, machine claim, commit and artifact path belong in the tracking issue before
launch; detached repository-local `nohup` drivers are not valid experiment launchers.

```bash
export SV_BENCHMARKS=/var/tmp/swear01-cpachecker-paper/sv-benchmarks/c   # pinned 9cf9198
export MODEL_API_KEY=...
hapi job run "$HAPI_SESSION_ID" core-only-stock --label "core-only stock" -- \
  bash ./scripts/vguided-cegar/run_core_only.sh --arm stock --manifest "$MANIFEST" --out "$STOCK_OUT"
```

Smoke set: 12 tasks (12 families, 2 expected-false) from the frozen manifest (`/tmp/smoke-manifest.json`, subset of `cap16-run/candidate-manifest.json`).

Harvest / gates (for the agent continuing this run):

- Per-arm products under `output/vguide/core_only/<arm>_core/` (or `smoke_<arm>/`): `records.jsonl` (one record per task: task/property/source hashes, commit, config/solver hashes, wall/CPU/memory, verdict, refinements, LLM calls, validated/injected predicates, failure category), `run_meta.json` (arm/commit/config+manifest hashes/limits/model), `logs/<task>.log`, and `dumps/` for the augmented arm (historical schema-9 VGuide dump; schema 10 corrects before/after precision attribution, schema 11 records `abstraction_formulas_pre`, and schema 12 adds the deterministic CFA-native `precision_compiler` record).
- Smoke gate: `python3 scripts/vguided-cegar/check_core_only_smoke.py output/vguide/core_only/smoke_stock/records.jsonl output/vguide/core_only/smoke_augmented/records.jsonl --manifest "$SMOKE_MANIFEST" --expect-count 12` — use the frozen 12-task smoke manifest; complete records + 0 wrong verdicts precede the held-out stage.
- Held-out gate: same checker on `stock_core` / `augmented_core`, replacing the smoke manifest with `--manifest "$HELD_OUT_MANIFEST" --expect-count 224`.
- Paired analysis (§6): join both arms' `records.jsonl` on `task`; per-task new/lost/disagreement/wrong; LLM metrics from the augmented dumps (`dumps/<task>/tasks/<stem>/llm_rounds.jsonl`, `refinements.jsonl` — validated/injected/rejections/ce_history/native_predicate_context).
- Fixed parameters: parallelism 8, timelimit 300 s, heap 6000M, model `muse-spark-1.2-contributor`, reasoning effort `minimal`, max completion tokens 1024; ablation options all OFF (`vguide.ceHistoryMode=OFF`, `nativePredicateContext=false`, `refinementOutcomeContext=false`, `replaceLlmPredicates=false`).
- 0 wrong is a hard gate for this smoke; interrupted/invalid runs are recorded as infrastructure failures, never silently retried. Preserve an incomplete attempt and use a fresh `--out` root for an explicitly recorded recovery. Reusing an output root is allowed only when existing task evidence has completed records and invocation provenance matches; it skips those completed records, including failures.

### 5. Held-out core-only evaluation

Run Stock-Core once for all 224 tasks. Verify completion, manifest/config hashes, and verdict soundness before running Augmented-Core once for the same 224 tasks. Do not retry individual tasks as a hidden performance fallback. Preserve interrupted or invalid attempts as infrastructure failures. An explicitly recorded recovery uses a fresh output root; the same-root resume path only starts tasks with no previous evidence and skips completed records after checking unchanged provenance. It refuses logs, execution status or dumps without a completed record. Resume checks JSON/task/command identity only; acceptance separately requires the smoke checker to verify the referenced logs, execution sidecars and hashes. SIGINT/SIGTERM preserves an `interrupted` sidecar and partial log as infrastructure-failure evidence; missing or corrupt sidecars remain invalid.

Stop immediately on a wrong verdict, config/manifest mismatch, missing provenance, or provider failure that would otherwise be mistaken for an analysis result.

### 6. Analysis and close-out

Produce per-task paired new/lost/disagreement/wrong attribution and aggregate verdict/resource/refinement/LLM metrics. Publish raw records, hashes, commands, and negative results. The report must state the one-run limitation and must not make stability or full-portfolio claims. Close #2 through a PR linked to the final report.

## Deferred publication confirmation

After the method is frozen for submission, repeat both arms on the same frozen 224-task manifest using a pre-registered repetition count and aggregation rule. Only that later confirmation may report run-to-run stability.
