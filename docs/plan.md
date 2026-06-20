# Plan

## In Progress

- **v1.6.1 overflow prompt improvement** (`SVCOMP26_OVERFLOW_VGUIDE_IMPROVEMENT_PLAN.md`): 91 fired / 37 fired-but-UNKNOWN on overflow; reachability prompt actively discourages bound predicates. P0 config elimination done (neutral). P1 = overflow-aware prompt (main lever, A/B result: neutral — cheap levers exhausted). Status: evaluating next steps.
- **svcomp-integration branch**: VGuide v1.5 integration into svcomp27 competition submission (`SVCOMP_INTEGRATION_PLAN.md`).

## Recently Done

- **ReachSafety LLM-improvement exploration — PAUSED at v1.7.1 (+22 / 0 wrong; 504/764)** (summary `reports/2026-06-20_reachsafety_exploration_summary.md`): cheap LLM-on-predicate levers exhausted. Investigated & **deferred/rejected**: A2 CPU isolation (rejected — race is standard, capping cuts the +18 wins), nla-digbench nonlinear (out of mechanism scope — ~70% of remaining UNKNOWN, needs nonlinear synthesis), peel-aware prompt (low confidence — fired-but-failed at quality ceiling), FALSE/bug-finding (v1.5 used wrong artifact; SOTA = LLM-directed fuzzing, but CPAchecker has no fuzzer). Further gains need a **new capability** (nonlinear / new injection point / execution-based bug-finding), all high-cost. (2026-06-20)
- **v1.7.1 ReachSafety peel trigger — DONE; +11 over v1.7.0, 0 wrong** (`vguided-cegar/REACHSAFETY_IMPROVEMENT_PLAN.md` A1.2, report `reports/2026-06-20_reachsafety_peel_trigger.md`): fire the LLM early (refinement #2+) when the CE unrolls a loop (loop-head visits ≥ 4) instead of waiting for #10 / 15s. Recovers v1.7.0's #1-need regressions (`heapsort`, `nested9`, `iftelse`, `sumt4`) + nla-digbench nonlinear. Full 764 `svcomp27-vguide`, only peel threshold differs (0→4): 493 → **504 (+11 = +18 new − 7 lost), 0 wrong, 0 flips**. Cumulative vs old fire-at-#1 schedule **+22 (482→504)**. Default `vguide.peelLoopHeadThreshold=4`; unit tests 12/12. (2026-06-20)
- **v1.7.0 ReachSafety stock-first schedule — DONE; +11 net, 0 wrong** (`vguided-cegar/REACHSAFETY_IMPROVEMENT_PLAN.md` A1, report `reports/2026-06-20_reachsafety_stockfirst_guard.md`): new `every_n_or_interval` LLM-call schedule fires only when stock is not converging — every-N refinements (never #1) **OR** every D=15s wall-clock — realizing portfolio plan P1 (stock-first guard). Full 764 both-arm `svcomp27-vguide` (only schedule differs): 482 → **493 (+11 = +17 new − 6 lost), 0 wrong, 0 flips**. 6 regressions are case-study direct-LLM-#1 wins (`heapsort`, `nested9`) → motivates the peel-based trigger ① (next). Now default in `config/vguide.properties`; unit tests 8/8. (2026-06-20)
- **v2.0 Termination ranking-function hook — DONE; small sound gain, verdict = small ceiling** (`vguided-cegar/TERMINATION_RANKING_HOOK_PLAN.md` §13–15, report `reports/2026-06-17_termination_ranking_hook.md`): LLM proposes ranking functions on loops where LassoRanker templates fail; each verified by a decrease+bounded SMT check (Tier S); env-gated lasso-route hook; 14 unit tests. termination_scalar 146: stock 80 → **vguide 84 @300s (+4 / 0 lost / 0 wrong)** (60s +3). **Cheap candidate-quality levers exhausted** (prompt/repair/stem-context all ≤ baseline); 40/56 targets never produce a lasso (pointer/array/string, structurally out of reach); competition-net ≤ isolated and not measured (terminationToSafety has no AI path, runs stock in parallel). Hook kept as sound opt-in building block, not a headline result.

## Next Up

- **Higher-impact LLM intervention point (open question)** — the termination ranking hook has a small ceiling. The next LLM-intervention effort should target a higher-leverage point: the structural earlier-injection that would reach the 40 never-fired (pointer/array/string) loops, or a different category/mechanism altogether. See `LLM_RESEARCH_ROADMAP.md`.
- v1.6.1: cheap levers exhausted (config +1, prompt +0); deferred — see `SVCOMP26_OVERFLOW_VGUIDE_IMPROVEMENT_PLAN.md` §8
- **v1.5.2+ portfolio LLM** (`SVCOMP26_PORTFOLIO_LLM_PLAN.md`): guards layer **DONE** (v1.7.0 stock-first + v1.7.1 peel, +22/0 wrong). **ReachSafety LLM-on-predicate line PAUSED at v1.7.1** (cheap levers exhausted — see exploration summary). adaptive budget / SAFE-only / routing (layers A–G) still open but lower priority; further gains need new capability not prompt/schedule tuning.
- **Next Class-A target**: MemSafety or DataRace branches (predicate-CEGAR based?) — probe feasibility per `LLM_RESEARCH_ROADMAP.md`

## Reference: Completed Milestones

| Version / Task | Result |
|----------------|--------|
| **FM 期末報告 (LNCS)** | `report/` LNCS 論文（llncs.cls）;**草稿、尚未投稿**,持續修訂(已納入 v1.7.x schedule 結果);Zenodo artifact DOI `10.5281/zenodo.20745141` |
| **消融實驗 source-prior** | CE context 必要（source_prior=stock=225，first_spurious +37）；0 wrong；報告 `reports/2026-06-17_source_prior_ablation.md` |
| v1.6 | Overflow Class-A: 363 solved vs stock 357 (+6 / 0 lost / 0 wrong) |
| v1.7.1 | ReachSafety peel trigger (early divergence firing, loop-head visits ≥ 4): full 764 svcomp27-vguide 493 → 504 (**+11** = +18 new − 7 lost / 0 wrong); cumulative **+22** vs old schedule |
| v1.7.0 | ReachSafety stock-first schedule (`every_n_or_interval`): full 764 svcomp27-vguide 482 → 493 (**+11** = +17 new − 6 lost / 0 wrong); realizes portfolio plan P1 |
| v1.5.1 | svcomp26-vguide Loops: 493 solved vs stock 486 (+7, 0 wrong, 16 direct LLM wins) |
| v1.5 | Loops broad set: +37 vs stock, 33 VGuide-only TRUE solves |
| v1.3 | noL3: 150 solved, PAR-2 192s (adaptive + freq10/n24) |
