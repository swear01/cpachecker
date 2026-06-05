# VGuide（Unified）

**單一路徑、全 Java。** 設計見 [UNIFIED_VGUIDE_ARCHITECTURE.md](UNIFIED_VGUIDE_ARCHITECTURE.md)。

## 現用文件

| 文件 | 用途 |
|------|------|
| [UNIFIED_VGUIDE_ARCHITECTURE.md](UNIFIED_VGUIDE_ARCHITECTURE.md) | 模組、控制流 |
| [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) | **實作計劃（缺什麼、Phase 0–5）** |
| [STANDARD_BENCHMARK_SUITE.md](STANDARD_BENCHMARK_SUITE.md) | Tier S（8）+ **full_scalar 217** + array-scalar 8 |
| [benchmark_sets/README.md](benchmark_sets/README.md) | manifest 清單與 **11 題排除** 說明 |
| [LLM_CALL_SCHEDULING.md](LLM_CALL_SCHEDULING.md) | 依 LLM/refinement 延遲推導排程 |
| [LLM_ENSEMBLE.md](LLM_ENSEMBLE.md) | 同 spurious 多抽卡（#1 單發 cache，#2+ 平行） |
| [OFFLINE_SAMPLING.md](OFFLINE_SAMPLING.md) | 離線抽樣 vs CPA 內 LLM |
| [NO_SPURIOUS_STATISTICS.md](NO_SPURIOUS_STATISTICS.md) | Legacy 池 / Exception 統計 |
| [FROZEN_PREDICATES.md](FROZEN_PREDICATES.md) | 透明 replay（`predicate_sets/`） |
| [RUN_EXPERIMENTS.md](RUN_EXPERIMENTS.md) | **`run.sh` 怎麼跑**；§6.2 **批次後必跑** PAR-2 / cactus |
| [LOCAL_DEVELOPMENT_ENV.md](LOCAL_DEVELOPMENT_ENV.md) | `~/sv-benchmarks`、JDK 21、Ant、平行預設 |
| [predicate_sets/](predicate_sets/) | 凍結 predicate（Exception 用） |

## 歷史材料

B2 / B4 / B5 / Python sidecar / Record-Replay 已移至 [archive/vguided-legacy/](../../archive/vguided-legacy/README.md)。

Advisor 會議表、case studies、舊實驗 log 同在 archive，**不作新實作依據**。
