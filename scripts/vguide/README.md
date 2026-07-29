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

Result validation accepts only the exact absolute corpus path, the exact
corpus-relative path used by portable evidence, BenchExec's canonical
working-directory-relative corpus path, the exact path relative to the actual
result XML's parent, and, when applicable, the exact benchmark-definition-
relative path. Every relative form is derived from the resolved frozen task;
traversal-prefixed, wrong-depth, wrong-corpus, symlink and other decoy paths
remain rejected.

Dataset v2 names the strict stratum `stable_analysis_unsolved` and limits it
to repetitions classified as timeout, out-of-memory, or UNKNOWN. Verifier
errors, exceptions, segmentation faults, and other non-analysis failures are
written to
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

For the approved cap-16-minus-cap-8 expansion, use the frozen Athena-only
assignment. Cthulhu had no safe P-core capacity at preregistration time; this
assignment is independent of verifier outcomes:

```bash
scripts/vguide/dataset.py difference \
  --manifest /path/to/cap16/candidate-manifest-license-audited.json \
  --exclude-manifest /path/to/cap8/candidate-manifest-license-audited.json \
  --sv-benchmarks /path/to/sv-benchmarks \
  --output-dir /path/to/cap16-minus-cap8 \
  --host athena

scripts/vguide/dataset.py validate-shards \
  --manifest /path/to/cap16-minus-cap8/candidate-manifest.json \
  --shard-manifest /path/to/cap16-minus-cap8/candidate-manifest-athena.json \
  --sv-benchmarks /path/to/sv-benchmarks \
  --host athena
```

The approved license-clean cohort and Athena manifest both have 254 tasks.
Their SHA-256 hashes are
`490f2337d68fba626f34eed05abb64c772c752289bab31689b354240d2146876`
and
`16e5f9ff04ed08ef9c29d8674021c11de3eed87b9da6a8c1e2ef68c6847ec0bb`.
Omitting `--host` retains the frozen three-host cap-8 derivation.

The r1 preregistration was rejected by its packaging/runtime preflight audit
before any task started: its archive omitted
`run-stock-formal-dataset.sh`, which the cap-16 runner sources, and it pinned
Valkyrie's Python 3.10 runtime instead of Athena's Python 3.12 runtime. The r2
preregistration supersedes r1. Its script package must contain exactly
`baseline.py`, `dataset.py`, `run-stock-formal-dataset.sh`, and
`run-stock-cap16-dataset.sh`. The r2 runner also pins Athena's independently
reproduced JAR-content digest
`49f95adc5255b89b1bb3edea81ab5f2f660364d36ffa69c3b12508d1e1943be3`.

`run-stock-cap16-dataset.sh` accepts only the frozen Athena manifest. It uses
two four-core slots on physical P-cores `0,2,4,6,8,10,12,14`, records the
r8 sustained-contention monitor, and derives an authenticated screen plan.
Completed untainted primary cases remain accepted; only incomplete or
contention-overlapping cases enter the next replacement definition. Each
replacement records its own taint manifest; if it is interrupted or
contended, only that attempt's still-tainted subset continues to the next
round. The final hashed screen plan authenticates every accepted row and
proves that completed rows were not rerun. Reinvoking the same command with
the same output directory after a reboot authenticates the saved
manifest, declared corpus property, scripts, and JAR; finalizes any preserved
incomplete XML; and resumes from its tainted subset without overwriting a
completed attempt. The stock,
SV-Benchmarks, and BenchExec checkouts are authenticated with the same clean
index, skip-worktree, and runtime-closure checks as the formal runner. Rebuilds
are compared by the deterministic JAR-content digest rather than the
timestamp-sensitive JAR byte hash. A summary becomes complete only after its
post-screen machine check, final runtime verification, and atomic artifact
manifest have all succeeded. Reentry recomputes the summary and compares the
exact `complete\n` sentinel bytes before accepting an already-complete output.

```bash
env -u VGUIDE_LLM -u DEEPSEEK_API_KEY -u OPENAI_API_KEY \
  JAVA_HOME=/path/to/pinned-jdk-21 ANT_HOME=/path/to/pinned-ant \
  scripts/vguide/run-stock-cap16-dataset.sh \
  /path/to/cpachecker-stock /path/to/sv-benchmarks /path/to/benchexec \
  /path/to/cap16-minus-cap8/candidate-manifest-athena.json \
  /path/to/phase-a-output
```

After that Phase-A output has its atomic `summary/.complete`, first materialize
its portable formal-input package:

```bash
python3 scripts/vguide/dataset.py package-cap16-phase-a \
  --phase-a-output /path/to/completed-cap16-phase-a-output \
  --sv-benchmarks /path/to/sv-benchmarks \
  --output-dir /path/to/cap16-phase-a-package
```

Packaging reauthenticates the complete source, rewrites benchmark, task-set and
result paths to corpus-relative forms, rebuilds the screen plan, row
provenance, survivor manifest and summary, and writes an artifact manifest
whose root is `.`. The package can therefore be moved without retaining the
source Phase-A output. Its exact aggregate hash is the formal identity gate.
The accepted Athena attempt-3 package aggregate is
`b0ce4f33ad505df816d559a4260d8cc75f96a9914b9396e214fe9c2e3ecf5dee`;
production authentication requires this exact value.

The cap-16 formal runner authenticates that frozen package's 254-task Athena
manifest, fixed screen definition, complete iterative screen plan and every
primary/replacement result, row-provenance bytes, recomputed survivor manifest,
summary counts and portable artifact aggregate. It selects no task from an
augmented result and does not accept a separately supplied survivor file. The
authenticated Phase-A survivor manifest is the only formal input.

The formal execution remains on Athena and reuses the existing two-repetition
recovery implementation: 900 s CPU, 910 s hard-CPU and 920 s wall time,
physical P-cores `0,2,4,6,8,10,12,14`, two four-core slots, the same sustained
foreign-load monitor, and hashed per-case taint/replacement plans. A nonzero
BenchExec interruption that leaves an incomplete XML is preserved. Reinvoking
the same output authenticates its saved inputs, retains every completed
untainted row, and continues only the current tainted subset. Each replacement
round gets a newly rendered definition for the remaining subset; a clean
primary is never rerun. An attempt is reusable only after an atomic version-4
completion record binds its result and definition, accepted BenchExec exit,
nonempty log, load monitor PID and stopped/sample record, and before/after
machine check.
An attempt without that record, with or without XML, is checked against its
recorded process identity (UID, PID, `/proc` start time and exact argv). The
BenchExec launcher additionally uses a deterministic unique transient systemd
scope derived from the canonical output root, mode and attempt label. A hashed
process descriptor binds the exact launcher unit and full pinned
systemd-run/taskset/environment/Python/BenchExec argv, plus the exact load
monitor script, output and excluded root argv. Resume authenticates an
unfinished identity against that descriptor before checking it and queries the
descriptor's expected unit rather than trusting the identity's recorded unit.
New version-2 descriptors require every Python process to start with
`-I -S -B -X pycache_prefix=/dev/null`. Only the two hash-pinned Athena
version-1 descriptors already present in the frozen recovery may be read; no
other version-1 path, hash, host or label is accepted.
It requires both the launcher identity to be gone and that expected unit to be
definitively inactive/not found. If either the exact owned process or unit is
still alive, resume fails closed and never signals it. For an authenticated
markerless incomplete attempt, resume atomically records an unobserved monitor
stop, a recovery machine snapshot/check, and reserved exit `125`, then validates
the BenchExec log against every complete XML row. Authenticated structured XML
is the only reusable-completion oracle. Only the first frozen version-2
selection may treat exactly one final console-log completion absent from
incomplete XML as interrupted; its recovered load monitor must also have valid
trailing NUL padding. The second frozen selection never enables that exception.
The third frozen selection also never enables that exception. Padding alone,
including on legacy recovery, never authorizes a mismatch. Every other XML/log
mismatch fails closed. Only missing/in-flight or
sustained-contention rows enter the taint/replacement plan; the completed
untainted rows and original result remain in place. Forged, overlapping,
inconsistent, or insufficient evidence fails closed instead of abandoning the
whole attempt.
Recovery evidence is revision-addressed at
`provenance/recoveries/<attempt-label>/<full-research-head>/` with exactly
`monitor-stopped`, `machine-after.json`, and `machine-check.json`. The runner
authenticates the active saved research closure before deriving this path.
The first write is immutable. A same-revision retry validates the exact
namespace topology and bytes, reuses the stored process/boot binding, and never
resamples recovery uptime or machine state. A different research revision gets
a distinct namespace. Initial evidence is assembled and fsynced in a fixed
sibling preparation directory, validated, then published with one atomic
directory rename. Resume discards only a recognized incomplete preparation;
a complete preparation is authenticated and published without resampling.
Missing or extra files in a published namespace, symlinks, tampering, and
path/head mismatches fail closed. The version-4 attempt marker hashes the actual
versioned paths and is the final recovery write; taint, replacement planning,
and further measurement cannot begin before that marker reauthenticates. Fixed
evidence paths referenced by prior version-3/version-4 markers remain valid
read-only.
The Athena repetition-1 repair is intentionally not a general selector. It
pins the full abandoned 50-complete-row attempt and displaced zero-complete-row
rerun inventories, writes a prepared transaction ledger, atomically moves the
displaced files into a fixed quarantine, and records the exact selected
attempt. Resume validates every possible transaction location and completes an
interrupted move only when each selected and displaced object exists in exactly
one expected location. Both ledgers and directory renames are fsynced. The
legacy version-1 PID identities are accepted only through that pinned selection
and must prove a reboot because their recorded `/proc` start ticks exceed the
recovery boot uptime. General new identities, which include the kernel boot UUID
and exact positive type/range checks, are not accepted by the markerless
recovery path. Its three frozen version-2 selections pin the exact replacement
label, role, repetition, captured boot UUID, result-directory digest and exact
regular-file/directory topology, and every definition, result, console,
load-monitor, process, machine, task-set, prior taint, and prior marker input.
The second selection is exactly
`repetition-1-replacement-attempt-2`: its authenticated incomplete result has
171 rows, of which 12 are reusable and 159 are interrupted. Recovery therefore
renders only those 159 tasks as `repetition-1-replacement-attempt-3`; it does
not rerun the 12 reusable rows and does not enable the first selection's final
log-only exception. Symlinks and special filesystem nodes fail closed. The
third selection is exactly
`repetition-1-replacement-attempt-3`: its authenticated incomplete result has
159 rows, of which only `c/array-tiling/nr4.yml` is structurally complete and
uncontended. That row is a `SEGMENTATION FAULT` in category `error`, so it is an
unsolved observation, not a correctness proof. Recovery retains it and renders
only the other 158 interrupted rows as
`repetition-1-replacement-attempt-4`, without enabling the first selection's
log-only exception. Every other version-2 attempt remains rejected; mixed
schemas or any drift fail closed. The
result-directory digest uses the production helper's Python `Path` part
ordering; reproduce it with that helper or `PurePosixPath`, not a plain sort of
relative strings. Only a proven reboot records machine counters as unavailable.
Recovered
snapshots still require identical host, platform, kernel, CPU model,
online/P-core sets, and Java identity; recorded `/proc/meminfo` `MemTotal` is
not an identity field because its reported byte count can change across boots.
Fully authenticated legacy version-3 completion markers remain immutable and are
validated read-only; new recovery markers use version 4.
Its runtime
closure is the cap-16 Athena Python 3.12/PyYAML 6.0.1 closure, not the older
Valkyrie Python 3.10 closure. It pins the Python executable, version and exact
isolated `sys.path`. Every helper starts with
`-I -S -B -X pycache_prefix=/dev/null` before any import, so host bytecode,
`site`, `.pth`, `sitecustomize`, user packages and Python environment variables
cannot alter executed code. The default path is only the standard-library zip,
standard library and `lib-dynload`; a saved-script parent or the exact BenchExec
checkout is inserted only by the command that needs it. PyYAML is loaded
directly from its pinned `yaml/__init__.py` with that one package search path,
not by adding either distribution-packages root; the same explicit bootstrap
preloads it before every BenchExec entry point. The runner pins the non-cache
standard-library closure at
`a0c9c33e4f5b6c4e8e921598ec1c7273341cf2e8f2c74d7a348d6a3584a2c325`;
the exact `yaml`, `_yaml` and `PyYAML-6.0.1.dist-info` package closure at
`9148a8dc1759caac2f87132749a8f29de2cf8ee71b6ddead932d027613045627`;
and an empty non-cache local distribution closure. Only real `__pycache__`
directories are excluded. A `.pyc` or `.pyo` outside one is authenticated by
the closure and is also rejected from every explicitly inserted saved-script
or BenchExec root, because Python can import such sourceless bytecode directly.
Source, extension, metadata, unknown non-cache, symlink and special-node drift
remains fail-closed, and PyYAML must still resolve to its pinned module path
and version. Before any rendering or measurement it copies
the portable package under `input/evidence/`, reauthenticates that saved copy,
and uses only saved-copy paths for all later render, validate and summarize
operations.

The pre-recovery `input/research/` closure remains immutable. A resume from the
frozen `2e2f8e7694d5d827756c322f788f59ac3c07a39d` runner authenticates those
saved files against that Git object. The first recovery closure at
`6b78ae338c687c32d905679243fb1d3a3f916733`, already stored under
`input/recovery-research/`, remains immutable. Each later clean recovery revision
is stored separately under
`input/recovery-research-<full-research-head>/`. Resume verifies the legacy
closure and every revision-addressed closure against its Git object during
activation, failure capture and final teardown; an existing path conflict,
path/head mismatch or modified prior closure fails closed.

Summary generation uses a separate staging directory. A crash cannot expose a
partial final summary; on resume a staged summary is recomputed and either
byte-compared with the promoted summary or atomically replaces incomplete
evidence. The final closure validator semantically authenticates both repetition
plans and requires an exact label-to-repetition, role, result hash, definition
hash and task-subset match for every attempt record, with no extra, missing,
reused or swapped attempts. It also checks the exact summary file set,
research/runtime and machine evidence, and the artifact manifest. `summary/.complete` is written
only after that validation and is the sole explicitly unmanifested
post-manifest sentinel; completed-output resume revalidates the same closure.
The sentinel must be a regular non-symlink containing exactly `complete\n` and
is created with fsync plus atomic rename. A partial, symlink or nonregular
sentinel is never treated as a legitimate crash artifact: resume fails closed
and preserves it in place without automatic repair or removal.
Before an incomplete invocation resumes, its mutable build, preflight,
failure, summary and final-verification evidence is moved into a numbered
`provenance/invocations/` directory instead of being overwritten.

```bash
env -u VGUIDE_LLM -u DEEPSEEK_API_KEY -u OPENAI_API_KEY \
  JAVA_HOME=/path/to/pinned-jdk-21 ANT_HOME=/path/to/pinned-ant \
  scripts/vguide/run-stock-cap16-formal-dataset.sh \
  /path/to/cpachecker-stock /path/to/sv-benchmarks /path/to/benchexec \
  /path/to/cap16-phase-a-package \
  /path/to/cap16-formal-output
```

The research checkout containing this runner must be frozen and published
before launching formal measurements. `summarize-cap16-formal` classifies the
two authenticated repetitions as `stable_hard_solved`,
`stable_analysis_unsolved`, `stable_solved_fast`, wrong, verifier failure,
infrastructure failure or mixed; only the first two enter
`hard-portfolio.csv`.

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

`run-stock-formal-dataset.sh` is the separate executable Phase-B runner. It
does not replace `run-stock-dataset.sh`. It runs only on Valkyrie, rejects
LLM-related environment variables, revision/runtime drift, a nonempty or
overlapping output, or a formal package other than the exact frozen node
topology. Symlinks, devices, sockets, and extra nodes in that package are
rejected. The research checkout, stock CPAchecker, SV-Benchmarks, and
BenchExec must all be clean. Assume-unchanged entries are forbidden; a
materialized skip-worktree node is checked against its index and HEAD type,
executable bit, and blob. Missing skip-worktree entries are accepted only for
the sparse SV-Benchmarks checkout. The runner pins the stock tool,
SV-Benchmarks, BenchExec, JDK, stock `lib/java`, Ant installation, system
Python binary, built JAR semantic content, and formal artifact; it
deliberately does not pin its own research-code commit because that would be
self-referential. The publication release or tag must externally pin the
final research commit.

Arguments six through fourteen are grouped as manifest, raw result, and
survivor for the original Valkyrie shard, r4 reroute, and r5 recovery:

```bash
env -u VGUIDE_LLM -u DEEPSEEK_API_KEY -u OPENAI_API_KEY \
  JAVA_HOME=/path/to/pinned-jdk-21 \
  ANT_HOME=/path/to/pinned-ant/share/ant \
  scripts/vguide/run-stock-formal-dataset.sh \
  /path/to/cpachecker-stock \
  /path/to/sv-benchmarks \
  /path/to/benchexec \
  /path/to/phase-b-merged-survivors-r6-final-20260727 \
  /path/to/320-task-parent/candidate-manifest.json \
  /path/to/original-valkyrie/candidate-manifest-valkyrie.json \
  /path/to/original-valkyrie-result.xml.bz2 \
  /path/to/original-valkyrie-survivor.json \
  /path/to/r4-reroute/candidate-manifest-valkyrie.json \
  /path/to/r4-reroute-result.xml.bz2 \
  /path/to/r4-reroute-survivor.json \
  /path/to/r5-recovery/candidate-manifest-valkyrie.json \
  /path/to/r5-recovery-result.xml.bz2 \
  /path/to/r5-recovery-survivor.json \
  /path/to/formal-output
```

Before creating output, the runner rejects output paths inside any tool,
research, JDK, Ant, Python, package, or Phase-A evidence tree, and rejects
inputs inside the output tree. Runtime closure is checked before output
initialization and again during success and failure teardown. It fixes stock
`lib/java` digest
`eea0df062de5c8e3febe0d96b583741c140e79d3ae41a87a56d7be365b876f9d`,
Ant-installation digest
`52772e241e78a875fa00dea891eac2023d4f2be639a5f28a17dca81580f75e5b`
and Ant 1.10.12, `/usr/bin/python3.10` digest
`7d51cd6b48b521277f5caa4610a82126e315fa2be4df069823a8b1eeb5bd4a86`
and Python 3.10.12, and BenchExec archive digest
`75e3332253429e6f9186352a255cd96c0aff6154a95e2fdd3b737c143ba018bc`
and version 3.35-dev. The Valkyrie P-core lock is cooperative and prevents
only another compliant runner from overlapping. Unrelated work is handled by
the frozen per-case contention policy below; a completely idle host is not a
formal prerequisite.

The exact isolated Python environment used to start BenchExec is also part of
the runtime closure. The runner pins the non-cache `/usr/lib/python3.10`
closure at
`c9af63c831839af73b709cf538807f9ea989c834d635526875a03787c29247cc`,
the exact `yaml`, `_yaml` and `PyYAML-5.4.1.egg-info` closure at
`9dd464e236b90eaa25fc9576bb22442b07817d16e086f9e3754d61c3328d9bbd`,
and the empty non-cache `/usr/local/lib/python3.10/dist-packages` closure at
`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.
Only real `__pycache__` directories are excluded. Sourceless `.pyc`/`.pyo`
outside one remains authenticated and is rejected from inserted saved-script
and BenchExec roots; every other selected-package, standard-library or
local-distribution node remains authenticated.
Under the actual `env -i HOME=/home/benchexec LANG=C.UTF-8 LC_ALL=C.UTF-8
PATH=/usr/bin:/bin JAVA=<pinned-jdk>/bin/java` invocation, it requires the
BenchExec checkout followed by `/usr/lib/python310.zip`, `/usr/lib/python3.10`,
and `/usr/lib/python3.10/lib-dynload` as the exact `sys.path`. Every helper
starts with `-I -S -B -X pycache_prefix=/dev/null` before imports. It never
loads `site` or processes `.pth`/`sitecustomize`; saved-script and BenchExec
paths are inserted explicitly. PyYAML is loaded directly from
`/usr/lib/python3/dist-packages/yaml/__init__.py`, without adding either
distribution-packages root, and must report version 5.4.1. These
paths, versions, module location, and filtered closure hashes are recorded before
measurement and reverified during both success and failure teardown. The
Python 3.10 interpreter does not expose `sys.flags.safe_path`; its equivalent
startup guarantee is authenticated by the exact `-I` argv and exact `sys.path`.
saved `dataset.py` and `baseline.py` commands use this same pinned interpreter
and are therefore covered by the same binary, standard-library, and installed
package closure.

The runner records a startup process/load snapshot. During each BenchExec run,
an isolated standard-library monitor samples `/proc` once per second from
E-core logical CPUs 16–23. It excludes the runner process tree, groups all
other thread CPU-time deltas by process, and observes both hardware threads of
every P-core (logical CPUs 0–15); each thread delta is attributed to the
processor reported by its `/proc` stat record at the sample boundary. A
foreign process is sustained contention only when it consumes at least 50% of
one logical CPU in every sample for at least 10 consecutive seconds. The
JSON-lines evidence records the fixed policy, timestamps, process identity,
measured percentage, and streak duration. Monitor death, an unclean stop, no
sample, malformed evidence, or an event-log/result mismatch outside the exact
authenticated abrupt-recovery case above fails closed. Before each primary or
replacement run, launch waits until the monitor has ten samples and its latest
sample contains no sustained contender; brief activity below the frozen
threshold does not block launch.

The runner builds stock CPAchecker, performs the ten-second machine preflight,
generates the fixed 900/910/920 definition with `render-formal`, and executes
two sequential `-N 2 -c 4` BenchExec repetitions with distinct fixed names.
Raw JAR bytes are not reproducible because ZIP metadata changes: two clean
rebuilds produced raw hashes
`424710996a6b93a6a23e73c35f55a33cb13f058f1dab3342598a30a0021e7b9c`
and
`a4c555548792fb7301dc5c0a6e860018f21da197f07f046108cac762f3207f30`.
Their 5,809 sorted entry names, Unix modes, and content hashes were identical
at semantic digest
`49f95adc5255b89b1bb3edea81ab5f2f660364d36ffa69c3b12508d1e1943be3`,
which is the post-build pin; each run also records its raw JAR hash.
Because `bin/cpachecker` places `classes/` before `cpachecker.jar` on its
classpath, the runner removes the build-created `classes/` tree only after
the JAR semantic digest passes. It then requires `classes/` to remain absent
before measurement and throughout success or failure teardown. Consequently,
an injected loose class cannot shadow the pinned JAR.
Each repetition has independent machine snapshots and a counter check.
The runner correlates each sustained-contention interval with the two
BenchExec task timelines and taints only tasks active during the interval.
It also taints every missing row in an `error="incomplete"` primary result.
Completed untainted primary rows remain accepted. Tainted tasks are rerun with
the unchanged formal protocol; a completed but contaminated replacement is
retained as evidence and retried in a new directory until a clean replacement
exists. An external interruption still stops the process fail-closed; the same
plan commands can resume from its incomplete primary without discarding
completed untainted rows. The runner then writes a hashed repetition plan before
`summarize --hard-threshold 200`. Every missing primary row must be tainted,
only tainted rows may be replaced, replacement definitions must contain
exactly their declared tasks, and no accepted result artifact may be reused
across repetitions.
`summarize` emits `row-provenance.json`, which binds every accepted row to its
primary or replacement result hash and records the replacement reason.

`render-formal-replacement` authenticates the full Phase-B inputs, result, and
taint manifest, then renders the unchanged 900/910/920 protocol for only the
tainted tasks. A cap-16 retry may use a prior replacement result as
its new primary only when its attempt marker authenticates the exact prior
replacement definition and result task set. This covers both an interruption
and a completed attempt with sustained contention. Complete untainted rows
remain accepted, while incomplete or contaminated rows are rendered again;
missing, extra, wrong, or duplicate result rows fail closed. Full primary
results and cap-8 recovery remain strict against the complete formal manifest.
`repetition-plan` binds that definition and its complete result to the primary:

```bash
python3 scripts/vguide/dataset.py render-formal-replacement \
  <the same Phase-B inputs as render-formal> \
  --manifest /path/to/formal-manifest.json \
  --primary-result /path/to/incomplete-primary.xml \
  --taint-manifest /path/to/taint.json \
  --property-file /path/to/sv-benchmarks/c/properties/unreach-call.prp \
  --output-dir /path/to/replacement-definition

python3 scripts/vguide/dataset.py repetition-plan \
  --manifest /path/to/formal-manifest.json --repetition 1 \
  --primary-result /path/to/incomplete-primary.xml \
  --taint-manifest /path/to/taint.json \
  --replacement-result /path/to/replacement-result.xml.bz2 \
  --replacement-definition /path/to/replacement-definition/hard-case-candidates.xml \
  --output /path/to/repetition-1-plan.json
```

The output retains the formal package; the
parent manifest; all three Phase-A manifests, raw results, and survivor
manifests; and the one declared corpus property under relative
`input/evidence/` paths with a relative hash inventory. Thus the copied
evidence can be reauthenticated without its original directories, using the
pinned SV-Benchmarks checkout. It also copies the exact runner, `dataset.py`,
and `baseline.py`, plus research HEAD, empty status/diff evidence, and their
relative hashes under `input/research/`. After that capture, every Python
dataset and provenance command runs from those saved copies. Success and
failure teardown stop the monitor and recheck the live research, stock,
SV-Benchmarks, and BenchExec checkouts, every runtime digest/version, the
BenchExec closure, the saved scripts, and the built JAR when present; drift
fails closed. Generated definitions, build and runner logs, both complete
BenchExec result trees, machine/process evidence, summary, and an artifact
manifest are retained. Artifact inventory rejects symlinks and every other
non-regular, non-directory node instead of following it. Post-initialization
failure attempts an after-state and artifact manifest without masking the
original exit status.

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

Before publishing provenance, expand abbreviated Git revisions with
`git rev-parse` and verify the full object with `git cat-file`; never construct
the missing suffix manually.
