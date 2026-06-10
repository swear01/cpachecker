# LLM 多抽卡（Ensemble）與雙 prompt（v1.4）

**作者**: r14k41044 黃思維  
**模組**: `VGuideRefinementBridge` + `PredicateProposalClient`  
**計劃**：[DUAL_PROMPT_V1_PLAN.md](../analysis/DUAL_PROMPT_V1_PLAN.md)

> **預設（v1.4）**：`vguide.dualPromptMode=true`，`llmSamplesPerCall=1` → 每 LLM 輪 **SAFE×1 + BUG×1** = **2** HTTP。  
> 單次 API 回應內條數由 [PREDICATE_BUDGET.md](PREDICATE_BUDGET.md) / adaptive tier 建議；**合併層不 cap**（兩軌 union 後全送 validate）。

## 雙 prompt（`dualPromptMode`，預設 true）

| 概念 | 說明 |
|------|------|
| **K** | `llmSamplesPerCall` = **每軌** draw 數（SAFE 軌 K 次 + BUG 軌 K 次） |
| K=1 | SAFE×1 + BUG×1 = **2** HTTP/輪（**含第一次 spurious**，無 #1 特例） |
| K=3 | SAFE×3 + BUG×3 = **6** HTTP/輪 |
| 順序 | SAFE 軌（1 sync + (K−1) parallel）→ BUG 軌（同上）；**不** SAFE∥BUG |
| 合併 | SAFE 與 BUG 的 predicates **直接 union + dedupe**，**不** `capOrdered` |
| Repair | **任一站軌**有 accepted → 不修；兩軌皆空才 1 次 repair |

關閉 dual（`dualPromptMode=false`）：僅 SAFE 軌，行為對照實驗用。

## 單軌 ensemble（每 profile 內）

| 每軌 K | 該軌 API | 平行 |
|--------|----------|------|
| K=1 | 1 sync | 不平行 |
| K=3 | 1 sync + 2 parallel extras | 僅同 profile、同 prompt |

## 參數（`vguide.*`）

| 選項 | v1.4 預設 | 說明 |
|------|-----------|------|
| `dualPromptMode` | **true** | SAFE + BUG 兩軌 |
| `llmSamplesPerCall` | `1` | **每軌** K（非「整輪一共 K」） |
| `llmSampleParallelism` | `4` | 每軌 (K−1) extras 最大併發 |
| `maxLlmRoundsPerAnalysis` | 依實驗 config | 計 **spurious 輪次**，非 HTTP 次數 |
| `wallBudgetSec` | `0` | 0=不限制；&gt;0 時 LLM 牆鐘上限（見下） |

### HTTP 次數公式

```
HTTP_per_round ≈ 2 × K × (dualPromptMode ? 1 : 0.5)   // dual: 2軌；單軌: 1軌
總 HTTP ≈ maxLlmRounds × HTTP_per_round + repair（偶發）
```

例：`maxLlmRounds=10`、`K=1`、dual → 約 **20** HTTP（不含 repair）。

### `wallBudgetSec`

可選整題 LLM 牆鐘（秒）。**預設 0 = 不啟用**。啟用時每次 API latency 累加；剩餘 &lt;15s 跳過 LLM。與 API 次數無關，除非手動設了上限。

### `maxLlmRounds` 語意

- **計 1**：排程允許的一次「spurious → VGuide LLM 流程」。
- **不計**：該輪內 2K 次 HTTP 與 repair。

## Log 範例（dual, K=1）

```
VGuide LLM round #1 spurious #1 profiles=SAFE+BUG samples_per_profile=1 api=2 ... latencyMs=...
```

## 多 draw / 雙軌合併與正確性

候選只進 **precision**；SAFE/BUG union 不 cap **不影響 soundness**，可能增加注入條數、略增 refinement 開銷。

## 與排程的關係

`every_n` / `min_interval` 決定 **哪幾個 spurious 輪** 叫 LLM；ensemble 與 dual 只影響 **該輪內** API 次數。見 [LLM_CALL_SCHEDULING.md](LLM_CALL_SCHEDULING.md)。
