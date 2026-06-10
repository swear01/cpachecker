# VGuide（Unified）

**單一路徑、全 Java。** 設計見 [architecture/UNIFIED_VGUIDE_ARCHITECTURE.md](architecture/UNIFIED_VGUIDE_ARCHITECTURE.md)。

## 快速入口

| 文件 | 用途 |
|------|------|
| [RUN_EXPERIMENTS.md](RUN_EXPERIMENTS.md) | **`run.sh` 怎麼跑**；批次後 PAR-2 / cactus |
| [reports/README.md](reports/README.md) | 進度報告 |
| [reports/2026-06-10_freq10_n24_adaptive_noL3.md](reports/2026-06-10_freq10_n24_adaptive_noL3.md) | **現行 noL3 最佳**：150 solved、PAR-2 192s（adaptive + freq10/n24） |
| [analysis/PREDICATE_ANALYSIS_PLAN.md](analysis/PREDICATE_ANALYSIS_PLAN.md) | **Predicate 分析計劃**（context / overlap / PCS；token 以 API `usage` 為準） |
| [analysis/FALSE_ORIENTED_VGUIDE_PLAN.md](analysis/FALSE_ORIENTED_VGUIDE_PLAN.md) | **計劃**：面向 FALSE / 找 bug 的 harness 與 prompt |
| [analysis/DUAL_PROMPT_V1_PLAN.md](analysis/DUAL_PROMPT_V1_PLAN.md) | **計劃**：v1.4 雙 prompt + cache + JSON mode |
| [analysis/CE_SUMMARY_COMPRESSION.md](analysis/CE_SUMMARY_COMPRESSION.md) | CE 摘要 **語意壓縮**（loop-head、關係式提取，非 char cap） |
| [analysis/CE_CONTEXT_PROMPT_PLAN.md](analysis/CE_CONTEXT_PROMPT_PLAN.md) | CE 摘要進 prompt（併入 v1.4） |
| [analysis/OVERLAP_AND_PCS.md](analysis/OVERLAP_AND_PCS.md) | Overlap / PCS 語意（Z3 entailment） |
| [reports/2026-06-08_predicate-analysis_noL3.md](reports/2026-06-08_predicate-analysis_noL3.md) | **Predicate 分析結果**（217 題 dump） |
| [LOCAL_DEVELOPMENT_ENV.md](LOCAL_DEVELOPMENT_ENV.md) | `~/sv-benchmarks`、JDK 21、Ant |

## 現行目錄

```
docs/vguided-cegar/
├── RUN_EXPERIMENTS.md
├── LOCAL_DEVELOPMENT_ENV.md
├── architecture/UNIFIED_VGUIDE_ARCHITECTURE.md
├── llm/                    # 排程、ensemble、離線 vs CPA
├── experiments/            # 單次實驗計劃（config 變更、驗收標準）
├── evaluation/             # benchmark 定義、frozen replay
├── reports/                # 進度報告
├── analysis/               # 機制分析計劃（predicate / context / overlap）
├── benchmark_sets/         # manifest（run.sh 讀取）
└── predicate_sets/         # Exception 用凍結謂詞
```

### llm/

| 文件 | 用途 |
|------|------|
| [LLM_API.md](llm/LLM_API.md) | **DeepSeek V4** 模型、thinking / non-thinking、環境變數 |
| [LLM_CALL_SCHEDULING.md](llm/LLM_CALL_SCHEDULING.md) | `min_interval` / `every_n` 排程 |
| [LLM_ENSEMBLE.md](llm/LLM_ENSEMBLE.md) | 雙 prompt（SAFE+BUG）與每軌 ensemble（v1.4 計劃） |
| [PREDICATE_BUDGET.md](llm/PREDICATE_BUDGET.md) | **單輪多條** predicate 數量與品質 |
| [ADAPTIVE_PREDICATE_BUDGET_PLAN.md](llm/ADAPTIVE_PREDICATE_BUDGET_PLAN.md) | 自適應 min/max + LLM 頻率（已實作；217 結果見上報告） |
| [experiments/2026-06-10_freq10_n24_adaptive_budget.md](experiments/2026-06-10_freq10_n24_adaptive_budget.md) | v1.3.0 實驗規格（freq10/n24） |
| [experiments/2026-06-10_freq20_n12_adaptive_budget.md](experiments/2026-06-10_freq20_n12_adaptive_budget.md) | **下一版** every_n=12、max rounds 20 |
| [analysis/case_studies/const_1-2.md](analysis/case_studies/const_1-2.md) | Case study：高 refinement + 打滿 LLM |
| [OFFLINE_SAMPLING.md](llm/OFFLINE_SAMPLING.md) | `test_llm_proposal_quality.py` vs CPA 內 LLM |

### evaluation/

| 文件 | 用途 |
|------|------|
| [STANDARD_BENCHMARK_SUITE.md](evaluation/STANDARD_BENCHMARK_SUITE.md) | sample(8) + full_scalar(217) |
| [benchmark_sets/README.md](benchmark_sets/README.md) | manifest 與排除說明 |
| [FROZEN_PREDICATES.md](evaluation/FROZEN_PREDICATES.md) | NO_SPURIOUS Exception、replay |

## 歷史文件

已移至本機 **`archive/vguided-docs/`**（gitignore）：實作計劃、2026-06-04 報告、case study、NO_SPURIOUS 舊統計、LLM 品質快照等。見 [`archive/vguided-docs/README.md`](../../archive/vguided-docs/README.md)。
