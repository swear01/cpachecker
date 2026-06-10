# 實驗：v1.4 dual prompt + ce_summary

**狀態**：**已跑**（2026-06-10）  
**設計**：[analysis/DUAL_PROMPT_V1_PLAN.md](../analysis/DUAL_PROMPT_V1_PLAN.md)  
**完整報告**：[reports/2026-06-10_dual_prompt_v1_noL3.md](../reports/2026-06-10_dual_prompt_v1_noL3.md)

## Config

`config/vguide-experiment-dual-prompt-v1.properties`（dual + freq20/n12 + adaptive + noL3）

## Run

| 項目 | 值 |
|------|-----|
| 集合 | `full_scalar`（217） |
| 目錄 | `output/vguide/experiments/full_scalar_dual_v1_20260610/` |
| Commit | `85706b4bf0` |

## 結果摘要

| 指標 | stock | v1.3 adaptive | v1.4 dual |
|------|-------|---------------|-----------|
| 解出 (T+F) | 116 | 150 | **155** |
| FALSE | 40 | 40 | **38** |
| PAR-2 avg | 283s | 192s | **183s** |

## 驗收（§6）

| 項目 | 目標 | 結果 |
|------|------|------|
| FALSE +≥2 | ✓ | **失敗**（−2，0 新 FALSE） |
| 總解出 / PAR-2 | 改善 | **達成** |
| `regression_false_unknown` | 子集 | **未跑** |
| `const_1-2` | 進度 | **未單獨跑** |

## 結論

**FALSE 導向目標失敗**；SAFE 向 invariant 證明大幅受益。下一階段應在 FALSE 子集 + 非 spurious 觸發上迭代，見報告 §3–§4。
