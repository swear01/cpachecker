# VGuide 進度報告

## 現行（deepseek-v4-pro）

| 報告 | 說明 |
|------|------|
| **[`../analysis/V1_5_LOOPS_EXPLORATORY_PLAN.md`](../analysis/V1_5_LOOPS_EXPLORATORY_PLAN.md)** | **v1.5 計劃 + 實測摘要**：SV-COMP Loops exploratory evaluation（broad set 已完成；clean/applicable tier 分析待補） |
| **[`2026-06-13_v1.5_loops_reachsafety_unreach.md`](2026-06-13_v1.5_loops_reachsafety_unreach.md)** | **v1.5 實測結果**：SV-COMP Loops `unreach-call` 764 題；stock 225 solved、v1.4 262（+37）、`--svcomp26` 486；VGuide-only 33 TRUE |
| **[`2026-06-13_svcomp27_vguide_integration.md`](2026-06-13_svcomp27_vguide_integration.md)** | **SV-COMP config integration**：`svcomp27-vguide` scoped configs、BAM fallback、process LLM cap、runner mode 與 smoke-test evidence |
| **[`2026-06-13_svcomp27_pilot_calibration.md`](2026-06-13_svcomp27_pilot_calibration.md)** | **SV-COMP full-set readiness**：sample regression、portfolio verdict attribution、20-task 900s pilot calibration、`svcomp27-stock` 對照模式與 full-set nohup launcher |
| **[`2026-06-11_advisor_meeting_post_0604.md`](2026-06-11_advisor_meeting_post_0604.md)** | **Advisor meeting 整合報告**（6/4 → 6/11，8 天）：v1.0 → v1.4 全時間軸、機制分析、FALSE 失敗歸因、v1.5 方向 |
| **[`2026-06-10_dual_prompt_v1_noL3.md`](2026-06-10_dual_prompt_v1_noL3.md)** | **v1.4** dual SAFE/BUG + ce_summary：**155 solved**、PAR-2 **183s**；**FALSE 目標失敗**（38 vs stock 40） |
| **[`2026-06-07_vguide-report_deepseek-v4-pro.md`](2026-06-07_vguide-report_deepseek-v4-pro.md)** | 歷史總覽：217 題 `full_scalar`；L3-on **131**/217；noL3 vs stock；L3 消融 |
| **[`2026-06-08_predicate-analysis_noL3.md`](2026-06-08_predicate-analysis_noL3.md)** | **Predicate 分析**（noL3 dump）：context budget / **Z3 overlap** / 排程；33 rescued vs stock |
| **[`2026-06-10_freq10_n24_adaptive_noL3.md`](2026-06-10_freq10_n24_adaptive_noL3.md)** | **v1.3.0** adaptive + freq10/n24：**150 solved**、PAR-2 **192s** |
| **[`2026-06-09_notthinking_noL3.md`](2026-06-09_notthinking_noL3.md)** | **thinking disabled** 217 題：+21 vs stock、PAR-2 vs budget306/v1.0.0、overlap Phase D |

設計文件：[experiments/2026-06-10_dual_prompt_v1.md](../experiments/2026-06-10_dual_prompt_v1.md)、[analysis/DUAL_PROMPT_V1_PLAN.md](../analysis/DUAL_PROMPT_V1_PLAN.md)

**實驗目錄**

| Run | 路徑 |
|-----|------|
| Stock baseline | `output/vguide/experiments/full_scalar_stock/` |
| VGuide L3-on | `output/vguide/experiments/full_scalar_vguide/` |
| VGuide noL3 | `output/vguide/experiments/full_scalar_vguide_noL3/` |
| **noL3 分析重跑**（instrumentation） | `output/vguide/experiments/full_scalar_vguide_noL3_analysis/` |
| **Analysis dump + CSV** | `output/vguide/analysis_dumps/full_scalar_noL3_20260608/` |
| **noL3 notthinking**（d7021692） | `output/vguide/experiments/full_scalar_vguide_noL3_notthinking_20260609/` |
| **notthinking dump** | `output/vguide/analysis_dumps/full_scalar_noL3_notthinking_20260609/` |
| **adaptive freq10_n24**（fd69f395） | `output/vguide/experiments/full_scalar_vguide_noL3_freq10_n24_adaptive_20260610/` |
| **adaptive dump** | `output/vguide/analysis_dumps/full_scalar_noL3_freq10_n24_adaptive_20260610/` |
| **dual v1.4**（85706b4） | `output/vguide/experiments/full_scalar_dual_v1_20260610/` |
| 三向 CSV | `output/vguide/experiments/l3_ablation_comparison.csv` |

**Predicate 離線分析（Phase D）**

```bash
# 現行 adaptive run（20260610）
python3 scripts/vguided-cegar/analyze_predicate_study.py \
  --dump-dir output/vguide/analysis_dumps/full_scalar_noL3_freq10_n24_adaptive_20260610 \
  --logs-dir output/vguide/experiments/full_scalar_vguide_noL3_freq10_n24_adaptive_20260610/logs \
  --stock-logs output/vguide/experiments/full_scalar_stock/logs \
  --out output/vguide/analysis_dumps/full_scalar_noL3_freq10_n24_adaptive_20260610/analysis

# 歷史 v1.0.0 thinking dump（20260608）
python3 scripts/vguided-cegar/analyze_predicate_study.py --skip-validate \
  --dump-dir output/vguide/analysis_dumps/full_scalar_noL3_20260608 \
  --logs-dir output/vguide/experiments/full_scalar_vguide_noL3_analysis/logs \
  --stock-logs output/vguide/experiments/full_scalar_stock/logs
```

方法與計劃：[analysis/PREDICATE_ANALYSIS_PLAN.md](../analysis/PREDICATE_ANALYSIS_PLAN.md) · [analysis/OVERLAP_AND_PCS.md](../analysis/OVERLAP_AND_PCS.md)

**注意**：2026-06-08 analysis dump 使用 **`llmSamplesPerCall=1`**、prompt 建議 **4–8** 條 predicate（見 [LLM_ENSEMBLE.md](../llm/LLM_ENSEMBLE.md)）。實驗 dump 在 `output/`（gitignore），報告與離線 CSV 路徑見各報告 §產物。

**一鍵重跑 PAR-2 / cactus**

```bash
./scripts/vguided-cegar/post_batch_analysis.sh \
  --vguide-out output/vguide/experiments/full_scalar_vguide \
  --stock-out  output/vguide/experiments/full_scalar_stock \
  --set full_scalar --timelimit 300
```

**重跑不完整 L3-on log（8 題）**

```bash
./scripts/vguided-cegar/run.sh cpa \
  --set incomplete_l3on_rerun --ablation l3 --parallel 4 --timelimit 300 \
  --out output/vguide/experiments/full_scalar_vguide
```

## 歷史

| 檔案 | 說明 |
|------|------|
| [`archive/vguided-docs/reports/2026-06-04_vguide-report_deepseek-chat_HISTORICAL.md`](../../../archive/vguided-docs/reports/2026-06-04_vguide-report_deepseek-chat_HISTORICAL.md) | 2026-06-04 advisor 快照（**deepseek-chat**，11↑/205=/1↓） |
