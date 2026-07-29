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

Formal result validation accepts the exact absolute corpus path, the exact
path relative to the generated definition, and BenchExec's exact
`../../../../<corpus-name>/...` spelling from the stock-checkout working
directory. Normalized aliases and other relative spellings remain rejected.

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
survivor for the original Valkyrie shard, r4 reroute, and r5 recovery.
Argument fifteen is the exact frozen r8 failure root:

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
  /path/to/phase-b-formal-valkyrie-r8-attempt2 \
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
the runtime closure. The runner pins `/usr/lib/python3.10` at
`eef7994f6b57cb0bbdb803ef6aadc0c1afbe61d444932eeef5dc5c114b6cf27b`,
`/usr/lib/python3/dist-packages` at
`0970024a48206a1937b5bfbf889335525b769b89a27ca7df25d793d7727b909c`,
and the empty `/usr/local/lib/python3.10/dist-packages` at
`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.
Under the actual `env -i HOME=/home/benchexec LANG=C.UTF-8 LC_ALL=C.UTF-8
PATH=/usr/bin:/bin JAVA=<pinned-jdk>/bin/java` invocation, it requires the
BenchExec checkout followed by `/usr/lib/python310.zip`, `/usr/lib/python3.10`,
`/usr/lib/python3.10/lib-dynload`,
`/usr/local/lib/python3.10/dist-packages`, and
`/usr/lib/python3/dist-packages` as the exact `sys.path`. PyYAML must resolve
to `/usr/lib/python3/dist-packages/yaml/__init__.py` at version 5.4.1. These
paths, versions, module location, and directory hashes are recorded before
measurement and reverified during both success and failure teardown. The
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
measured percentage, and streak duration. Processes that disappear between
`/proc` enumeration and reading are a normal race and are skipped. Sample
wall-clock deltas must agree with their monotonic elapsed intervals within one
millisecond. A monitor watchdog stops the active BenchExec scope when the
monitor dies instead of allowing an unobserved run to continue. Monitor death,
an unclean stop, no sample, malformed evidence, or a mismatch between the
BenchExec event log and result rows fails closed. Before each primary or
replacement run, launch waits
until the monitor has ten samples and its latest sample contains no sustained
contender; brief activity below the frozen threshold does not block launch.
Each BenchExec launcher also owns a separate session, but teardown authority is
the exact named systemd scope. The runner authenticates that scope's
`ControlGroup` under `benchexec.slice`, recursively enumerates its
`cgroup.procs`, and requires the preserved launcher PID to be a member. It then
sends `SIGTERM` and repeated `SIGKILL`, reaps the launcher, and verifies that
the cgroup is empty. Session inspection is only a secondary check, so a
descendant that creates a new session still cannot escape. If the named cgroup
cannot be authenticated, bound to that launcher, or read, the run fails without
claiming successful termination.

The r9 runner is the exact recovery for the interrupted r8 Valkyrie output. It
requires the frozen r8 failure tree whose 146-file aggregate is
`5d36fc0fe6a867ec93b8bb437ede510c26279e66029de22dd68625ed8eacdf2c`
and whose manifest hash is
`6f737f3c48f9632a844367c3f3c4f9286150f520756ce5e09423f73b9ca00ecb`.
It retains that tree as immutable input evidence, rederives the first
repetition's 18 contaminated rows and clean 18-row replacement, and preserves
all 270 accepted first-repetition rows. For the interrupted second repetition,
strict monitor coverage accepts 13 completed rows and taints 253 incomplete
plus four completed-but-uncovered rows; only those 257 tasks are replaced.
The old results remain byte-identical, while a new plan binds them to a
definition regenerated at the recovery output path. The runner builds stock
CPAchecker, performs the ten-second machine preflight, generates the fixed
900/910/920 definitions, and executes replacement attempts with `-N 2 -c 4`.
The copied r8 tree is reauthenticated before measurement and twice during
successful final closure, including once after the final artifact inventory.
Authentication derives the only permitted directory set from the pinned file
manifest plus the manifest file itself, so extra empty directories, symlinks,
and other special nodes fail closed.
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
Completed primary rows remain accepted only when valid monitor samples cover
their complete logged execution interval; rows that extend outside that
coverage are tainted. Completed untainted primary rows remain accepted. Tainted
tasks are rerun with the unchanged formal protocol; a completed but
contaminated replacement is retained as evidence and retried in a new
directory until a clean replacement exists. An external interruption still
stops the process fail-closed; the same plan commands can resume from its
incomplete primary without discarding completed untainted rows. The runner
then writes a hashed repetition plan before `summarize --hard-threshold 200`.
Every missing primary row must be tainted, only tainted rows may be replaced,
replacement definitions must contain
exactly their declared tasks, and no accepted result artifact may be reused
across repetitions.
`summarize` emits `row-provenance.json`, which binds every accepted row to its
primary or replacement result hash and records the replacement reason.

The same runner enters the frozen cap-8 r10 recovery only with its 18-argument
form: the final four arguments are the r9 output tree, r9 launch log, r9 exit
status, and new output directory. The 16-argument r9 path is unchanged. R10
accepts only the artifact tree with manifest
`0a4e978e90fd4c969c61fe6c4d8a7e475ef939933b642aeaffe2c21500fe92a1`
and aggregate
`1e29c7f7a79f5e930529c4bd958f3dcf34dbd5e1c93a6d6dfbc6651b44126f7a`,
plus the pinned external launch log and exit status. This exact failed attempt
contains 257 rows: 67 complete untainted rows are reusable and 190 rows remain
pending (182 incomplete and eight contaminated). Root
`error="interrupted"` is accepted only while this exact tree, result, log,
monitor, failure status, and external failure evidence authenticate; normal
complete results and every other partial path still reject it.

R10 preserves the raw interrupted XML. Each version-2 repetition-plan entry
hashes its result, definition, taint, BenchExec log, and load monitor. Entries
are applied sequentially to exactly the preceding tainted set; accepted rows
are derived as attempted tasks minus that entry's taint. Accepted sets must be
disjoint and the final taint must be empty. The runner therefore renders only
the current remainder after every attempt instead of restarting completed
cases. If an authenticated attempt leaves that remainder unchanged, its raw
result, log, monitor, and taint remain in the output and the run fails closed
instead of retrying forever. Symlinks, special nodes, path escapes, topology
drift, task drift, hash drift, non-exact coverage, or unauthenticated
interrupted XML fail closed.

`render-formal-replacement` authenticates the full Phase-B inputs, incomplete
primary and taint manifest, then renders the unchanged 900/910/920 protocol for
only the tainted tasks. `repetition-plan` binds that definition and its complete
result to the primary:

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
