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

The formal command terminates on cgroup-preflight failure, any non-correct calibration result, an incomplete or mismatched full result, duplicate tasks, or a wrong verdict. It retrieves and hashes every YAML witness for a correct result, renders validation runs from the pinned official CPAchecker witness-validator definitions, and requires all correctness and violation validation runs to be correct. On success it writes correct hard-over-200-second and stock-unsolved manifests, per-set/resource distributions, witness-validation evidence, post-run machine state, and a checksummed artifact manifest. Wrong verdicts are quarantined from both research strata. The artifact manifest is also attempted on every post-preflight failure without masking the original exit status.

BenchExec preserves CPAchecker's relative output directory in retrieved result files, so each witness is resolved as `${taskdef_name}/output/witness.yml`; generated validator definitions use the same path.

Each BenchExec invocation starts in the stock checkout, exposes that checkout through an ephemeral overlay, keeps the rest of `/` read-only, and hides `/home`. This keeps the working directory visible even if the outer runner was launched from a hidden home directory and permits witness output without making the host checkout writable. BenchExec receives a fixed minimal environment so result XML files cannot capture unrelated credentials or session-specific variables from the invoking account.

`config/predicateAnalysis-vguide.properties` keeps augmentation disabled unless a run explicitly supplies `vguide.enable=true`, `vguide.endpoint`, and `vguide.model`.

## Result manifests

```bash
scripts/vguide/baseline.py summarize \
  --result /path/to/result.xml.bz2 \
  --task-manifest /path/to/generated/selection.manifest.json \
  --output-dir /path/to/summary
```

## Wiki integrity

```bash
scripts/vguide/wiki.py check /path/to/cpachecker.wiki
scripts/vguide/wiki.py backup \
  https://github.com/swear01/cpachecker.wiki.git cpachecker-wiki.bundle
```
