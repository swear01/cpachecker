# 單輪多條 Predicate 控制（Predicate Budget）

**模組**：`ProposalPromptBuilder` + `PredicateBudget` + `LlmEnsembleMerger`

## 問題

舊 prompt「4–8 diverse predicates」：

- 模型常往上限靠（分析 batch 中位數 **7** 條 / call）
- 無優先級 → Z3 overlap **45% Redundant**
- 與 `llmSamplesPerCall>1` 是不同維度：前者是 **一次 API 內多條**，後者是 **多次 API**

## 策略（1.0.0 之後）

| 層 | 機制 | 強制？ |
|----|------|--------|
| **Prompt** | `min`–`max` 區間 + **角色分工** + 禁止 padding | 軟性（引導 LLM） |
| **Parse 後** | 單次 API：`PredicateBudget.capOrdered` 截斷至 `max` | **硬性**（保留陣列順序） |
| **雙軌合併（v1.4）** | SAFE∪BUG union **不**再 cap | 見 [DUAL_PROMPT_V1_PLAN.md](../analysis/DUAL_PROMPT_V1_PLAN.md) |
| **驗證** | 既有 L1/L2/L3 pipeline | 硬性 |

### Prompt 語意

1. JSON **陣列順序 = 優先級**（最重要放 index 0）
2. 鼓勵 **不同角色**：loop-carried 關係、assertion 相關跨變數關係、非平凡的 guard bound
3. **不要**為湊滿 `max` 而輸出平凡 bound（如 `i>=0` 在 `for(i=0;...)`）
4. adaptive 模式：prompt 要求 **至少 min、盡量覆蓋** assertion / loop 耦合（見 `ProposalPromptBuilder`）

### 預設

| 選項 | 預設 | 說明 |
|------|------|------|
| `vguide.minPredicatesPerCall` | **3** | prompt 軟下限（aim）；fixed 模式 |
| `vguide.maxPredicatesPerCall` | **6** | prompt 硬上限 + parse 截斷；fixed 模式 |
| `vguide.enableAdaptivePredicateBudget` | **false** | `true` → low **4–8** / medium **6–12** / high **8–16** |
| `vguide.llmMaxCompletionTokens` | **1024** | adaptive 建議 **2048**（見實驗 config） |
| `vguide.llmSamplesPerCall` | **1** | 單 draw；與 budget 正交 |

對照 1.0.0 分析 batch：prompt 4–8、median 7 → 現預設 cap **6**，並用角色引導提品質。

**實驗 config**（non-thinking 主線候選）：`config/vguide-experiment-freq10-n24.properties` — `enableAdaptivePredicateBudget=true`，tiers (4–8)/(6–12)/(8–16)，`llmMaxCompletionTokens=2048`。217 題：**preds/call median 6**，medium tier **9**；見 [reports/2026-06-10_freq10_n24_adaptive_noL3.md](../reports/2026-06-10_freq10_n24_adaptive_noL3.md)。

## 何時調參

```bash
# 簡單題 / 省 completion：少而精
--option vguide.minPredicatesPerCall=2 --option vguide.maxPredicatesPerCall=4

# 複雜多 loop / 需多關係：放寬上限（仍單 API）
--option vguide.minPredicatesPerCall=4 --option vguide.maxPredicatesPerCall=8
```

若單輪 `max` 仍不夠：**多輪 LLM**（調 `everyN` / `min_interval`）或 **Pre-CEGAR bootstrap**（計劃中），而非盲目開 `llmSamplesPerCall>1`。

## 與其他機制

| 需求 | 用什麼 |
|------|--------|
| 一次要多條不同角色 | **predicate budget**（本文件） |
| 同一 prompt 要多個獨立視角 | `llmSamplesPerCall>1`（少數題第 2+ 輪） |
| 第一輪不夠、CE 變了再補 | 排程 `every_n` ↓ |
| 格式全 reject | repair call（不佔 budget 邏輯，但 repair prompt 沿用同一 budget） |

## 實作

- `VGuideOptions.getPredicateBudget()` → fixed `PredicateBudget(min, max)`
- `PredicateBudgetResolver.resolve(ContextPack, refinementIndex)` → adaptive tiers（`enableAdaptivePredicateBudget=true`）
- `LlmEnsembleMerger.unionValidate(responses, budget)`
- `VGuideRefinementBridge`：每輪 resolve budget；repair 路徑亦 `budget.capOrdered(...)`
