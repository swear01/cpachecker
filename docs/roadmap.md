# Roadmap

See `docs/vguided-cegar/LLM_RESEARCH_ROADMAP.md` for the full long-horizon map.

## Active

- **Predicate usefulness gating**：final PDR/KI-PDR oracle matrix已all zero而STOP。Fixed first-call signature已fresh回收7/7 losses、保留2/2 wins、0 wrong；下一步只做threshold-frozen held-out/full764，不再調rule。

## Backlog

- ~~A2 CPU-budget isolation~~ — **rejected 2026-06-20**: the parallel race is the standard portfolio mechanism (not broken, 0-wrong unaffected); capping VGuide's CPU would also cut the +18 wins it earns by spending that CPU (same coin), and the −7 is run-to-run resource noise. Low ROI. See `REACHSAFETY_IMPROVEMENT_PLAN.md` §3.2/§6.
- **Termination ranking hook — 300s competition-grade confirmation** + higher per-loop cap / ensemble. The hook itself is **implemented and validated** (see Recently Done); this is the follow-up to strengthen the number, mirroring overflow P2.
- **v2.1: Termination ranking hook — earlier injection point (the expensive headroom)** — 2026-06-18 diagnosis (`TERMINATION_RANKING_HOOK_PLAN.md` §13): on a 56-target subset the hook only *fired* on 9; **40/56 are pointer/array/string loops where the lasso safety analysis gives up before producing a lasso**, so the current hook (which sits after `checkTermination` returns unknown) is never reached. Winning these needs a structurally earlier injection (before lasso construction / at the safety-analysis counterexample stage) or pointer/array handling. Class-B+, not a prompt tweak. This is where the real headroom is.
- **MemSafety / DataRace probes** — check if predicate-CEGAR fires; if yes, Class-A config generalization. See `LLM_RESEARCH_ROADMAP.md §3.1`.
- **FALSE path / witness generation** — LLM for counterexample witness hints (Tier S). Long horizon.
- **Offline corpus learning** — pre-compute predicate libraries per program class. Exploratory.
- **svcomp27 full integration** — packaging VGuide into the competition submission.

## Current Order

1. Fresh loss7 runtime確認multiplicative short-peel gate。
2. 以預先固定rule做跨schedule/family holdout，不再調threshold。
3. Gate至少消除50%已知 injection losses，且 net勝固定 `peel=0`，才跑完整764。
4. 其他 branch/hook 全部 defer，避免同時開多條高成本研究線。

## Recently Done

- **Ordinary + final PDR/KI-PDR oracle-capacity — STOP** — exact-BV/MathSAT、exact NIA/Z3、per-location conjunction、KI-PDR與direct PDR oracle arms全部0/12 delta；0 wrong。Reports `reports/2026-07-11_nla_oracle_capacity_smoke.md`、`reports/2026-07-11_pdr_oracle_capacity_matrix.md`。（2026-07-11）
- **ReachSafety LLM-improvement exploration — PAUSED at v1.7.1 (+22 / 0 wrong, 504/764)** — cheap LLM-on-predicate levers exhausted. Investigated & deferred/rejected: A2 CPU isolation (rejected), nla-digbench nonlinear (out of mechanism scope, ~70% of remaining UNKNOWN), peel-aware prompt (low confidence), FALSE/bug-finding (v1.5 wrong-artifact; SOTA = LLM-directed fuzzing but CPAchecker has no fuzzer). Further gains need a new capability (nonlinear / new injection point / execution-based bug-finding), all high-cost. Summary: `reports/2026-06-20_reachsafety_exploration_summary.md`. (2026-06-20)
- **v1.7.1 ReachSafety peel trigger — IMPLEMENTED + validated; +11 over v1.7.0, 0 wrong** — fire the LLM early (refinement #2+) when the CE unrolls a loop (loop-head visits ≥ `vguide.peelLoopHeadThreshold`=4), recovering v1.7.0's #1-need regressions (`heapsort`/`nested9`/`iftelse`/`sumt4`). `countLoopHeadVisits` in the bridge + `peelFire` OR-branch in the scheduler. Full 764 `svcomp27-vguide` (only peel threshold differs 0→4): 493 → **504 (+11 = +18 new − 7 lost), 0 wrong**; cumulative **+22 vs old schedule (482→504)**. Unit tests 12/12. Report `reports/2026-06-20_reachsafety_peel_trigger.md`. (2026-06-20)
- **v1.7.0 ReachSafety stock-first schedule — IMPLEMENTED + validated; +11 net, 0 wrong** — new `every_n_or_interval` LLM-call schedule (fire only when stock is not converging: every-N refinements never at #1, **OR** every D=15s wall-clock; Tier R). Realizes portfolio plan P1 (stock-first guard). Full 764 both-arm `svcomp27-vguide` (only schedule differs): 482 → **493 (+11 = +17 new − 6 lost), 0 wrong**. Now default in `config/vguide.properties`; unit tests 8/8. The 6 regressions (`heapsort`/`nested9` — direct-LLM-#1 wins) motivate the peel-based trigger ① follow-up. Report `reports/2026-06-20_reachsafety_stockfirst_guard.md`. (2026-06-20)
- **v2.0 Termination ranking-function hook — IMPLEMENTED + validated; small sound gain, cheap levers exhausted** — Class-B Java hook in the lasso route: LLM proposes ranking functions (+ optional supporting invariant), verified by a decrease+bounded SMT check (Tier S). termination_scalar 146: stock 80 → **vguide 84 @300s (+4 / 0 lost / 0 wrong)** (60s: +3). New code under `core/algorithm/termination/lasso_analysis/vguide/`, 14 unit tests. **Verdict (2026-06-18): small ceiling** — cheap candidate-quality levers (prompt/repair/stem-context) all exhausted (≤ baseline); 40/56 targets never produce a lasso (pointer/array/string, structurally out of reach); competition-net ≤ isolated and not measured (terminationToSafety ∥ lasso, terminationToSafety has no AI path). Higher-impact LLM interventions lie elsewhere. Report: `reports/2026-06-17_termination_ranking_hook.md`; plan §13–15. (2026-06-17/18)
- **消融實驗 source-prior 完成** — 4 組（base+svcomp26 × loops+overflow）順序跑；CE context 對 base config 至關重要（source_prior≈stock=225），svcomp26 portfolio 差距微小（loops −7、overflow −1），0 wrong；報告：`reports/2026-06-17_source_prior_ablation.md` (2026-06-17)
- **消融實驗 source-prior 實作** — `vguide.sourcePriorMode`、`ContextPackBuilder.buildSourceOnly()`、`PredicateCPA.registerPreCegarBridge()`、4 個實驗 config；`run.sh` 加 4 個 source-prior mode (2026-06-16)
- v1.6: Overflow Class-A generalization — `svcomp26-vguide` now routes overflow through VGuide; +6 solved, 0 wrong (2026-06-15)
- v1.6 termination probe: RED (Class-B confirmed; tabled for v2.0) (2026-06-13)
- v1.5.1: Loops + full_scalar on svcomp26-vguide; 16 direct LLM predicate wins (2026-06-14)
- v1.5: Broad Loops set +37 vs stock (2026-06-13)
- Unified VGuide architecture: replaced all B2/B4/B5 sidecar designs with single Java path
