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

### 1. Contract and runner foundation

Before method work, define the exact target core config and a single runner that accepts an arm, frozen manifest, and output directory. The runner must emit one record per task containing task/property/source hashes, commit, binary/config/solver hashes, wall/CPU/memory use, verdict, refinement count, LLM calls, validated/injected predicates, and explicit failure category.

A config-diff validator must reject any difference between the two arms except the augmentation configuration and its required provenance fields. The chosen CPU set, parallelism, wall limit, CPU limit, memory limit, model ID, prompt/context version, candidate budget, and retry/failure policy must be frozen from development evidence before held-out execution.

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
