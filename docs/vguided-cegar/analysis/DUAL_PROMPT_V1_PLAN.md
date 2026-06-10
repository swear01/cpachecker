# v1.4 計劃：雙 prompt（SAFE + BUG_HUNT）+ cache + JSON mode + CE 摘要

**狀態**：計劃（未實作）  
**版本標**：實測通過後 `v1.4.0`  
**相關**：[FALSE_ORIENTED_VGUIDE_PLAN.md](FALSE_ORIENTED_VGUIDE_PLAN.md)、[CE_CONTEXT_PROMPT_PLAN.md](CE_CONTEXT_PROMPT_PLAN.md)

---

## 0. 目標一句話

每一 scheduled LLM 輪：**SAFE×K + BUG×K** API（K=`llmSamplesPerCall`，**每軌各 K**）；**完整共用 source**；profile 差異在 source **之後**；**永久** `json_object`；**必做** `ce_summary`；兩軌 parse 結果 **直接 union 合併**（不做 cap 擠掉）；合併後單次 validate/inject。

---

## 1. 已敲定決策

| 項 | 決策 |
|----|------|
| JSON mode | **永久開啟**，無 config/env 開關 |
| K 語意 | K=1 → **SAFE×1 + BUG×1** = 2 HTTP/輪；K=3 → 每軌 3 = 6 HTTP/輪。**所有 spurious 輪相同**（含第一次 spurious，**取消**「#1 只 1 draw」） |
| source | **兩軌 byte 級相同** `pack.sourceCode()` |
| harness | **一套** bridge/validation/inject；**兩套** prompt profile |
| 合併 | **直接 union**：SAFE 與 BUG 所有 parse 成功謂詞合併、字串 dedupe，**不**做 `budget.capOrdered` 裁切 |
| ce_summary | **必做**（first/later 皆帶） |
| 謂詞來源 | dump **紀錄** `source_profile`（SAFE/BUG） |
| Repair | **任一站軌** parse 出 accepted → **不修**；僅兩軌皆空才 repair |
| `dualPromptMode` | **預設 true**（v1.4 主路徑；關閉僅供對照實驗） |
| SAFE∥BUG | **不平行**；SAFE 軌完 → BUG 軌 |
| yml 分流 | v1 不做 |

### 1.1 `wallBudgetSec` 是什麼？（與 API×2 的關係）

可選項 `vguide.wallBudgetSec`（預設 **0** = 不限制）：為 **整題分析** 設 LLM 牆鐘上限；每次 API 的 latency 累加進 `llmUsedMs`，剩餘時間 **&lt; 15s** 時跳過後續 LLM（`llm_skip_reason=wall_budget`）。

- **預設 `wallBudgetSec=0`**：實際 **不會** 因 API 變 2 倍而提早停；先前「API×2 提早 wall_budget」僅在 **手動設了 wall 上限** 時才可能發生。
- 若日後設 `wallBudgetSec>0`，dual 會更快耗盡配額 → 可加大 wall 或減 `maxLlmRounds`。

---

## 2. Prompt 分層（cache + 語意）

```
system          RULES + JSON contract（217 題共用）
user 前段       loop heads、contract、hints
user source     "Source code:\n" + 完整源碼（兩軌相同）
user profile    SAFE 或 BUG 專屬塊（§2.1）
user dynamic    ce_summary（first/later）、budget min/max（最末）；**無** trace_summary
```

**assertion** 在 **profile 塊**（source 之後）：標籤不同、內容相同。

### 2.1 Profile 專屬塊（整塊分開，非一句目標句）

| 塊 | SAFE | BUG_HUNT |
|----|------|----------|
| 角色 | CEGAR；split **spurious** | 目標 **reach assertion failure** |
| `predicateBudgetBlock` | bound / assertion support | violation / assert-failure / spurious split |
| `taskExamples` | 現行 bound | `x=0`、`not (= x 1)`；parity violation |
| first/later 尾段 | strengthen abstraction | 勿只證 assertion 恆真 |
| repair | 現行 | failing-state 導向 |

### 2.2 CE 摘要與壓縮

現行 `trace_summary`：5 block **完整** `dumpFormula`，median **2772** chars（max **8914**）— **冗餘且 SSA 名對 LLM 有害**。

**不用字元 cap 當主策略**（硬切 SMT 會產生不可 parse 碎片）。改 **語意壓縮**，詳見 **[CE_SUMMARY_COMPRESSION.md](CE_SUMMARY_COMPRESSION.md)**：

| 手段 | 說明 |
|------|------|
| **Loop-head only** | 只摘要 trace 上 loop head block（≤4），非任意前 5 block |
| **關係式提取** | AND 拆 conjunct → source 名 + predicate 風格 `(bvslt i n)`，丟 `.def_*` / `declare-fun` |
| **去重 / delta** | 跨 head 不重複列；`i: 0→1` 僅變化量 |
| **interpolant 合併** | 與 block 子集重複則不另列 |
| **assertion 優先排序** | 先列 assertion 變量相關 rel，非 assertion 的後刪 |
| **廢止 `trace_summary`** | 僅 `ce_summary` 一條通道 |

**語意上限**：≤4 heads、每 head ≤8 rels。  
**字元 fallback**：僅 &gt;**12000** chars（必須很高；v1.3 trace max ~8914）。  

與 `trace_summary`：**完整 dump 並送** 重複性 ~**97%**；語意 ce + 廢止 trace 則 **itp 多為新增**（見 [CE_SUMMARY_COMPRESSION.md §3](CE_SUMMARY_COMPRESSION.md)）。  
預估 median **&lt;600 chars**（現行 trace 2772）。

---

## 3. Harness 行為

### 3.1 配置

```properties
# config/vguide-experiment-dual-prompt-v1.properties
include vguide-experiment-freq20-n12.properties
vguide.dualPromptMode=true
vguide.llmSamplesPerCall=1
```

| 選項 | v1.4 預設 |
|------|-----------|
| `dualPromptMode` | **true** |
| `llmSamplesPerCall` | 1（= SAFE×1 + BUG×1 / 輪） |
| `getLlmSamplesForRefinement` | **一律** `llmSamplesPerCall`（刪除 #1 特例） |

`maxLlmRoundsPerAnalysis` 仍計 spurious **輪次**；HTTP ≈ `rounds × 2K`（+ 偶發 repair）。

### 3.2 單輪順序

```
SAFE 軌: K 次（1 sync + (K-1) parallel extras，僅 SAFE 同 prompt）
BUG 軌: K 次（同上）
→ union 合併 → validate → inject
```

### 3.3 合併（直接 union，不 cap）

```text
merged = dedupe(SAFE_preds ∪ BUG_preds)   // 字串 exact dedupe，保留先出現順序（SAFE 軌優先）
→ PredicateValidationPipeline.validate(merged)   // 不經 budget.capOrdered
```

LLM **單次回應** 內仍受 prompt 的 min/max **建議**；合併層 **不** 再砍條數。注入條數由 L1/L2 + loop-head 是否在 trace 決定。

### 3.4 謂詞來源紀錄

| 位置 | 欄位 |
|------|------|
| `llm_rounds.jsonl` | 每 API 行已有 `predicates_raw` |
| `refinements.jsonl` / validated 行 | `source_profile`: `SAFE` / `BUG_HUNT` |
| 合併後列表 | 每 raw 字串帶 profile → 寫入 dump |

### 3.5 Repair

| 條件 | 動作 |
|------|------|
| SAFE 或 BUG **任一** 有 accepted | **不修** |
| 兩軌皆空且有 rejected | **1 次** repair（profile 可固定 BUG 或 heuristic） |

---

## 4. JSON mode（永久）

`PredicateProposalClient` 固定 `response_format: json_object`；`messages` = system + user。

---

## 5. Dumper / 分析腳本（實作時更新）

### 5.1 `llm_rounds.jsonl`

| 欄位 | 說明 |
|------|------|
| `prompt_profile` | `SAFE` / `BUG_HUNT` |
| `prompt_kind` | `first_safe` / `first_bug` / `later_safe` / `later_bug` / `repair_*` |
| `call_kind` | `safe_primary` / `bug_primary` / `safe_ensemble_extra` / … |
| `prompt_components.ce_summary` | char count |
| `prompt_components.trace` | later 應為 **0**（併入 ce） |
| `dual_prompt_mode` | boolean |

### 5.2 腳本

- [ ] `scripts/vguided-cegar/analyze_predicate_study.py` — 新欄位、`source_profile` 彙總、V9 repair 規則
- [ ] `post_batch_analysis.sh` — HTTP 次數公式 `2K×rounds`
- [ ] `compare_official_reference.py` — dual 實驗目錄

### 5.3 schema

`run_manifest.json`：`dual_prompt_mode`、`schema_version` bump。

---

## 6. 測試與實驗

| ID | 配置 | 集合 |
|----|------|------|
| A | dual off（對照） | `regression_false_unknown` |
| C | dual on + ce_summary（**v1.4 目標**） | 同上 + `const_1-2` |

驗收：FALSE +≥2、`const_1-2` 進度、BUG 軌 `source_profile` 注入 &gt;0、`parse_ok`、壓縮後 `prompt_tokens` median &lt; 2000。

**實測（2026-06-10，`full_scalar_dual_v1_20260610`）：** 155 solved、PAR-2 183s（優於 v1.3）；**FALSE 38（−2 vs stock，0 新 FALSE）→ FALSE 目標失敗**。見 [reports/2026-06-10_dual_prompt_v1_noL3.md](../reports/2026-06-10_dual_prompt_v1_noL3.md)。

---

## 7. 實作順序

```
Phase 0  JSON client + messages
Phase 1  CeSummaryBuilder（壓縮）+ ContextPack.ceSummary；later 停用 trace_summary 重複
Phase 2  ProposalPromptBuilder 雙 profile + 分層
Phase 3  union merge（無 cap）+ source_profile
Phase 4  VGuideOptions：dual 預設 true；刪 #1 特例
Phase 5  Bridge 雙軌 + repair 條件
Phase 6  Dumper + analyze 腳本
Phase 7  config + LLM_ENSEMBLE / RUN_EXPERIMENTS / ConfigurationOptions.txt
```

---

## 8. 留 v2

yml 分流、validation safe-bias、feasible CE 鉤子、BUG 專用 `every_n`。

---

## 9. 文檔狀態（2026-06 檢查）

### 9.1 已對齊 v1.4 計劃

| 文件 | 狀態 |
|------|------|
| 本文件、`CE_SUMMARY_COMPRESSION.md`、`CE_CONTEXT_PROMPT_PLAN.md` | ✅ |
| `LLM_ENSEMBLE.md`、`PREDICATE_BUDGET.md`、`LLM_API.md` | ✅ |
| `RUN_EXPERIMENTS.md`、`README.md`、`STANDARD_BENCHMARK_SUITE.md` | ✅ |
| `FALSE_ORIENTED_VGUIDE_PLAN.md` | ✅ |
| `config/vguide.properties` 註解、`ConfigurationOptions.txt` 註解 | ✅ |

### 9.2 刻意保留舊語境（歷史，不改）

| 文件 | 說明 |
|------|------|
| `reports/2026-06-08_*`、`reports/2026-06-10_*` | v1.3 **實測**快照 |
| `experiments/2026-06-10_freq*.md` | 已跑實驗 |

### 9.3 實作與實驗（2026-06-10）

| 項目 | 狀態 |
|------|------|
| 代碼（dual、ce_summary、JSON、dumper） | ✅ `85706b4bf0` |
| `config/vguide-experiment-dual-prompt-v1.properties` | ✅ |
| `full_scalar` 217 題實跑 | ✅ |
| FALSE +≥2 驗收 | ❌ |
| `regression_false_unknown` 子集 | 未跑 |
| analysis dump（`source_profile` 統計） | 本 run 未開 |

### 9.4 可再改善（非阻塞）

| 建議 |
|------|
| `architecture/UNIFIED_VGUIDE_ARCHITECTURE.md` 雙 profile 一節 |
| `PREDICATE_ANALYSIS_PLAN.md` §4.2 欄位（v1.4 草案已加） |
| `OFFLINE_SAMPLING.md` 註明未模擬 dual / ce_summary |
| `regression_false_unknown.list` 自動生成 |
