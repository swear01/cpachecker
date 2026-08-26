# Structure

| Path | Purpose |
|------|---------|
| `src/org/sosy_lab/cpachecker/cpa/predicate/vguide/` | **VGuide Java implementation** — LLM bridge, per-loop-head candidate contract (loop-head-candidate-v1), validator + scope check, precision injector, usefulness gate, fail-closed paired-response cache, schema-10 analysis dump |
| `config/vguide.properties` | Runtime defaults: LLM scheduling; **L3 off** (not used after ablation) |
| `config/predicateAnalysis-vguide.properties` | PredicateCPA + VGuide entry config |
| `config/vguide-experiment-usefulness-gate-{off,on}.properties` | Frozen paired experiment configs; general default remains off |
| `config/svcomp26-vguide.properties` | Competition config: routes reachability + overflow through VGuide |
| `config/vguide-experiment-source-prior-{loops,overflow}.properties` | 消融實驗：source-prior mode，base config（predicateAnalysis-vguide 底） |
| `config/vguide-experiment-source-prior-svcomp26-{loops,overflow}.properties` | 消融實驗：source-prior mode，svcomp26 portfolio 底 |
| `scripts/vguided-cegar/run.sh` | Local VGuide/benchmark entry point; formal runs additionally follow the external protocol |
| `/home/swear01/cpachecker-experiments/` | Experiment protocol, task harnesses, raw evidence and reports |
| [GitHub Wiki](https://github.com/swear01/cpachecker/wiki) | Current research design and decisions |
| `docs/vguided-cegar/` | Script/config dependencies only: benchmark sets, predicate sets and evaluation data |
| `docs/vguided-cegar/evaluation/` | Benchmark definitions, frozen replay, and the Phase F predicate-usefulness/context-budget plan |
| `docs/vguided-cegar/evaluation/nla_oracle_smoke_candidates.json` | 12-task reference polynomial candidates + frozen source/YAML hashes |
| `docs/vguided-cegar/evaluation/predicate_usefulness_gate_frozen_20260711.json` | Frozen commits, config/manifest hashes, gate constants, model/solver, and primary resource protocol |
| `docs/vguided-cegar/evaluation/HARD_CASE_DATASET_V2_FINAL.md` | Final Issue #16 dataset identity, counts, release verification, and downstream-use boundary |
| `docs/vguided-cegar/benchmark_sets/` | `.list` manifests read by `run.sh` |
| `docs/vguided-cegar/predicate_sets/` | Frozen predicates for NO_SPURIOUS replay |
| `/home/swear01/cpachecker-experiments/runs/` | Active raw experiment output |
| `/home/swear01/cpachecker-experiments/records/archive/` | Historical material; never current truth |
| `report/` | **LNCS report** (FM 期末,**草稿、尚未投稿**,持續修訂——已納入 v1.7.x schedule 結果;Zenodo artifact DOI `10.5281/zenodo.20745141`) — `main.tex` (llncs.cls), `references.bib`；build artifacts + PDF gitignored |
| `slides/vguide-presentation/` | **Beamer deck** (dark metropolis) — `main.tex`, `metadata.tex` (數字), `slides/NN_*.tex` (一 frame 一檔), `figures/`; `build.sh [light]` |
| `test/` | CPAchecker upstream test suite |
| `build/`, `classes/` | Compiled artifacts |
| `doc/` | Upstream CPAchecker official docs |
| `lib/` | Third-party JARs |
| `~/sv-benchmarks/c` | SV-COMP benchmark tree (external; not in repo) |

## Standalone VGuide LLM call

After `ant build`, prompt experiments can invoke the production Java client without starting a
CPAchecker verification:

```bash
java -cp 'classes:lib/*:lib/java/runtime/*' \
  org.sosy_lab.cpachecker.cpa.predicate.vguide.PredicateProposalCli \
  --system-file /path/to/system.txt \
  --user-file /path/to/user.txt
```

The command uses the same `VGUIDE_LLM_*`, provider credential, model, record/replay, and retry
environment as CPAchecker. The Java client requests SSE streaming and has a 30-second connection
timeout but no total inference deadline. Standard output is one JSON object containing `content`,
`reasoning_content`, `usage`, `latency_ms`, `start_epoch_ms`, `request_hash`, and
`response_source`. Invalid arguments, missing files, configuration failures, HTTP failures, and
malformed or incomplete provider streams terminate nonzero; there is no fallback transport.

## Module Boundaries

- VGuide code (`src/.../vguide/`) is the only place LLM integration lives. Do not add LLM calls elsewhere.
- `PredicateUsefulnessGate` is a deterministic Tier-R filter between validation and precision injection; it never changes standard interpolation or verdict semantics.
- `LlmResponseCache` is evaluation-only infrastructure: record and replay modes are mutually exclusive, keyed by exact request hash plus per-task ordinal, and replay never falls back to a live call.
- `scripts/vguided-cegar/` is the only scripts directory for VGuide experiments. Legacy scripts are in `cpachecker-experiments/records/archive/`.
- GitHub Wiki is the design source of truth; `/home/swear01/cpachecker-experiments/` owns protocol and evidence.
- When searching for current design, exclude historical records, `predicate_sets/`, `output/`, `build/`, and `classes/`.

## Grep / Find Exclude Flags

```bash
# General code/architecture search:
rg ...

# If using grep:
grep -r ... --exclude-dir=archive --exclude-dir=predicate_sets --exclude-dir=output --exclude-dir=build --exclude-dir=classes

# When searching for design specs only (not experiment records):
grep -r ... --exclude-dir=archive --exclude-dir=reports --exclude-dir=predicate_sets --exclude-dir=output
```
