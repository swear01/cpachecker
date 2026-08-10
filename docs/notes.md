# Notes

> Tacit knowledge an agent can't infer from reading code.

## Gotchas

- **`archive/` is NOT authoritative.** If a grep result points into `archive/`, discard it and look in `docs/vguided-cegar/` instead. If no current equivalent exists, surface the gap to the user.
- **`~/sv-benchmarks/c` is external.** It must exist locally before running experiments; it is not in the repo. Export `SV_BENCHMARKS=~/sv-benchmarks/c` before any `run.sh` call.
- **`DEEPSEEK_API_KEY` is required for live/record mode.** A paired replay may omit it only when `VGUIDE_LLM_REPLAY_DIR` is set. Record/replay are mutually exclusive and a replay miss terminates the run instead of falling back to the live API or stock behavior.
- **`output/vguide/` is gitignored.** Experiment results live locally only. Do not commit them.
- **Raw output lifecycle (both git-ignored).** Active raw → `output/vguide/experiments/` (run.sh writes here automatically). Retired raw → `mv` it to `archive/raw-legacy/` to keep it; do NOT delete raw just to free git (it's already ignored), and never put raw in tracked dirs.
- **LLM soundness constraint.** VGuide must only propose candidates (Tier S) or control resources/routing (Tier R). Never let LLM output be used as a direct verdict or unverified assumption (Tier X = forbidden).
- **Loop-head candidate contract (Issue #4, since 2026-08-10).** The LLM output contract is `loop-head-candidate-v1`: every candidate must name its loop head(s). Legacy `{"predicates":[...]}` responses are rejected per item as `missing_loop_head` — do NOT re-introduce implicit broadcast. Free variables must be visible at the named head (encoded vocabulary + function scope). `over_specific`/`group_conflict` are advisory diagnostics; `group_conflict` is computed only when `vguide.enableL3Entailment=true`. Dump schema is 5 (`candidate_rejections`).
- **Termination branch is Class-B.** The `termination.config` path uses `TerminationToReachCPA`, not PredicateCPA. VGuide cannot fire there without a new Java ranking-function hook. Do not attempt Class-A config tricks for termination.
- **`predicate_sets/` is frozen replay data**, not design specs. Exclude it from architecture searches.
- **`reports/` is result records**, not current design. Exclude it when searching for specs or architecture.
- **Config naming convention:** `<set>_vguide` / `<set>_stock` for experiment output directories.
- **`archive/` is a local-only history pile (git-ignored).** `/archive` is in `.gitignore`, so the base-block archive workflow (`agents_rule archive` → git `R` rename) does NOT apply here. To retire a doc, move it under `archive/` with plain `git mv`/`mv` (it leaves git tracking) or just keep it local; do not expect a rename in `git status`. The one-off 2026-06-15 cleanup deleted ~593MB of retired raw (results-legacy / experiments-legacy); only analysis `.md` files are kept. Going forward, retire raw by moving it to `archive/raw-legacy/` (don't delete) — see the raw-output-lifecycle gotcha above.

- **Termination experiment harness (lasso route) — three easy-to-miss settings.** When running termination via `run.sh --mode termination-stock|termination-vguide` (see `vguided-cegar/TERMINATION_RANKING_HOOK_PLAN.md` §7):
  - **No `--spec`.** Termination configs use internal automata (`termination_as_reach.spc`, `TerminatingFunctions.spc`); passing `default.spc`/`sv-comp-reachability.spc` overrides and breaks termination detection. The harness sets `VGUIDE_SPEC=` (empty) for termination modes so `run_benchmark_set.sh` skips `--spec`.
  - **`useVocabularyGuide=false`.** Termination's inner safety analysis is predicate-CEGAR-based, so leaving the reachability VGuide on would fire it *inside* termination and confound the ranking-function hook. Harness sets `VGUIDE_USE_VOCABULARY_GUIDE=false`.
  - **`analysis.machineModel=Linux64`.** termination-crafted/-crafted-lit/-numeric are all LP64; the harness otherwise defaults to ILP32 and wrong int widths can flip termination verdicts (0-wrong risk). Harness auto-adds it for `termination-*` modes.
- **Stock lasso-only termination config = `config/components/termination-composition-lassoBasedAnalysis.properties`** (runs standalone, verified TRUE/FALSE). The full `terminationAnalysis.properties` is the *parallel portfolio* (lasso ∥ terminationToSafety); use lasso-only to isolate the ranking hook for clean attribution.
- **Termination benchmark scoping.** The dedicated integer families (`termination-crafted`, `termination-crafted-lit`, `termination-numeric` = 146 tasks, `benchmark_sets/termination_scalar.list`) are the ranking-function targets. Big dirs under `termination.prp` (product-lines 597, eca-rers2012 200, seq-mthreaded 143) are reactive systems, not loop-ranking targets — excluded.

## Decisions

- **Predicate usefulness gate is the active result (2026-07-11).** Frozen rule: reject a precision batch when loop-head visits ≤8 and at least2 unique validated formulas contain `bvmul`; disable later LLM rounds but retain standard refinement. Offline replay predicted7/7 loss recovery with0 sacrificed wins on the selection arm. Fresh online targeted runs confirmed7/7 losses recovered and2/2 VGuide-only wins preserved,0 wrong. Thresholds are now frozen pending held-out/full764 evaluation. Report: `vguided-cegar/reports/2026-07-11_predicate_usefulness_gate.md`.
- **Paired response cache is experimental evidence infrastructure, not a predicate source.** `VGUIDE_LLM_RECORD_DIR` records exact request-hash/ordinal responses per task; `VGUIDE_LLM_REPLAY_DIR` replays them fail-closed and preserves recorded latency by default. The runner sets `VGUIDE_LLM_CACHE_NAMESPACE` to the task name. Do not confuse this with `predicate_sets/` frozen semantic seeds.
- **VGuide-NLA stopped after the final consumer gate on 2026-07-11.** Exact-BV and repaired exact NIA/Z3 individual candidates, per-location conjunction, KI-PDR, and direct PDR root/vocabulary modes all produced0/12 oracle delta and0 wrong. No CTI helper will be built on current consumers. See `vguided-cegar/VGUIDE_NLA_PLAN.md`.
- **Do not start a dynamic LLM helper before the final consumer gate.** The only permitted core change is a test-only oracle loader for conjunction/PDR capacity. CTI-local generation remains blocked until reference predicates produce target-proof direct wins.
- **Ordinary k-induction oracle-capacity result (2026-07-11).** Harness/TDD is complete. Current-commit exact-BV/MathSAT and repaired exact NIA/Z3 both solve 0/12 stock and 0/12 oracle at 60s; `ps2-ll` BV remains UNKNOWN at 300s. Z3 4.15.4 repair eliminated the ABI blocker. This RED stops candidate-generation work on that consumer, while the final PDR/KI-PDR matrix tests structurally different consumers. Reports: `vguided-cegar/reports/2026-07-11_nla_oracle_capacity_smoke.md` and `vguided-cegar/reports/2026-07-11_pdr_oracle_capacity_matrix.md`.
- **Source-prior ablation:** `vguide.sourcePriorMode=true` fires LLM at analysis start (before any CEGAR round) with source-code-only context (no CE trace). Predicates injected into `PredicateCPA.getInitialPrecision()` via `registerPreCegarBridge()`, so they are active from round 0. Risk: LLM call on all tasks including fast ones (PAR-2 overhead). Ablation question: does CE context help, or is source code enough?
  - base config: `--mode source-prior-loops` / `source-prior-overflow` (8 parallel OK)
  - svcomp26 portfolio: `--mode source-prior-svcomp26-loops` / `source-prior-svcomp26-overflow` (2 parallel MAX — heavier)
  - **Must run one experiment group at a time** — running two groups simultaneously makes results inaccurate (too many JVMs competing). See `RUN_EXPERIMENTS.md` for the sequential launch block.

- **Unified VGuide (single Java path):** Previous B2/B4/B5 sidecar design was replaced. Only one implementation path now. See `architecture/UNIFIED_VGUIDE_ARCHITECTURE.md`.
- **Class-A first:** Any new property category should attempt config-only generalization (Class-A) before touching Java. v1.6 overflow proved this works for predicate-CEGAR-based branches.
- **No `grep` into `archive/`.** Use `rg` (respects `.gitignore`, which excludes `archive/`) or always pass `--exclude-dir=archive`.
- **DeepSeek V4 (non-thinking) as primary model.** Thinking mode not used in production path; see `llm/LLM_API.md` for rationale.
- **L3 not used (noL3).** Validation is L1+L2 only (`vguide.enableL3Entailment=false`). A 2026-06-07 `full_scalar` ablation showed L3-on worse overall (fewer solves, higher PAR-2); all mainline evals since then keep L3 off.
- **Overflow prompt is neutral.** The reachability prompt actively discourages the bound predicates that overflow needs. A dedicated overflow-aware prompt is the main lever for v1.6.1 improvement (P1), not config tweaks.
