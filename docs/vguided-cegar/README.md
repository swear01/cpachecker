# VGuide（Unified）

**單一路徑、全 Java。** 設計見 [architecture/UNIFIED_VGUIDE_ARCHITECTURE.md](architecture/UNIFIED_VGUIDE_ARCHITECTURE.md)。

## 快速入口

| 文件 | 用途 |
|------|------|
| [RUN_EXPERIMENTS.md](RUN_EXPERIMENTS.md) | **`run.sh` 怎麼跑**；批次後 PAR-2 / cactus |
| [reports/README.md](reports/README.md) | 進度報告 |
| [reports/2026-06-15_svcomp26_overflow_vguide.md](reports/2026-06-15_svcomp26_overflow_vguide.md) | **v1.6 Class-A 泛化（✓）**：NoOverflow 452 題，320 solved vs stock 314（**+6 / 0 lost / 0 wrong**），6 全 direct LLM win；零 Java/prompt |
| [reports/2026-06-14_svcomp26_vguide_loops.md](reports/2026-06-14_svcomp26_vguide_loops.md) | **v1.5.1 svcomp26-vguide**：Loops 764 題，493 solved vs svcomp26 486（+7），0 wrong，16 direct LLM predicate wins |
| [reports/2026-06-13_v1.5_loops_reachsafety_unreach.md](reports/2026-06-13_v1.5_loops_reachsafety_unreach.md) | **v1.5 實測結果**：Loops broad set 764 題，VGuide +37 vs stock，33 VGuide-only TRUE solves |
| [reports/2026-06-10_freq10_n24_adaptive_noL3.md](reports/2026-06-10_freq10_n24_adaptive_noL3.md) | **v1.3 noL3**：150 solved、PAR-2 192s（adaptive + freq10/n24） |
| [SVCOMP26_VGUIDE_FULLSET_PLAN.md](SVCOMP26_VGUIDE_FULLSET_PLAN.md) | **svcomp26-vguide** full-set 計劃與完成狀態（v1.5.1） |
| [SVCOMP26_PORTFOLIO_LLM_PLAN.md](SVCOMP26_PORTFOLIO_LLM_PLAN.md) | **v1.5.2+**：把 LLM 從 PredicateCPA 擴展到 svcomp26 portfolio strategy（routing / budget / guards / hints） |
| [LLM_RESEARCH_ROADMAP.md](LLM_RESEARCH_ROADMAP.md) | **v1.6 → v2.0 → exploratory**：長 horizon 廣域地圖——跨 property category（Termination / MemSafety / Overflow…）、跨 CPA domain、FALSE/witness、離線 corpus 學習；含 S/R/X soundness 守則與 hook-inheritance 分級 |
| [SVCOMP26_OVERFLOW_VGUIDE_PLAN.md](SVCOMP26_OVERFLOW_VGUIDE_PLAN.md) | **v1.6（✓ 完成）**：把 reachability 的 predicate-CEGAR hook 泛化到 NoOverflow branch（Class-A、config-only、零 Java）——+6/0 lost/0 wrong |
| [SVCOMP26_OVERFLOW_VGUIDE_IMPROVEMENT_PLAN.md](SVCOMP26_OVERFLOW_VGUIDE_IMPROVEMENT_PLAN.md) | **v1.6.1 提升計劃**：91 fired/37 fired-but-UNKNOWN；發現 reachability prompt 主動勸退 overflow 需要的 bound predicate → P1 overflow-aware prompt 是最大 lever（P0 config 排除法、P2 300s 確認）|
| [SVCOMP26_TERMINATION_VGUIDE_PROBE.md](SVCOMP26_TERMINATION_VGUIDE_PROBE.md) | **probe RED → Class-B**：termination safety-路 feasibility probe 否決——引擎是 `TerminationToReachCPA` 非 predicate-CEGAR，強接 CEGAR 仍 0 refinement，VGuide 無從 fire；termination 留 v2.0 ranking-function Java hook |
| [SVCOMP_INTEGRATION_PLAN.md](SVCOMP_INTEGRATION_PLAN.md) | **svcomp27** × VGuide v1.5 整合計劃 |

## 現行目錄

```
docs/vguided-cegar/
├── RUN_EXPERIMENTS.md
├── LOCAL_DEVELOPMENT_ENV.md
├── SVCOMP_INTEGRATION_PLAN.md
├── SVCOMP26_VGUIDE_FULLSET_PLAN.md
├── SVCOMP26_PORTFOLIO_LLM_PLAN.md
├── LLM_RESEARCH_ROADMAP.md
├── SVCOMP26_OVERFLOW_VGUIDE_PLAN.md   # v1.6 ✓ 完成
├── SVCOMP26_OVERFLOW_VGUIDE_IMPROVEMENT_PLAN.md   # v1.6.1 提升計劃
├── SVCOMP26_TERMINATION_VGUIDE_PROBE.md   # v1.6 probe RED
├── architecture/UNIFIED_VGUIDE_ARCHITECTURE.md
├── llm/                    # 排程、ensemble、predicate budget、API
├── analysis/               # 已完成/歷史計劃與方法記錄
├── experiments/            # 已完成的單次實驗規格
├── evaluation/             # benchmark 定義、frozen replay
├── reports/                # 進度報告
├── benchmark_sets/         # manifest（run.sh 讀取）
└── predicate_sets/         # Exception 用凍結謂詞
```

### llm/

| 文件 | 用途 |
|------|------|
| [llm/LLM_API.md](llm/LLM_API.md) | **DeepSeek V4** 模型、thinking / non-thinking、環境變數 |
| [llm/LLM_CALL_SCHEDULING.md](llm/LLM_CALL_SCHEDULING.md) | `min_interval` / `every_n` 排程 |
| [llm/LLM_ENSEMBLE.md](llm/LLM_ENSEMBLE.md) | 雙 prompt（SAFE+BUG）與每軌 ensemble（v1.4） |
| [llm/PREDICATE_BUDGET.md](llm/PREDICATE_BUDGET.md) | **單輪多條** predicate 數量與品質 |
| [llm/OFFLINE_SAMPLING.md](llm/OFFLINE_SAMPLING.md) | `test_llm_proposal_quality.py` vs CPA 內 LLM |

### evaluation/

| 文件 | 用途 |
|------|------|
| [evaluation/STANDARD_BENCHMARK_SUITE.md](evaluation/STANDARD_BENCHMARK_SUITE.md) | sample(8) + full_scalar(217) |
| [benchmark_sets/README.md](benchmark_sets/README.md) | manifest 與排除說明 |
| [evaluation/FROZEN_PREDICATES.md](evaluation/FROZEN_PREDICATES.md) | NO_SPURIOUS Exception、replay |

## 已完成/歷史計劃

`analysis/`、`experiments/` 與部分 `llm/*PLAN.md` 保留已完成的設計與實驗規格，
現行 claim 與重跑入口以上方報告、`RUN_EXPERIMENTS.md`、`SVCOMP26_VGUIDE_FULLSET_PLAN.md` 為準。
搜尋目前架構時優先看 `architecture/`、`llm/` 的現行說明與 `reports/2026-06-14_svcomp26_vguide_loops.md`。
