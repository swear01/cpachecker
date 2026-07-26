<!--
This file is part of CPAchecker,
a tool for configurable software verification:
https://cpachecker.sosy-lab.org

SPDX-FileCopyrightText: 2026 SSU-WEI HUANG <https://github.com/swear01>

SPDX-License-Identifier: Apache-2.0
-->

# VGuide execution utilities

The active research design, decisions and results live in the [GitHub Wiki](https://github.com/swear01/cpachecker/wiki). This directory contains only executable reproduction utilities and pinned machine-readable inputs.

## Frozen stock baseline v1

```bash
env -u VGUIDE_LLM -u DEEPSEEK_API_KEY -u OPENAI_API_KEY \
  JAVA_HOME=/path/to/jdk-21 \
  scripts/vguide/run-stock-baseline.sh \
  /path/to/cpachecker-stock /path/to/sv-benchmarks \
  /path/to/benchmark-definitions /path/to/benchexec /path/to/output
```

The runner refuses revision drift, a dirty stock checkout, LLM-related environment variables, an unexpected P-core topology, a non-empty output directory, a runtime other than the pinned OpenJDK 21.0.11, a mismatched JDK tree hash, or VGuide in the stock configuration closure. The JDK pin is the upstream CI-image runtime with its absolute image-root symlinks materialized as byte-identical files for execution outside that image. Before measurement, the runner performs a clean upstream JAR build, the full unit suite, configuration checks, and integration tests; every gate log is retained. It then executes three repetitions of the fixed balanced ten-task calibration declared in `baseline.py`, records timing noise, runs the full 764-task corpus, and validates the witnesses. The calibration tasks are pinned fast stock-solvable infrastructure probes and are not used to select or score the scientific corpus. Machine state is captured before execution and after each measurement phase. Both the gate processes, BenchExec harness, and child runs are restricted to logical CPUs `0,2,4,6,8,10,12,14`, representing the eight physical P-cores without SMT siblings.

The formal command terminates on cgroup-preflight failure, any non-correct calibration result, an incomplete or mismatched full result, duplicate tasks, or a wrong verdict. It retrieves and hashes every YAML witness for a correct result and renders validation runs from the pinned official CPAchecker witness-validator definitions. Those validator runs reproduce the competition protocol; they are supplemental evidence, not the acceptance gate for the research hard-case dataset. The runner writes correct hard-over-200-second and stock-unsolved manifests, per-set/resource distributions, witness-validation evidence, post-run machine state, and a checksummed artifact manifest. Wrong verdicts are quarantined from both research strata. The artifact manifest is also attempted on every post-preflight failure without masking the original exit status.

BenchExec preserves CPAchecker's relative output directory in retrieved result files, so each witness is resolved as `${taskdef_name}/output/witness.yml`; generated validator definitions use the same path.

Each BenchExec invocation starts in the stock checkout, exposes that checkout through an ephemeral overlay, keeps the rest of `/` read-only, and hides `/home`. This keeps the working directory visible even if the outer runner was launched from a hidden home directory and permits witness output without making the host checkout writable. BenchExec receives a fixed minimal environment so result XML files cannot capture unrelated credentials or session-specific variables from the invoking account.

`config/predicateAnalysis-vguide.properties` keeps augmentation disabled unless a run explicitly supplies `vguide.enable=true`. Remote runs also require `vguide.endpoint` and `vguide.model`; the stock-only eligibility probe uses the deterministic `vguide.provider=EMPTY`.

## Result manifests

```bash
scripts/vguide/baseline.py summarize \
  --result /path/to/result.xml.bz2 \
  --task-manifest /path/to/generated/selection.manifest.json \
  --output-dir /path/to/summary
```

## Frozen hard-case dataset v1

`dataset.py inventory` combines the prior 764-task screen, family-balanced stock-only seeds from the verified SV-COMP 2026 result table, and licensed CBMC, ESBMC, and SeaHorn tasks that have property-compatible binary ground truth, a lexical loop, exactly one C source, and an explicit reachability-error call. Generic CBMC/ESBMC failing results are excluded because the failure may belong to another checked property; SeaHorn assertion results and successful CBMC/ESBMC results are retained. Selection never reads an augmented-arm result. Sources without a distributable license or compatible task semantics remain inventory exclusions.

The frozen runner validates every task and source hash, executes the stock `svcomp27` full portfolio twice with two four-core slots on physical P-cores `0,2,4,6,8,10,12,14`, and classifies:

- `stable_hard_solved`: both runs correct and median CPU time greater than 200 seconds;
- `stable_unsolved`: both runs are neither correct nor wrong;
- `mixed`: the two runs disagree or lack the timing required by the rule;
- `wrong_quarantine`: either run is wrong;
- `infrastructure_failure`: a missing harness or manifest result, excluded from both research strata.

BenchExec emits both combined and per-source-group result XML files; only the combined XML is an input to repeated classification.

```bash
env -u VGUIDE_LLM -u DEEPSEEK_API_KEY -u OPENAI_API_KEY \
  JAVA_HOME=/path/to/pinned-jdk-21 \
  scripts/vguide/run-stock-dataset.sh \
  /path/to/cpachecker-stock /path/to/sv-benchmarks \
  /path/to/benchexec /path/to/candidate-manifest.json /path/to/output
```

Development, validation, and held-out assignments are deterministic hashes of the source and program family, so a family cannot cross splits.

Before publication, audit the frozen screen without consulting verifier outcomes:

```bash
scripts/vguide/dataset.py license-audit \
  --manifest /path/to/candidate-manifest.json \
  --sv-benchmarks /path/to/sv-benchmarks \
  --external-root /path/to/frozen-source-checkouts \
  --output-dir /path/to/audited-candidate-corpus
```

The audit accepts an official task only when each source has an inline license statement or a license file in the same directory, and hashes the frozen root license for each redistributed external source. It emits a license-audited manifest plus full and quarantined audit CSV files. License-unresolved tasks remain in the original screen evidence but are excluded from the paper dataset independently of all stock and augmented results.

`run-cegar-probe.sh` runs the resulting hard-portfolio manifest with the matched PredicateCPA configuration and a local deterministic provider that always returns zero candidates. This cannot augment precision. PredicateCPA is single-threaded, so the probe runs eight simultaneous one-core jobs on the eight physical P-cores. An empty telemetry file is created before analysis and atomically replaced after each refinement so BenchExec can retrieve zero-event or partial evidence from timeout runs. The probe intentionally does not pass CPAchecker's `--benchmark` shortcut because that shortcut disables all output files. A task is CEGAR-eligible only after native refinement produces a spurious counterexample whose path visits a loop head. No refinement event is the structurally-unreachable census; a refinement event without a loop-head visit and missing infrastructure output remain separate strata.

## Wiki integrity

```bash
scripts/vguide/wiki.py check /path/to/cpachecker.wiki
scripts/vguide/wiki.py backup \
  https://github.com/swear01/cpachecker.wiki.git cpachecker-wiki.bundle
```
