# Notes

> Tacit knowledge an agent can't infer from reading code.

## Gotchas

- **正式 run 一律用 `launch_isolated_run.sh`（獨立 git worktree，since 2026-08-16，#93）。** NFS 共享 repo 的 classes/ 在執行中 rebuild 會讓 JVM `NoClassDefFoundError: ...$1`（匿名 class 不一致）crash 整個 run（2026-08-16 兩次：212/224、174/224 crash 作廢）；改被執行中的 script 也會 bash `unexpected EOF`（arm-2/stock 各中招）。worktree 執行後主 repo 可隨時開發。勿再直接在主 repo 跑正式 run。
- **每個實驗必須先建立 GitHub tracking issue（流程 #97）。** Issue 是跨 agent/session 的生命週期介面：launch 前記 hypothesis、arms、commit/config/manifest/spec hashes、provider/route、資源協議、exact command、output path 與 acceptance criteria；launch 時記 machine/worktree/start/run id；執行中記 provider/infrastructure failures 與 reruns；harvest 時回貼完整 records、verdict/wrong/dispute/failure/PAR-2、validity decision、artifact paths/hashes。Issue 不能取代 `run_meta.json`、`records.jsonl` 與 raw logs。
- **764 全量 run 必須用 `run.sh --mode svcomp26-vguide`（或明確設 `VGUIDE_CONFIG`/`VGUIDE_SVCOMP`/`VGUIDE_SPEC`）— since 2026-08-14.** `run_benchmark_set.sh` 的 config 預設是 `predicateAnalysis-vguide`；直接跑它會與既有 764 數據（`svcomp26-vguide`）不可比。2026-08-14 的 Flash run 就是這樣作廢的（漏 `VGUIDE_CONFIG` → 613 vs 242 LLM 觸發、全部收割結論作廢，見 #76）。完整 launch 環境對照：`cpachecker-experiments/docs/LAUNCH_RECIPES.md`（sibling）。收割前驗證：summary CSV 的 `config` 欄位（2026-08-14 起記錄）或任一 task log 開頭的 `CPAchecker ... / <config>` 字串。

- **Source slicing for huge programs (issue #74, since 2026-08-14).** `ContextPackBuilder` slices sources >100K chars (`SourceSlicer.SLICE_THRESHOLD`) to the loop-head lines + CE-path statement lines + assertion line (margin ±2) before they enter the LLM prompt; small sources pass through untouched. Applies to both `build()` and `buildSourceOnly()`. The assertion line detection matches `__VERIFIER_assert` or `reach_error();` (eca family uses `reach_error()`). The slice keeps constant-array *declarations* but drops their values (neural-net weights etc.) — the SMT validator uses the real program constants, and loop invariants are structural, so values are not needed for LLM proposals. **Known limitation:** line numbers are per-file; slicing assumes a single source file (all 224 core-only tasks are single-file; multi-file programs >100K chars would misalign ranges).
- **Phase F prompt contract (issues #104–#109).** Source-level array reads use `a[i]` and are translated by `ArrayTermTranslator`; prompts must not simultaneously ban and request that syntax. Scalar declaration hints must cover simple comma-separated declarations. The full context-budget/usefulness design is tracked in `docs/vguided-cegar/evaluation/PHASE_F_PREDICATE_USEFULNESS_HARNESS_PLAN.md` and must stay separate from formal #100/#102 claims.
- **VGuide predicates are state partitions, not required invariants (issue #119, since 2026-08-20).** The default per-response budget is 8–12. Prompts explicitly welcome initiation-only, exit-only, threshold, violation-state, and path-splitting predicates and ask for broad informed guesses; judge them by validation and downstream CEGAR usefulness, not by whether each formula holds at every loop-head visit.
- **VGuide defaults to one SAFE profile per LLM round (issue #122, since 2026-08-20).** Historical BUG_HUNT results showed no new correct FALSE outcomes, so `dualPromptMode=false` and the SAFE response owns the full 8–12 round budget. BUG_HUNT remains explicit long-term research only (#121), not part of formal default runs.

- **`cpachecker-experiments/records/archive/` is NOT authoritative.** If a grep result points into `cpachecker-experiments/records/archive/`, discard it and look in `docs/vguided-cegar/` instead. If no current equivalent exists, surface the gap to the user.
- **`~/sv-benchmarks/c` is external.** It must exist locally before running experiments; it is not in the repo. Export `SV_BENCHMARKS=~/sv-benchmarks/c` before any `run.sh` call.
- **`DEEPSEEK_API_KEY` is required for live/record mode.** A paired replay may omit it only when `VGUIDE_LLM_REPLAY_DIR` is set. Record/replay are mutually exclusive and a replay miss terminates the run instead of falling back to the live API or stock behavior.
- **`cpachecker-experiments/runs/legacy_output_2026/vguide/` is gitignored.** Experiment results live locally only. Do not commit them.
- **Raw output lifecycle (both git-ignored).** Active raw → `cpachecker-experiments/runs/legacy_output_2026/vguide/experiments/` (run.sh writes here automatically). Retired raw → `mv` it to `cpachecker-experiments/records/archive/raw-legacy/` to keep it; do NOT delete raw just to free git (it's already ignored), and never put raw in tracked dirs.
- **Native-solver test exclusions (issues #30/#111, since 2026-08-11).** `SolverViewBasedTest0`
  assumes-away OpenSMT, Z3, Z3_WITH_INTERPOLATION, CVC4, CVC5, BITWUZLA (besides BOOLECTOR/YICES2),
  **gated on the env var `VGUIDE_SKIP_BROKEN_NATIVE_SOLVERS=1`** (value must be "1" or
  "true"): other machines keep full solver coverage. On this machine the bundled native libs
  crash/cannot load (Z3 4.15.4 needs glibc 2.38; Z3 4.5.0 legacy segfaults; bitwuzla/cvc5 JNI
  crash in the shared JVM), and loading OpenSMT before MathSAT contaminates MathSAT's native
  symbol state in parameterized tests (issue #111) — run `VGUIDE_SKIP_BROKEN_NATIVE_SOLVERS=1
  ant unit-tests` here. The JUnit unit-test baseline with the gate has 0 crashed classes and no
  known solver-test failures. Machines without the gate retain full solver coverage.
- **Configuration-check baseline is explicitly classified (issue #116).** The forked checker now
  pins its JVM to `-Xmx4g`, preventing JavaBDD's `Runtime.maxMemory()`-based table sizing from
  overflowing on large-memory hosts; bare `ant configuration-checks` no longer needs an environment
  heap override. The VGuide fragment and named research/portfolio configs that require
  launcher-supplied `cpa.predicate.refinement.useVocabularyGuide=true`, an external provider, or
  a non-empty benchmark are checked by parsing and default-specification validation only. Other
  VGuide components and non-VGuide configs remain runnable checks; VGuide component checks need
  the normal provider or replay environment. The checker does not globally
  suppress `vguide.*` or silently add the VGuide hook.
- **Formal-run CPU isolation is mandatory (Baseline-Protocol, since 2026-08-11).**
  Any timing-sensitive experiment (baselines, core-only 224, future ablation runs) must pin
  CPA invocations with `taskset -c 0,2,4,6,8,10,12,14` (8 physical P-cores, no SMT sibling,
  no E-core), refuse to start when the P-core pool is busy (mpstat ≥50% or concurrent local
  processes), record `cpu_isolation`/`load_check` in run_meta.json, and pick the machine via
  the fleet availability monitor (valkyrie/athena/cthulhu, idle_ready; 13900K/14900K P-cores
  are comparable and mixable). `run_core_only.sh` implements this. Contaminated runs are
  invalid for timing claims. Full text: `docs/EXPERIMENT_PROTOCOL.md` (branch
  `research/vguide-upstream-reimpl`). The 2026-08-11 stock+augmented 224 runs predate this
  and are a rough usefulness check only.
- **LLM soundness constraint.** VGuide must only propose candidates (Tier S) or control resources/routing (Tier R). Never let LLM output be used as a direct verdict or unverified assumption (Tier X = forbidden).
- **Loop-head candidate contract (Issue #4, since 2026-08-10).** The LLM output contract is `loop-head-candidate-v1`: every candidate must name its loop head(s). Legacy `{"predicates":[...]}` responses are rejected per item as `missing_loop_head` — do NOT re-introduce implicit broadcast. Free variables must be visible at the named head (encoded vocabulary + function scope). `over_specific`/`group_conflict` are advisory diagnostics; `group_conflict` is computed only when `vguide.enableL3Entailment=true`. Dump schema is 5 (`candidate_rejections`).
- **Termination branch is Class-B.** The `termination.config` path uses `TerminationToReachCPA`, not PredicateCPA. VGuide cannot fire there without a new Java ranking-function hook. Do not attempt Class-A config tricks for termination.
- **`predicate_sets/` is frozen replay data**, not design specs. Exclude it from architecture searches.
- **`reports/` is result records**, not current design. Exclude it when searching for specs or architecture.
- **Config naming convention:** `<set>_vguide` / `<set>_stock` for experiment output directories.
- **`cpachecker-experiments/records/archive/` is a local-only history pile (git-ignored).** `/archive` is in `.gitignore`, so the base-block archive workflow (`agents_rule archive` → git `R` rename) does NOT apply here. To retire a doc, move it under `cpachecker-experiments/records/archive/` with plain `git mv`/`mv` (it leaves git tracking) or just keep it local; do not expect a rename in `git status`. The one-off 2026-06-15 cleanup deleted ~593MB of retired raw (results-legacy / experiments-legacy); only analysis `.md` files are kept. Going forward, retire raw by moving it to `cpachecker-experiments/records/archive/raw-legacy/` (don't delete) — see the raw-output-lifecycle gotcha above.

- **Termination experiment harness (lasso route) — three easy-to-miss settings.** When running termination via `run.sh --mode termination-stock|termination-vguide` (see `cpachecker-experiments/docs/vguided-cegar/TERMINATION_RANKING_HOOK_PLAN.md` §7):
  - **No `--spec`.** Termination configs use internal automata (`termination_as_reach.spc`, `TerminatingFunctions.spc`); passing `default.spc`/`sv-comp-reachability.spc` overrides and breaks termination detection. The harness sets `VGUIDE_SPEC=` (empty) for termination modes so `run_benchmark_set.sh` skips `--spec`.
  - **`useVocabularyGuide=false`.** Termination's inner safety analysis is predicate-CEGAR-based, so leaving the reachability VGuide on would fire it *inside* termination and confound the ranking-function hook. Harness sets `VGUIDE_USE_VOCABULARY_GUIDE=false`.
  - **`analysis.machineModel=Linux64`.** termination-crafted/-crafted-lit/-numeric are all LP64; the harness otherwise defaults to ILP32 and wrong int widths can flip termination verdicts (0-wrong risk). Harness auto-adds it for `termination-*` modes.
- **Stock lasso-only termination config = `config/components/termination-composition-lassoBasedAnalysis.properties`** (runs standalone, verified TRUE/FALSE). The full `terminationAnalysis.properties` is the *parallel portfolio* (lasso ∥ terminationToSafety); use lasso-only to isolate the ranking hook for clean attribution.
- **Termination benchmark scoping.** The dedicated integer families (`termination-crafted`, `termination-crafted-lit`, `termination-numeric` = 146 tasks, `benchmark_sets/termination_scalar.list`) are the ranking-function targets. Big dirs under `termination.prp` (product-lines 597, eca-rers2012 200, seq-mthreaded 143) are reactive systems, not loop-ranking targets — excluded.

## Decisions

- **Predicate usefulness gate is the active result (2026-07-11).** Frozen rule: reject a precision batch when loop-head visits ≤8 and at least2 unique validated formulas contain `bvmul`; disable later LLM rounds but retain standard refinement. Offline replay predicted7/7 loss recovery with0 sacrificed wins on the selection arm. Fresh online targeted runs confirmed7/7 losses recovered and2/2 VGuide-only wins preserved,0 wrong. Thresholds are now frozen pending held-out/full764 evaluation. Report: `cpachecker-experiments/docs/vguided-cegar/reports/2026-07-11_predicate_usefulness_gate.md`.
- **Paired response cache is experimental evidence infrastructure, not a predicate source.** `VGUIDE_LLM_RECORD_DIR` records exact request-hash/ordinal responses per task; `VGUIDE_LLM_REPLAY_DIR` replays them fail-closed and preserves recorded latency by default. The runner sets `VGUIDE_LLM_CACHE_NAMESPACE` to the task name. Do not confuse this with `predicate_sets/` frozen semantic seeds.
- **VGuide-NLA stopped after the final consumer gate on 2026-07-11.** Exact-BV and repaired exact NIA/Z3 individual candidates, per-location conjunction, KI-PDR, and direct PDR root/vocabulary modes all produced0/12 oracle delta and0 wrong. No CTI helper will be built on current consumers. See `cpachecker-experiments/docs/vguided-cegar/VGUIDE_NLA_PLAN.md`.
- **Do not start a dynamic LLM helper before the final consumer gate.** The only permitted core change is a test-only oracle loader for conjunction/PDR capacity. CTI-local generation remains blocked until reference predicates produce target-proof direct wins.
- **Ordinary k-induction oracle-capacity result (2026-07-11).** Harness/TDD is complete. Current-commit exact-BV/MathSAT and repaired exact NIA/Z3 both solve 0/12 stock and 0/12 oracle at 60s; `ps2-ll` BV remains UNKNOWN at 300s. Z3 4.15.4 repair eliminated the ABI blocker. This RED stops candidate-generation work on that consumer, while the final PDR/KI-PDR matrix tests structurally different consumers. Reports: `cpachecker-experiments/docs/vguided-cegar/reports/2026-07-11_nla_oracle_capacity_smoke.md` and `cpachecker-experiments/docs/vguided-cegar/reports/2026-07-11_pdr_oracle_capacity_matrix.md`.
- **Source-prior ablation:** `vguide.sourcePriorMode=true` fires LLM at analysis start (before any CEGAR round) with source-code-only context (no CE trace). Predicates injected into `PredicateCPA.getInitialPrecision()` via `registerPreCegarBridge()`, so they are active from round 0. Risk: LLM call on all tasks including fast ones (PAR-2 overhead). Ablation question: does CE context help, or is source code enough?
  - base config: `--mode source-prior-loops` / `source-prior-overflow` (8 parallel OK)
  - svcomp26 portfolio: `--mode source-prior-svcomp26-loops` / `source-prior-svcomp26-overflow` (2 parallel MAX — heavier)
  - **Must run one experiment group at a time** — running two groups simultaneously makes results inaccurate (too many JVMs competing). See `RUN_EXPERIMENTS.md` for the sequential launch block.

- **Unified VGuide (single Java path):** Previous B2/B4/B5 sidecar design was replaced. Only one implementation path now. See `architecture/UNIFIED_VGUIDE_ARCHITECTURE.md`.
- **Explicit LLM transport contracts:** `VGUIDE_LLM_PROVIDER=deepseek` (default) sends DeepSeek Chat Completions with `response_format: {"type":"json_object"}` and uses `DEEPSEEK_API_KEY`. `VGUIDE_LLM_PROVIDER=meta` sends Meta Chat Completions for `muse-spark-1.2-contributor` with the full `loop-head-candidate-v1` JSON schema, no DeepSeek `thinking` field, and uses `MODEL_API_KEY`; `VGUIDE_LLM_THINKING=disabled` selects Meta's minimum `reasoning_effort=minimal`, while enabled selects `VGUIDE_LLM_REASONING_EFFORT`. Core-only metadata records the provider and provider-specific API format, so incompatible runs cannot resume into the same output directory.
- **LLM experiments must reuse the production Java transport path.** Prompt probes and A/B experiments must call `PredicateProposalClient` directly (a thin Java CLI/JShell entry is sufficient) or run CPAchecker replay. Do not create Python/curl HTTP clients: they change headers and transport behavior, bypass Java request construction/retry/cache semantics, and are not production-equivalent. Issue #124's Python `urllib` probe was invalid; `api.commandcode.ai` Cloudflare rejected its default User-Agent with HTTP 403, while the same Java client and route succeeded.
- **Transient LLM failures:** `PredicateProposalClient` retries network/429/5xx failures twice by default, with nonnegative values capped at 10 attempts and 60 seconds per backoff delay; other 4xx responses fail immediately.
- **LLM responses are streamed (issue #128, since 2026-08-20).** The production Java client uses OpenAI-compatible SSE, separately accumulates `reasoning_content` and final `content`, and records final usage. Its 30-second timeout covers connection establishment only; inference has no application-level total deadline. Once a 200 stream begins, malformed or interrupted output fails closed without retrying the partial generation.
- **Class-A first:** Any new property category should attempt config-only generalization (Class-A) before touching Java. v1.6 overflow proved this works for predicate-CEGAR-based branches.
- **No `grep` into `cpachecker-experiments/records/archive/`.** Use `rg` (respects `.gitignore`, which excludes `cpachecker-experiments/records/archive/`) or always pass `--exclude-dir=archive`.
- **DeepSeek V4 (non-thinking) as primary model.** Thinking mode not used in production path; see `llm/LLM_API.md` for rationale.
- **L3 not used (noL3).** Validation is L1+L2 only (`vguide.enableL3Entailment=false`). A 2026-06-07 `full_scalar` ablation showed L3-on worse overall (fewer solves, higher PAR-2); all mainline evals since then keep L3 off.
- **Overflow prompt is neutral.** The reachability prompt actively discourages the bound predicates that overflow needs. A dedicated overflow-aware prompt is the main lever for v1.6.1 improvement (P1), not config tweaks.
- **Fleet machines: never trust incremental `ant build` after syncing code.** NFS
  mtime skew makes ant's up-to-date checks unreliable — a stale `classes/` (from a
  previous agent's build of different source) silently survives and crashes at
  runtime with `NoSuchMethodError`. Always `ant clean` before `ant build` when the
  code changes on a fleet machine. A full build takes ~1m30s; anything much faster
  means nothing was recompiled. Output goes to `~/cpachecker/classes/` (the
  `bin/cpachecker` launcher classpath), not `build/classes`. Symptom seen
  2026-08-12: augmented arm crashed 167/224 with
  `NoSuchMethodError: VGuideOptions.isShadowPredicateUtilityGateEnabled()`.
