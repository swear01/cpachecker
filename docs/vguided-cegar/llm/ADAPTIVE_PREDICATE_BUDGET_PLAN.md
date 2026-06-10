# 計劃：自適應 Predicate 數量 + LLM 呼叫頻率（non-thinking 主線）

**狀態**：已實作並完成 217 題（20260610）→ **結果** [reports/2026-06-10_freq10_n24_adaptive_noL3.md](../reports/2026-06-10_freq10_n24_adaptive_noL3.md)；規格見 [experiments/2026-06-10_freq10_n24_adaptive_budget.md](../experiments/2026-06-10_freq10_n24_adaptive_budget.md)  
**動機**：notthinking 品質檢查顯示 overlap Novel% 與 thinking 相近，但 **每 call 少 ~3 條**（median 4 vs 7），總解題少 ~14 題。  
**優先於**：CE prompt（見 [CE_CONTEXT_PROMPT_PLAN.md](../analysis/CE_CONTEXT_PROMPT_PLAN.md)）可並行，但 **調數量/頻率成本低、可先試**。

---

## 1. 現況（config 預設）

| 參數 | 值 | 含義 |
|------|-----|------|
| `minPredicatesPerCall` | 3 | prompt 軟下限 |
| `maxPredicatesPerCall` | 6 | parse 硬上限 |
| `llmCallSchedule` | `every_n_and_interval` | 兩條件都滿足才呼叫 |
| `llmEveryNSpuriousRefinements` | **72** | 第 1、73、145… 次 spurious |
| `llmMinIntervalSec` | **15** | 距上次 LLM ≥15s |
| `maxLlmRoundsPerAnalysis` | **5** | 整場最多 5 輪 LLM |

**notthinking 217 題實測**

- 總 API calls：**234**（190 題有 predicate）
- 每題 LLM calls：median **1**，max **5**；分布 `{0:27, 1:163, 2:18, 3:7, 4:2, 5:20}`
- 27 題從未觸發 LLM（無 spurious 或排程前結束）
- **20 題打滿 5 輪**（如 `odd` 仍 UNKNOWN）

**頻率直覺**：fast 題上 **every_n=72 幾乎只會叫到第 1 輪**；要更多輪靠 **min_interval 每 15s 一次**，但受 `maxLlmRounds=5` 上限。

non-thinking LLM ~2.4s/call → 300s 內 **理論可遠多於 5 次**，現被 `maxLlmRounds` 卡住。

---

## 2. 方向 A：自適應 predicate budget

### 2.1 啟發式（建議 v1）

依 **loop head 數** + **assertion 複雜度** 分檔（在 `VGuideRefinementBridge` 或 `PredicateBudget` factory）：

| 檔位 | S | min | max |
|------|---|-----|-----|
| **low** | ≤3 | 4 | 8 |
| **medium** | 4–6 | **6** | **12** |
| **high** | ≥7 | **8** | **16** |

（分數 `S` 與實驗規格見 [experiments/2026-06-10_freq10_n24_adaptive_budget.md](../experiments/2026-06-10_freq10_n24_adaptive_budget.md)。）

**Prompt 調整**：刪弱「fewer rather than weak fillers」；改 **「必須至少 min 條不同角色；max 內盡量覆蓋 assertion + 跨 loop 耦合」**。

### 2.2 實作要點

- `PredicateBudget.forContext(ContextPack pack)` 回傳 `(min,max)`  
- `ProposalPromptBuilder` 已依 `PredicateBudget` 動態生成 block → 無需改 JSON schema  
- dump `run_manifest` 記錄 `budget_tier`

### 2.3 驗收

Regression 21 題 + 全量 217；對照 notthinking baseline（137 solved）。**217 實測：150 solved**（+13 vs notthinking）。

---

## 3. 方向 B：提高 LLM 呼叫頻率

### 3.1 可調旋鈕

| 旋鈕 | 現值 | 建議實驗 | 效果 |
|------|------|----------|------|
| `llmEveryNSpuriousRefinements` | 72 | **24–36** | 快題上第 2 輪 spurious 更早可觸發 |
| `llmMinIntervalSec` | 15 | **10**（non-thinking 下安全） | 牆鐘允許更密 |
| `maxLlmRoundsPerAnalysis` | 5 | **8** | `odd` 類題可多補幾輪 |

**成本**：234 calls → 粗估 **350–500** API calls（仍 << thinking 的單 call 60s+）。

### 3.2 建議實驗矩陣（2×2）

1. Baseline：現 config + notthinking  
2. **Budget only**：adaptive 5–8  
3. **Freq only**：every_n=36, maxRounds=8, interval=10  
4. **Both**

### 3.3 注意

- `every_n_and_interval`：**兩條都要滿足**；只降 every_n 不夠時檢查 interval  
- 提高頻率需配合 **更好的 later-spurious prompt**（列已注入 predicate、避免重複）

---

## 4. 執行狀態（2026-06-10）

1. ~~Adaptive budget + freq10/n24 + maxRounds 10~~ → **full 217 完成**（150 solved）  
2. ~~Regression 子集~~ → 未單獨跑；smoke sample 8/8 已過  
3. **下一步**：high tier 未觸發、`down` 等仍 UNKNOWN → [CE_CONTEXT_PROMPT_PLAN.md](../analysis/CE_CONTEXT_PROMPT_PLAN.md) 或調 S 分數

---

## 5. 相關

- [PREDICATE_BUDGET.md](PREDICATE_BUDGET.md)  
- [LLM_CALL_SCHEDULING.md](LLM_CALL_SCHEDULING.md)  
- [reports/2026-06-10_freq10_n24_adaptive_noL3.md](../reports/2026-06-10_freq10_n24_adaptive_noL3.md)
- [reports/2026-06-09_notthinking_noL3.md](../reports/2026-06-09_notthinking_noL3.md)
