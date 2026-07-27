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

## Hard-case datasets

`dataset.py inventory` combines the prior 764-task screen, family-balanced stock-only seeds from the verified SV-COMP 2026 result table, and licensed CBMC, ESBMC, and SeaHorn tasks that have property-compatible binary ground truth, a lexical loop, exactly one C source, and an explicit reachability-error call. Generic CBMC/ESBMC failing results are excluded because the failure may belong to another checked property; SeaHorn assertion results and successful CBMC/ESBMC results are retained. Selection never reads an augmented-arm result. Sources without a distributable license or compatible task semantics remain inventory exclusions.

Dataset v1 executed the stock `svcomp27` full portfolio twice with two four-core slots on physical P-cores `0,2,4,6,8,10,12,14`, and classified:

- `stable_hard_solved`: both runs correct and median CPU time greater than 200 seconds;
- `stable_unsolved`: both runs are neither correct nor wrong;
- `mixed`: the two runs disagree or lack the timing required by the rule;
- `wrong_quarantine`: either run is wrong;
- `infrastructure_failure`: a missing harness or manifest result, excluded from both research strata.

BenchExec emits both combined and per-source-group result XML files; only the combined XML is an input to repeated classification.

Dataset v2 tightens `stable_unsolved` to repetitions classified as timeout,
out-of-memory, or UNKNOWN. Verifier errors, exceptions, segmentation faults,
and other non-analysis failures are written to
`verifier-failure-quarantine.csv`; infrastructure, mixed, and wrong results
remain separate. The frozen v1 release retains its original classification.

The frozen v2 cap-8 universe has 729 tasks. Its license audit retains 700;
subtracting the 380-task audited v1 manifest yields 320 outcome-independent
discovery tasks. Derive them and their deterministic per-host manifests:

```bash
scripts/vguide/dataset.py difference \
  --manifest /path/to/cap8/candidate-manifest-license-audited.json \
  --exclude-manifest /path/to/v1/candidate-manifest-license-audited.json \
  --sv-benchmarks /path/to/sv-benchmarks \
  --output-dir /path/to/incremental-screen-manifests
```

The command validates both input manifests and every task/source hash,
requires every excluded record to be identical to its full-manifest record,
and copies corpus provenance. It balances
`(family, seed_class, expected_verdict)` strata deterministically across
Athena, Cthulhu, and Valkyrie. `validate-shards` independently recomputes the
assignment and rejects overlap, omission, changed records, or a different
assignment.

The r4 runner at commit
`9701fce2b28672ba6da91ea2b1b10df3f715d6ba` accepts only the fixed Cthulhu
reroute manifest for Athena
(`477374a2bbab9fd8559e1945e6781b5484e26afec7808266332423c1db9cddd6`)
or Valkyrie
(`6c5e9d46d83f9cb644cc37d9651511102cc27ce539bed7024e8b14f1698aae29`)
and rejects Cthulhu. Use the r3 runner at commit
`99bc3800cce4da16ec0cbf108af6197595a54ff3` for the original three shards.
Both protocols perform one Phase-A screen with fixed 120 s CPU, 130 s
hard-CPU, and 140 s wall limits. `screen-summary` requires exactly one
BenchExec `systeminfo` hostname, verifies it against the requested host and
manifest provenance, and carries `phase_a_host` into its CSV, summary, and
survivor manifest. It separates correct-fast, wrong,
analysis-survivor, verifier-failure, and infrastructure outcomes. Its hashed
survivor manifest is the input for two subsequent 900-second measurements on
the same host. Postprocessing accepts only the exact combined or official-only
`hard-case-candidates` result XML filename, compressed or uncompressed, and
still requires exactly one match. A
ten-second preflight and the complete screen record package thermal-throttle
and kernel swap-I/O counter deltas as provenance. Nonzero deltas are warnings,
not acceptance failures. Missing, non-integer, decreasing, or cross-host
counters remain fail-closed.
The summary fails on missing CPU/wall metrics; UNKNOWN is eligible only when
BenchExec explicitly reports it as the status or category.
After output initialization, a failed run still records machine state and an
artifact manifest while preserving the original exit status.

The r4 reroute is a fixed, outcome-independent repartition of the frozen r3
Cthulhu shard
`40bda9c755c88d9b617269aaa6e1c66ceea07fb818e0741f8a1f960536bd6d4b`.
It assigns all 107 task records to Athena and Valkyrie with the same
stratified algorithm as the original three-host partition:

```bash
scripts/vguide/dataset.py reroute-cthulhu \
  --manifest /path/to/r3/candidate-manifest-cthulhu.json \
  --sv-benchmarks /path/to/sv-benchmarks \
  --output-dir /path/to/r4-reroute

scripts/vguide/dataset.py validate-reroute \
  --manifest /path/to/r3/candidate-manifest-cthulhu.json \
  --reroute-manifest /path/to/r4-reroute/candidate-manifest-athena.json \
  --reroute-manifest /path/to/r4-reroute/candidate-manifest-valkyrie.json \
  --sv-benchmarks /path/to/sv-benchmarks
```

Two attempts to run Athena's original 107-task shard were interrupted by
reboots. The 53-task r4 Athena reroute was never launched. The r5 fallback
does not read either partial original-shard result. It concatenates the frozen
original and reroute Athena manifests in parent order, preserves every row and
both derivation lineages, and assigns the complete union to Valkyrie:

```bash
scripts/vguide/dataset.py athena-recovery \
  --athena-manifest /path/to/r3/candidate-manifest-athena.json \
  --athena-reroute-manifest /path/to/r4/candidate-manifest-athena.json \
  --sv-benchmarks /path/to/sv-benchmarks \
  --output-dir /path/to/r5-athena-recovery

scripts/vguide/dataset.py validate-athena-recovery \
  --athena-manifest /path/to/r3/candidate-manifest-athena.json \
  --athena-reroute-manifest /path/to/r4/candidate-manifest-athena.json \
  --manifest /path/to/r5-athena-recovery/candidate-manifest-valkyrie.json \
  --sv-benchmarks /path/to/sv-benchmarks
```

The current `run-stock-dataset.sh` is the r5 Valkyrie-only Phase-A runner. It
accepts only the frozen recovery manifest; it is not a general r3/r4 runner
and is not a Phase-B runner:

```bash
env -u VGUIDE_LLM -u DEEPSEEK_API_KEY -u OPENAI_API_KEY \
  JAVA_HOME=/path/to/pinned-jdk-21 \
  scripts/vguide/run-stock-dataset.sh \
  /path/to/cpachecker-stock /path/to/sv-benchmarks \
  /path/to/benchexec \
  /path/to/r5-athena-recovery/candidate-manifest-valkyrie.json \
  /path/to/r5-phase-a-output
```

After all three accepted Valkyrie Phase-A packages finish, `merge-survivors`
takes the frozen 320-task parent and exactly three each of
`--phase-a-manifest`, `--phase-a-result`, and `--survivor-manifest`: the
original Valkyrie shard, the r4 Valkyrie reroute, and the r5 Valkyrie recovery.
It authenticates the fixed manifests by hash, checks that they form an exact
unchanged partition of the parent, reparses every complete result, and
recomputes every survivor set. It writes one parent-ordered
`candidate-manifest-valkyrie-formal.json`. Duplicate or changed task records
fail closed. An authenticated zero-survivor merge remains valid evidence and
produces a zero-task manifest.

Every Phase-A manifest argument must be a self-contained preregistration or
release copy whose declared `corpus_files` resolve beside that manifest. The
three `provenance/candidate-manifest.json` files stored inside Phase-A run
records are evidence copies only: they do not carry the corpus tree beside
them and cannot be supplied as standalone merge inputs.

Result authentication pins all three raw result and survivor-manifest hashes,
their survivor counts, CPAchecker `4.2.2-2417-g1848f9eb59`, tool module
`benchexec.tools.cpachecker`, and generator `BenchExec 3.35-dev`. It rejects
an absent end time, any result-root `error`, and any run whose task,
source-file, expected-verdict, or unreachability-property topology differs
from its frozen manifest.

The merged formal manifest is byte-pinned at
`e8aed1d26a0920bfef4964d495d86b69bbad666efb8d72e87462f297ca243855`.
The merge copies only files declared in the parent manifest's `corpus_files`;
it never copies unrelated corpus sidecars. The package also contains a
path-independent `artifact-manifest.json` whose sorted file hashes define its
aggregate hash, so rebuilding at another output path produces identical
bytes.

`test_phase_b_production_closure` is environment-gated for upstream unit
runs. Release verification sets `VGUIDE_PHASE_B_PARENT_MANIFEST`,
`VGUIDE_PHASE_B_PHASE_MANIFESTS`, `VGUIDE_PHASE_B_RESULTS`,
`VGUIDE_PHASE_B_SURVIVORS`, and `VGUIDE_PHASE_B_SV_BENCHMARKS`; each
three-item list uses the platform path separator. Together with the existing
r5 production variables, the full test suite must report zero skipped tests.

`render-formal` is definition generation, not an executable Phase-B runner.
It accepts only the Valkyrie merge authenticated from those three evidence
sets, reports an empty merge as an explicit skip, and fixes the prospective
stock definition at 900 s CPU, 910 s hard-CPU, and 920 s wall time. Formal
`summarize` reauthenticates all three Phase-A packages and requires two
distinct, complete Valkyrie results from that merged manifest. Both commands
reject a nonempty output directory.

Phase B is not executable yet. The formal input is pinned, but an executable
runner intentionally remains unimplemented pending review. The existing
Phase-A runner must not be used as a substitute.

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
