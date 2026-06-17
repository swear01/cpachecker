# Plan

## In Progress

- **v1.6.1 overflow prompt improvement** (`SVCOMP26_OVERFLOW_VGUIDE_IMPROVEMENT_PLAN.md`): 91 fired / 37 fired-but-UNKNOWN on overflow; reachability prompt actively discourages bound predicates. P0 config elimination done (neutral). P1 = overflow-aware prompt (main lever, A/B result: neutral — cheap levers exhausted). Status: evaluating next steps.
- **svcomp-integration branch**: VGuide v1.5 integration into svcomp27 competition submission (`SVCOMP_INTEGRATION_PLAN.md`).

## Next Up

- v1.6.1: decide whether to pursue overflow-aware prompt further or move to next property category
- **v1.5.2+ portfolio LLM** (`SVCOMP26_PORTFOLIO_LLM_PLAN.md`): extend LLM from predicate injection to portfolio routing / budget / guards / hints (layers A–G) — still within reachability branch
- **Next Class-A target**: MemSafety or DataRace branches (predicate-CEGAR based?) — probe feasibility per `LLM_RESEARCH_ROADMAP.md`

## Reference: Completed Milestones

| Version / Task | Result |
|----------------|--------|
| **IEEE preprint** | 8-page IEEEtran journal paper; `paper/` directory; all results + ablation + related work |
| **消融實驗 source-prior** | CE context 必要（source_prior=stock=225，first_spurious +37）；0 wrong；報告 `reports/2026-06-17_source_prior_ablation.md` |
| v1.6 | Overflow Class-A: 363 solved vs stock 357 (+6 / 0 lost / 0 wrong) |
| v1.5.1 | svcomp26-vguide Loops: 493 solved vs stock 486 (+7, 0 wrong, 16 direct LLM wins) |
| v1.5 | Loops broad set: +37 vs stock, 33 VGuide-only TRUE solves |
| v1.3 | noL3: 150 solved, PAR-2 192s (adaptive + freq10/n24) |
