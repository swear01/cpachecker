# 計劃：VGuide 面向 FALSE（找 bug）的 harness 與 prompt 改進

**狀態**：計劃（未實作）— 實作路徑見 [DUAL_PROMPT_V1_PLAN.md](DUAL_PROMPT_V1_PLAN.md)（雙軌 SAFE+BUG，預設開）  
**動機**：v1.3.0 相對 stock **rescued 35 題全為 TRUE**；**0 題** stock UNKNOWN → adaptive FALSE。在 expected-false 子集上 adaptive 還多 **4 題錯誤 TRUE**（如 `bin-suffix-5`, `odd` 等，依 yml 對照）。  
**目標**：在 **不大幅犧牲 TRUE rescued** 的前提下，提高 **FALSE 發現率**、降低 **false benchmark 上的錯誤 TRUE**。

**相關**：[CE_CONTEXT_PROMPT_PLAN.md](CE_CONTEXT_PROMPT_PLAN.md)（CE 摘要，可合併 Phase 1）、[case_studies/const_1-2.md](case_studies/const_1-2.md)

---

## 1. 機制診斷：為何現行 VGuide 偏 TRUE

### 1.1 觸發點只有 spurious CE

```
PredicateCPA 探索 → spurious CE → VGuide LLM → 加 precision → 排除 spurious 路徑
                → feasible CE 到 reach_error → FALSE（**不經 VGuide**）
```

LLM 只在 **抽象過寬的不可行路徑** 上介入；語意是 **收斂抽象、證明路徑不可行**。對「應 FALSE」題，成功路徑是 **讓探索走到真實 assert 失敗**，不是多證一條 spurious 不可行。

### 1.2 Prompt 語意偏「證 safe」

現行 `ProposalPromptBuilder` 關鍵句：

- 「CEGAR-based predicate abstraction verifier」
- 「split similar **spurious** paths」
- 「**assertion support**」「strengthen abstraction」
- 範例多為 bound / guard（`i>=0`, `i<n`）

模型被引導產生 **維持/證明 assertion 成立** 的 invariant 式謂詞，而非 **區分 bug 狀態** 的謂詞。

### 1.3 實測（full_scalar + sv-benchmarks yml）

| 集合 | 題數 | stock FALSE | adaptive FALSE | 仍 UNKNOWN（兩邊） |
|------|------|-------------|----------------|---------------------|
| expected **false**（yml） | 87 | 39 | 39 | **25**（含 `const_1-2`） |
| stock UNKNOWN → adaptive（expected-false） | 4 | — | **0 FALSE / 4 TRUE** | 多為錯誤 TRUE |

expected-**true** 題上的 rescued 全 TRUE 是合理目標；問題在 **bug 題** 上沒多找 bug，甚至偶發 **誤證 safe**。

### 1.4 與 SV-COMP 工具的差

`const_1-2` 等題上 CBMC / CPAchecker SV-COMP 配置多為 **`false(unreach-call)`**（直接找反例或 BMC）。我們是 **predicate CEGAR + 僅在 spurious 上掛 LLM**，路線不同；改進應 **對齊「幫助到達 violation」**，而非照搬 BMC。

---

## 2. 設計原則

1. **雙模式 prompt**：依任務 **expected verdict**（或啟發式）切換 SAFE vs BUG_HUNT，**默認保持現行 SAFE**（向後相容）。
2. **Harness 先讀 manifest**：`expected_verdict` 來自 `*.yml`（與 SV-COMP 一致），不讓 LLM 猜題型。
3. **FALSE 優先指標**：在 expected-false 子集上量 **FALSE 數、錯誤 TRUE 數**，不只看總 solved。
4. **分階實作**：先 prompt + CE 摘要（低成本），再考慮 feasible CE 鉤子（架構改動大）。

---

## 3. Harness 改進

### 3.1 任務元數據（`TaskVerificationMode`）

| 來源 | 欄位 |
|------|------|
| `loop-acceleration/const_1-2.yml` | `expected_verdict: false` |
| Runner 傳入 | `VGUIDE_TASK_YML=/path/to/task.yml` 或 batch 時由 `run_benchmark_set.sh` 解析 |

**實作要點**

- `ContextPack` 新增：`verificationMode`（`SAFE` | `BUG_HUNT` | `UNKNOWN`）
- `ContextPackBuilder`：若 yml 存在則讀 `expected_verdict`；否則 `UNKNOWN` → 用現行 SAFE prompt
- `run_benchmark_set.sh`：對每題 export `VGUIDE_TASK_YML=$SV_BENCHMARKS/c/${rel%.c}.yml`（`.i` 同理）

**配置**

```properties
vguide.promptMode = auto          # auto | safe | bug_hunt
vguide.promptModeAutoFromYml = true
```

### 3.2 CE 摘要（實作見 v1.4）

**SAFE / BUG 共用** 同一 `ce_summary`；壓縮與格式見 **[CE_SUMMARY_COMPRESSION.md](CE_SUMMARY_COMPRESSION.md)**（loop-head、語意 rel、非重複 itp；**廢止** `trace_summary`）。

Dumper：`prompt_components.ce_summary` char count。

### 3.3 排程：expected-false 可選加頻（Phase 3）

| 參數 | SAFE（現行） | BUG_HUNT 建議 |
|------|--------------|---------------|
| `every_n` | 12–24 | **8–12**（更多輪在到達 assert 前） |
| `maxLlmRounds` | 20 | 20 |
| 觸發 | 僅 spurious | 同左（Phase 3 再議 feasible） |

**不** 對所有題加頻；僅 `verificationMode=BUG_HUNT` 時套用 `vguide-experiment-bug-hunt.properties`。

### 3.4 進階：feasible CE / assert 前鉤子（Phase 4，可選）

當 `PredicateCPARefiner` 得到 **feasible** CE 且目標為 `reach_error` / `__VERIFIER_assert` 失敗：

- **不** 走 precision 注入（已是 violation）
- 可選：記錄 dump；或 **最後一輪 spurious 靠近 assert** 時用 BUG_HUNT prompt

需改 `VGuideRefinementBridge` 與 refiner 契約；**列為 Phase 4**，先驗證 prompt-only 收益。

### 3.5 Validation 管線（BUG 模式微調）

現行 noL3：`enableL3Entailment=false` → 全 `PRECISION_ONLY`，不 strengthen interpolant（對找 bug 較友善）。

**Phase 2 可選規則**（`PredicateValidationPipeline`）：

| 規則 | 目的 |
|------|------|
| BUG 模式：若 predicate **entails assertion 公式**（在 loop exit 語境），標記 `LIKELY_SAFE_BIAS`，降優先或 log | 減少「證 safe」式謂詞 |
| BUG 模式：若 predicate **与 assertion 否定相容**（與 CE block 同時 satisfiable），標記 `BUG_RELEVANT` | 分析用，不強制過濾 |

預設 **不刪** 謂詞，只調整 **prompt 內 array 順序說明**；過濾需 regression 證明不傷 TRUE。

---

## 4. Prompt 改進

### 4.1 模式對照

| 區塊 | SAFE（現行，微調） | BUG_HUNT（新增） |
|------|-------------------|------------------|
| 角色句 | CEGAR verifier；split **spurious** paths | 同上，但目標是 **reach assertion failure / `reach_error`** |
| 任務句 | strengthen abstraction；assertion **support** | 提出謂詞使 **violation 狀態可區分**、探索能 **到達 assert 失敗** |
| CE 段 | optional `ce_summary` | **必填** `ce_summary` + 「若 CE 顯示 assert 為假，優先謂詞區分該狀態」 |
| 角色分工 | loop-carried, guard, assertion support | (1) **assert 失敗相關**（如 `x` 在出口為 0） (2) loop 計數/邊界 (3) 區分 safe vs bug 狀態 |
| 禁止 | padding | 額外：**勿** 僅輸出「證明 assertion 恆真」的謂詞 |

### 4.2 BUG_HUNT prompt 草案（插入 `buildBugHuntFirstSpurious`）

```text
Property: reach_error() must be reachable (program may violate the assertion).
Target assertion (may FAIL on real paths): {assertion}

Read the spurious CE summary below. Propose predicates that:
- Help the verifier reach or refine toward states where the assertion FAILS, if reachable;
- Separate loop states that can lead to assertion failure from spurious-only states;
- Use source variable names only.

Do NOT only propose predicates that imply the assertion always holds.

SPURIOUS CE SUMMARY (read-only):
{ce_summary}
```

`buildBugHuntLaterSpurious`：加上 `traceSummary` + 「已注入謂詞勿重複」+ 同上 violation 導向。

### 4.3 `const_1-2` 專用 few-shot（BUG 模式）

```text
Examples (loop sets x=0 each iter; assertion x==1 fails at exit):
  (= x (_ bv0 32))
  (= y (_ bv1024 32))
  (bvuge y (_ bv1024 32))
  (not (= x (_ bv1 32)))
```

觸發條件：`assertion` 含 `x` 且 source 有 `x = 0` 在 loop 內（簡單 heuristic）或 task id `const_1-2`。

### 4.4 範例與 parity 題

現行 parity 範例（`bvand`/`bvurem`）在 BUG 模式改為：

- 「parity violation 狀態」：` (= (bvand x (_ bv1 32)) (_ bv0 32))` 等
- 避免只給「證 odd」的 predicate

### 4.5 Repair prompt

BUG 模式 repair 補充：「Rejected predicates may have been too aligned with proving assertion; try predicates true in **failing** states shown in CE.」

---

## 5. Benchmark harness（評估用）

### 5.1 新 manifest

| 檔案 | 內容 |
|------|------|
| `benchmark_sets/regression_false_expected.list` | yml `expected_verdict: false` ∩ full_scalar（約 **87**） |
| `benchmark_sets/regression_false_unknown.list` | 上式 ∩ stock & adaptive 皆 UNKNOWN（約 **25**），含 `const_1-2` |

生成腳本：`scripts/vguided-cegar/regenerate_benchmark_lists.py` 擴充（讀 yml）。

### 5.2 執行

```bash
export VGUIDE_CONFIG=config/vguide-experiment-bug-hunt.properties
export VGUIDE_LLM_THINKING=disabled
./scripts/vguided-cegar/run.sh cpa --set regression_false_unknown --ablation no-l3 --timelimit 300
```

`vguide-experiment-bug-hunt.properties`：`include freq20-n12` + `vguide.promptMode=auto` + `vguide.promptModeAutoFromYml=true`。

### 5.3 驗收指標（優先於總 solved）

| 指標 | v1.3.0 基線 | 目標（第一輪 prompt-only） |
|------|-------------|---------------------------|
| expected-false：**FALSE 數** | 39 | **≥42**（+3） |
| `regression_false_unknown` 解出 | 0 | **≥3**（含 `const_1-2` 若可） |
| expected-false：**錯誤 TRUE** | 22 | **≤18**（不惡化） |
| expected-true rescued | — | **不下降 >3** |
| `const_1-2` | UNKNOWN | **FALSE** 或至少 UNKNOWN→有進度（refs↓） |

---

## 6. 實作階段

### Phase 1 — Prompt 雙模式 + yml 讀取（**1–2 天**）

- [ ] `TaskVerificationMode` + yml 解析（SnakeYAML 或 regex `expected_verdict`）
- [ ] `ProposalPromptBuilder.buildFirst/Later(..., mode)`
- [ ] `run_benchmark_set.sh` 傳 `VGUIDE_TASK_YML`
- [ ] Unit：`ProposalPromptBuilderTest` SAFE vs BUG 字串
- [ ] 離線：`test_llm_proposal_quality.py --tasks const_1-2,down` 看是否出 `x=0` 類謂詞

### Phase 2 — CE 摘要 + dumper（**1 天**，可與 Phase 1 並行）

- [ ] `CeSummaryBuilder`（從 `ContextPackBuilder.summarizeTrace` 擴充 + interpolants）
- [ ] 合併 [CE_CONTEXT_PROMPT_PLAN.md](CE_CONTEXT_PROMPT_PLAN.md)
- [ ] `regression_false_unknown` smoke（25 題）

### Phase 3 — BUG 專用排程 + config（**0.5 天**）

- [ ] `vguide-experiment-bug-hunt.properties`
- [ ] 可選：僅 `BUG_HUNT` 題 `every_n=8`

### Phase 4 — Validation 偏置 + feasible 鉤子（**調研後**）

- [ ] `LIKELY_SAFE_BIAS` 標記（僅 log / dump）
- [ ] 評估是否在 refiner 加 assert-near 鉤子

---

## 7. 風險與緩解

| 風險 | 緩解 |
|------|------|
| BUG prompt 傷 TRUE rescued | `auto` 模式；expected-true 仍用 SAFE |
| 錯誤 TRUE 增加 | 驗收盯 `wrong TRUE on false`；必要時 SAFE_BIAS 過濾 |
| yml 缺失 | `UNKNOWN` → SAFE（現行行為） |
| LLM 仍不產 violation 謂詞 | CE 摘要 + `const_1-2` few-shot；仍不行再 Phase 4 |
| 與「總 solved」目標衝突 | 報告 **分開** TRUE-gain / FALSE-gain |

---

## 8. 與現行實驗線的關係

| 實驗 | 關係 |
|------|------|
| freq20/n12（下一版） | 可先跑 **SAFE 基線**；BUG 實驗用獨立 `regression_false_*` |
| CE_CONTEXT 計劃 | 併入 Phase 2；BUG 模式 **強制** 帶 CE |
| const_1-2 case study | Phase 1 離線驗證 + Phase 2 單題 CPA |

---

## 9. 參考

- SV-COMP task：`~/sv-benchmarks/c/loop-acceleration/const_1-2.yml`（`expected_verdict: false`）
- CPAchecker SV-COMP'24：同題 `false(unreach-call)`
- 程式碼：`ProposalPromptBuilder.java`, `VGuideRefinementBridge.onSpuriousBeforeRefinement`, `ContextPackBuilder.java`
