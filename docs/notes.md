# Notes

> Tacit knowledge an agent can't infer from reading code.

## Gotchas

- **`archive/` is NOT authoritative.** If a grep result points into `archive/`, discard it and look in `docs/vguided-cegar/` instead. If no current equivalent exists, surface the gap to the user.
- **`~/sv-benchmarks/c` is external.** It must exist locally before running experiments; it is not in the repo. Export `SV_BENCHMARKS=~/sv-benchmarks/c` before any `run.sh` call.
- **`DEEPSEEK_API_KEY` must be set.** All LLM calls fail silently if the key is missing — check env before debugging VGuide behavior.
- **`output/vguide/` is gitignored.** Experiment results live locally only. Do not commit them.
- **Raw output lifecycle (both git-ignored).** Active raw → `output/vguide/experiments/` (run.sh writes here automatically). Retired raw → `mv` it to `archive/raw-legacy/` to keep it; do NOT delete raw just to free git (it's already ignored), and never put raw in tracked dirs.
- **LLM soundness constraint.** VGuide must only propose candidates (Tier S) or control resources/routing (Tier R). Never let LLM output be used as a direct verdict or unverified assumption (Tier X = forbidden).
- **Termination branch is Class-B.** The `termination.config` path uses `TerminationToReachCPA`, not PredicateCPA. VGuide cannot fire there without a new Java ranking-function hook. Do not attempt Class-A config tricks for termination.
- **`predicate_sets/` is frozen replay data**, not design specs. Exclude it from architecture searches.
- **`reports/` is result records**, not current design. Exclude it when searching for specs or architecture.
- **Config naming convention:** `<set>_vguide` / `<set>_stock` for experiment output directories.
- **`archive/` is a local-only history pile (git-ignored).** `/archive` is in `.gitignore`, so the base-block archive workflow (`agents_rule archive` → git `R` rename) does NOT apply here. To retire a doc, move it under `archive/` with plain `git mv`/`mv` (it leaves git tracking) or just keep it local; do not expect a rename in `git status`. The one-off 2026-06-15 cleanup deleted ~593MB of retired raw (results-legacy / experiments-legacy); only analysis `.md` files are kept. Going forward, retire raw by moving it to `archive/raw-legacy/` (don't delete) — see the raw-output-lifecycle gotcha above.

## Decisions

- **Source-prior ablation:** `vguide.sourcePriorMode=true` fires LLM at analysis start (before any CEGAR round) with source-code-only context (no CE trace). Predicates injected into `PredicateCPA.getInitialPrecision()` via `registerPreCegarBridge()`, so they are active from round 0. Risk: LLM call on all tasks including fast ones (PAR-2 overhead). Ablation question: does CE context help, or is source code enough?
  - base config: `--mode source-prior-loops` / `source-prior-overflow` (8 parallel OK)
  - svcomp26 portfolio: `--mode source-prior-svcomp26-loops` / `source-prior-svcomp26-overflow` (2 parallel MAX — heavier)
  - **Must run one experiment group at a time** — running two groups simultaneously makes results inaccurate (too many JVMs competing). See `RUN_EXPERIMENTS.md` for the sequential launch block.

- **Unified VGuide (single Java path):** Previous B2/B4/B5 sidecar design was replaced. Only one implementation path now. See `architecture/UNIFIED_VGUIDE_ARCHITECTURE.md`.
- **Class-A first:** Any new property category should attempt config-only generalization (Class-A) before touching Java. v1.6 overflow proved this works for predicate-CEGAR-based branches.
- **No `grep` into `archive/`.** Use `rg` (respects `.gitignore`, which excludes `archive/`) or always pass `--exclude-dir=archive`.
- **DeepSeek V4 (non-thinking) as primary model.** Thinking mode not used in production path; see `llm/LLM_API.md` for rationale.
- **Overflow prompt is neutral.** The reachability prompt actively discourages the bound predicates that overflow needs. A dedicated overflow-aware prompt is the main lever for v1.6.1 improvement (P1), not config tweaks.
