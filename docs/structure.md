# Structure

| Path | Purpose |
|------|---------|
| `src/org/sosy_lab/cpachecker/cpa/predicate/vguide/` | **VGuide Java implementation** — LLM bridge, validator, precision injector |
| `config/vguide.properties` | Runtime defaults: LLM scheduling; **L3 off** (not used after ablation) |
| `config/predicateAnalysis-vguide.properties` | PredicateCPA + VGuide entry config |
| `config/vguide-experiment-usefulness-gate-{off,on}.properties` | Frozen paired experiment configs; general default remains off |
| `config/svcomp26-vguide.properties` | Competition config: routes reachability + overflow through VGuide |
| `config/vguide-experiment-source-prior-{loops,overflow}.properties` | 消融實驗：source-prior mode，base config（predicateAnalysis-vguide 底） |
| `config/vguide-experiment-source-prior-svcomp26-{loops,overflow}.properties` | 消融實驗：source-prior mode，svcomp26 portfolio 底 |
| `scripts/vguided-cegar/run.sh` | **Single entry point** for all experiments and bench setup |
| `scripts/vguided-cegar/oracle_capacity_harness.py` | VGuide-NLA TDD harness：catalog/hash validation、ordinary/KI-PDR/direct-PDR consumers、root/vocabulary modes、comparison/provenance |
| `scripts/vguided-cegar/analyze_predicate_usefulness_gate.py` | Replays the frozen first-call gate over recorded stock/VGuide summaries and logs |
| `scripts/vguided-cegar/post_batch_analysis.sh` | PAR-2 / cactus analysis after batch runs |
| `docs/vguided-cegar/` | All active research documentation |
| `docs/vguided-cegar/VGUIDE_NLA_PLAN.md` | **Current main plan** — two execution batches; sole breakpoint before changing BMC core |
| `docs/vguided-cegar/RUN_EXPERIMENTS.md` | How to run experiments end-to-end |
| `docs/vguided-cegar/architecture/` | Current design specs |
| `docs/vguided-cegar/llm/` | LLM scheduling, ensemble, budget, API docs |
| `docs/vguided-cegar/evaluation/` | Benchmark definitions, frozen replay |
| `docs/vguided-cegar/evaluation/nla_oracle_smoke_candidates.json` | 12-task reference polynomial candidates + frozen source/YAML hashes |
| `docs/vguided-cegar/benchmark_sets/` | `.list` manifests read by `run.sh` |
| `docs/vguided-cegar/predicate_sets/` | Frozen predicates for NO_SPURIOUS replay |
| `docs/vguided-cegar/reports/` | Experiment result records (not design specs) |
| `output/vguide/experiments/` | **Active raw output** — batch run products, written by `run.sh` (gitignored) |
| `archive/raw-legacy/` | **Retired raw output** parking — `mv` old raw here instead of deleting (gitignored) |
| `archive/` | **Obsolete** historical material — never treat as current truth |
| `report/` | **LNCS report** (FM 期末,**草稿、尚未投稿**,持續修訂——已納入 v1.7.x schedule 結果;Zenodo artifact DOI `10.5281/zenodo.20745141`) — `main.tex` (llncs.cls), `references.bib`；build artifacts + PDF gitignored |
| `slides/vguide-presentation/` | **Beamer deck** (dark metropolis) — `main.tex`, `metadata.tex` (數字), `slides/NN_*.tex` (一 frame 一檔), `figures/`; `build.sh [light]` |
| `test/` | CPAchecker upstream test suite |
| `build/`, `classes/` | Compiled artifacts |
| `doc/` | Upstream CPAchecker official docs |
| `lib/` | Third-party JARs |
| `~/sv-benchmarks/c` | SV-COMP benchmark tree (external; not in repo) |

## Module Boundaries

- VGuide code (`src/.../vguide/`) is the only place LLM integration lives. Do not add LLM calls elsewhere.
- `PredicateUsefulnessGate` is a deterministic Tier-R filter between validation and precision injection; it never changes standard interpolation or verdict semantics.
- `scripts/vguided-cegar/` is the only scripts directory for VGuide experiments. Legacy scripts are in `archive/`.
- `docs/vguided-cegar/` is the single source of truth for active research docs. `archive/` is not authoritative.
- `output/vguide/` is runtime output only — never commit it.
- **Raw output lifecycle:** active raw → `output/vguide/experiments/` (run.sh writes here); retired raw → `mv` to `archive/raw-legacy/` (keep, don't delete). Both git-ignored.
- When searching for current design, exclude: `archive/`, `reports/`, `predicate_sets/`, `output/`, `build/`, `classes/`.

## Grep / Find Exclude Flags

```bash
# General code/architecture search:
rg ...  # rg respects .gitignore which already excludes archive/ (/archive is in .gitignore)

# If using grep:
grep -r ... --exclude-dir=archive --exclude-dir=predicate_sets --exclude-dir=output --exclude-dir=build --exclude-dir=classes

# When searching for design specs only (not experiment records):
grep -r ... --exclude-dir=archive --exclude-dir=reports --exclude-dir=predicate_sets --exclude-dir=output
```
