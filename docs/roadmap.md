# Roadmap

See `docs/vguided-cegar/LLM_RESEARCH_ROADMAP.md` for the full long-horizon map.

## Backlog

- **v1.5.2 follow-up: peel-based trigger ①** — recover the 6 stock-first regressions (`heapsort`/`nested9`-type, which needed the LLM at refinement #1) by firing early when the refinement sequence is *diverging* (loop-head peel) rather than at a fixed count, plus K/D tuning. See `REACHSAFETY_IMPROVEMENT_PLAN.md` A1.2/A1.5.
- **Termination ranking hook — 300s competition-grade confirmation** + higher per-loop cap / ensemble. The hook itself is **implemented and validated** (see Recently Done); this is the follow-up to strengthen the number, mirroring overflow P2.
- **v2.1: Termination ranking hook — earlier injection point (the expensive headroom)** — 2026-06-18 diagnosis (`TERMINATION_RANKING_HOOK_PLAN.md` §13): on a 56-target subset the hook only *fired* on 9; **40/56 are pointer/array/string loops where the lasso safety analysis gives up before producing a lasso**, so the current hook (which sits after `checkTermination` returns unknown) is never reached. Winning these needs a structurally earlier injection (before lasso construction / at the safety-analysis counterexample stage) or pointer/array handling. Class-B+, not a prompt tweak. This is where the real headroom is.
- **MemSafety / DataRace probes** — check if predicate-CEGAR fires; if yes, Class-A config generalization. See `LLM_RESEARCH_ROADMAP.md §3.1`.
- **FALSE path / witness generation** — LLM for counterexample witness hints (Tier S). Long horizon.
- **Offline corpus learning** — pre-compute predicate libraries per program class. Exploratory.
- **svcomp27 full integration** — packaging VGuide into the competition submission.

## Recently Done

- **v1.5.2 ReachSafety stock-first schedule — IMPLEMENTED + validated; +11 net, 0 wrong** — new `every_n_or_interval` LLM-call schedule (fire only when stock is not converging: every-N refinements never at #1, **OR** every D=15s wall-clock; Tier R). Realizes portfolio plan P1 (stock-first guard). Full 764 both-arm `svcomp27-vguide` (only schedule differs): 482 → **493 (+11 = +17 new − 6 lost), 0 wrong**. Now default in `config/vguide.properties`; unit tests 8/8. The 6 regressions (`heapsort`/`nested9` — direct-LLM-#1 wins) motivate the peel-based trigger ① follow-up. Report `reports/2026-06-20_reachsafety_stockfirst_guard.md`. (2026-06-20)
- **v2.0 Termination ranking-function hook — IMPLEMENTED + validated; small sound gain, cheap levers exhausted** — Class-B Java hook in the lasso route: LLM proposes ranking functions (+ optional supporting invariant), verified by a decrease+bounded SMT check (Tier S). termination_scalar 146: stock 80 → **vguide 84 @300s (+4 / 0 lost / 0 wrong)** (60s: +3). New code under `core/algorithm/termination/lasso_analysis/vguide/`, 14 unit tests. **Verdict (2026-06-18): small ceiling** — cheap candidate-quality levers (prompt/repair/stem-context) all exhausted (≤ baseline); 40/56 targets never produce a lasso (pointer/array/string, structurally out of reach); competition-net ≤ isolated and not measured (terminationToSafety ∥ lasso, terminationToSafety has no AI path). Higher-impact LLM interventions lie elsewhere. Report: `reports/2026-06-17_termination_ranking_hook.md`; plan §13–15. (2026-06-17/18)
- **消融實驗 source-prior 完成** — 4 組（base+svcomp26 × loops+overflow）順序跑；CE context 對 base config 至關重要（source_prior≈stock=225），svcomp26 portfolio 差距微小（loops −7、overflow −1），0 wrong；報告：`reports/2026-06-17_source_prior_ablation.md` (2026-06-17)
- **消融實驗 source-prior 實作** — `vguide.sourcePriorMode`、`ContextPackBuilder.buildSourceOnly()`、`PredicateCPA.registerPreCegarBridge()`、4 個實驗 config；`run.sh` 加 4 個 source-prior mode (2026-06-16)
- v1.6: Overflow Class-A generalization — `svcomp26-vguide` now routes overflow through VGuide; +6 solved, 0 wrong (2026-06-15)
- v1.6 termination probe: RED (Class-B confirmed; tabled for v2.0) (2026-06-13)
- v1.5.1: Loops + full_scalar on svcomp26-vguide; 16 direct LLM predicate wins (2026-06-14)
- v1.5: Broad Loops set +37 vs stock (2026-06-13)
- Unified VGuide architecture: replaced all B2/B4/B5 sidecar designs with single Java path
