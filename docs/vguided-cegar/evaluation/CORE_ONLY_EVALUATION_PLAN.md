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
  retried.
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

### 4. Development smoke

Run both arms on the frozen development smoke set once. Require complete records, matching task order, valid provenance, valid paired-comparison output, and zero wrong verdict before proceeding. This smoke may reveal infrastructure defects, but it may not change frozen method choices without returning to the freeze-review step.

### 5. Held-out core-only evaluation

Run Stock-Core once for all 224 tasks. Verify completion, manifest/config hashes, and verdict soundness before running Augmented-Core once for the same 224 tasks. Do not retry individual tasks as a hidden performance fallback. Interrupted or invalid runs are recorded as infrastructure failures and restarted only under the documented whole-run recovery procedure.

Stop immediately on a wrong verdict, config/manifest mismatch, missing provenance, or provider failure that would otherwise be mistaken for an analysis result.

### 6. Analysis and close-out

Produce per-task paired new/lost/disagreement/wrong attribution and aggregate verdict/resource/refinement/LLM metrics. Publish raw records, hashes, commands, and negative results. The report must state the one-run limitation and must not make stability or full-portfolio claims. Close #2 through a PR linked to the final report.

## Deferred publication confirmation

After the method is frozen for submission, repeat both arms on the same frozen 224-task manifest using a pre-registered repetition count and aggregation rule. Only that later confirmation may report run-to-run stability.
