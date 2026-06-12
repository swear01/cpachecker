# 計劃：VGuide 面向 FALSE（找 bug）的 harness 與 prompt 改進

**狀態**：早期計劃 / TODO — v1.5 已改走 [SV-COMP Loops exploratory evaluation](V1_5_LOOPS_EXPLORATORY_PLAN.md)，FALSE / doomed-region context 暫移 v1.6+；v1.4 雙軌見 [DUAL_PROMPT_V1_PLAN.md](DUAL_PROMPT_V1_PLAN.md)（已實作）
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
---

## 10. v1.6+ TODO：原 v1.5 FALSE Context 工程（整塊移入）

> **狀態更新（2026-06-11）：** 以下內容為 **FALSE / bug-finding future work**（v1.6+），不屬 v1.5。v1.5 見 [V1_5_LOOPS_EXPLORATORY_PLAN.md](V1_5_LOOPS_EXPLORATORY_PLAN.md)。

### 10.0 目標一句話

在 **不動 VGuide 主管線** 的前提下，把 BUG_HUNT track 的 context 從「證 safe 的反義 prompt」升級為 **doomed-region / error-invariant 導向的 counterexample-to-predicate**；SAFE track 作 control group，僅加共用 ledger 與可選 throttle；以 **property-aligned bug benchmarks** 上的 FALSE 數與 new-FALSE 為主指標。

---

### 10.1 核心診斷

#### 10.1.1 瓶頸不是「模型不想找 bug」

FALSE 只在 **某條 abstract error path 通過 concrete feasibility check** 時宣告。瓶頸是 **candidate path selection** 與 **refinement budget 分配**。

#### 10.1.2 Predicate 影響 FALSE 的三條因果通道

設 **violation depth d\*** = 最短 failing execution 所需的 loop iteration **總數**（沿最短路徑累加）。

| 通道 | 機制 | 與 SAFE/BUG 的關係 |
|------|------|-------------------|
| **1 Off-path one-shot refutation** | 若 abstraction 能表達 ¬D（D = doomed region，從該 state 可達 failed assertion），經過 ¬D-labeled state 的 spurious sibling 可被直接或極少次 refinement 排除 | SAFE invariant atoms **也走此通道** → dual 不必然傷 FALSE，但 BUG 邊際價值須來自通道 2/3 |
| **2 On-path precision** | 表達 D 的 atoms 讓真正 failing path 的 prefix 與 safe states 區分，feasibility check 落在對的 candidate | BUG track 主戰場 |
| **3 Refinement 節約** | 每條比真路徑短的 abstract error path 須先 refute；好 atoms 讓 refutation 更便宜、更批次 | 兩軌皆可貢獻 |

#### 10.1.3 鐵律

**Predicate 無法縮短 feasible path 本身。** Candidate path 必須物理上包含 ≥ d\* 次 loop-head visit；排除所有更短 abstract error path 在純 predicate abstraction 下會退化成 **counting**（interpolant 序列 y≤1, y≤2, …）。

**案例 `const_1-2`：** 第一輪 LLM 已 propose 並 inject `(= x (_ bv0 32))`、`(bvslt y (_ bv1024 32))`，verdict 仍 UNKNOWN — 因 d\* ≈ 1024，結構性需展開或 portfolio 策略，非「缺謂詞」。SV-COMP 上 CPAchecker 解此類題靠 **strategy portfolio**（BMC、symexec、value analysis、PredAbs…），非單一 PredAbs + LLM。

#### 10.1.4 A/B 分類（量化判準）

| 類別 | 條件 | Context-only 期望 |
|------|------|-------------------|
| **A（predicate-gap）** | d\* ≲ 數百；stock 把 refinement 燒在錯誤區分上 | **主戰場** |
| **B（exploration-gap）** | d\* ≳ 10³；counting 結構性必然 | **無解**（需 strategy 層） |
| **Mixed** | 巢狀乘積或 phase 邊界介於兩者 | 部分可救 |

#### 10.1.5 Soundness 邊界

Predicate 注入 **不可能造成錯誤 verdict**（FALSE 經 concrete check；TRUE 是 over-approx fixpoint）。所有 proposal 的 risk 僅 **時間 / precision bloat**，非 soundness。

#### 10.1.6 理論錨點

- **Danger invariants**：safety invariant 的對偶；總結「保證能到達 error 的 trace 集合」（David, Kesseli, Kroening, Lewis, FM 2016）。
- **Doomed states**（Hoenicke et al., FM 2009）。
- **Error invariants**：error trace 上 over-approx reachable states，保留「繼續執行仍失敗」的狀態（Ermis, Schäf, Wies, FM 2012）。

**BUG track 目標物** = 上述概念在 **loop head** 上的 **atom 化**，不是「invariant 的反義詞」。

---

### 10.2 原 v1.4 基線與 FALSE 失敗歸因

`full_scalar` 217 題，300s：

| Run | TRUE | FALSE | UNKNOWN | Solved | PAR-2 avg |
|-----|------|-------|---------|--------|-----------|
| stock | 76 | 40 | 101 | 116 | 283.36s |
| v1.3 adaptive | 110 | 40 | 67 | 150 | 192.03s |
| **v1.4 dual** | **117** | **38** | 62 | **155** | **183.05s** |

- v1.4：**+39 solved vs stock**；rescued 幾乎全為 UNKNOWN→TRUE。
- FALSE：**40→38**（−2 regression：`benchmark40_polynomial`、`benchmark53_polynomial`）；**0 new FALSE**。

待驗證歸因：

1. Spurious-only context 與「找 failure」語意不一致。
2. SAFE∪BUG merge + 共用 validation；SAFE invariant 先佔序。
3. BUG 在所有 task 上跑，safe task 浪費 budget。
4. 無 later-round 記憶（counting / 重複 safe preds）。
5. 2 個 regression 死因未明（bloat vs candidate 順序）。

---

### 10.3 Bug benchmark taxonomy（TODO）

主軸：**d\***；archetype 為疊加結構特徵。重啟 FALSE 工作時，Phase 0 產出 `bug_benchmark_taxonomy.csv`。

| # | Archetype | 典型解鎖 predicates | A/B | LLM 有用 context 訊號 |
|---|-----------|---------------------|-----|------------------------|
| 1 | **Exit-mismatch / reset-constant**（loop 內重置變數，exit 後 assert 矛盾；`const_*`） | `(= x 0)`、`(not (= x 1))`、exit `(bvsge y N)` | N≥10³→**B**；N 小→A | ledger(reset) + tension；frontier **COUNTER-BOUND** |
| 2 | **Input-gated bug**（nondet + guard ladder，failing path 上 loop 淺） | 輸入區域 `(bvsge n k)`、guard atoms、parity | **A** | input-gate map；guards-to-error |
| 3 | **Phase / mode-switch**（`phases_*`、`Mono*`） | phase discriminator、per-phase rel、boundary equality | threshold 小→A；10⁶ 常數→B | ledger conditional update；frontier 卡 phase boundary |
| 4 | **Nested / sequential multi-loop** | relational `(= s (bvadd (bvmul i K) j))`、inner-exit equality | 乘積≲10³ 且 interleaving→A；大→B | cross-loop counter pairing |
| 5 | **Disjunctive guards / branch ladder** | branch atoms + 相關性 | 幾乎純 **A** | guards-to-error |
| 6 | **Stride mismatch / off-by-one** | relational stride、`(= i N)`、parity | bound 小→A；大常數→B | ledger stride；frontier arithmetic gap |

---

### 10.4 Context 設計：十項 Proposal（P1–P10）

| ID | 名稱 | Phase | 檔案 | Archetypes |
|----|------|-------|------|------------|
| P1 | Mechanism-grounded role brief | 1 | `ProposalPromptBuilder` | 全部 |
| P5 | Loop-role ledger + tension | 1 | `LoopLedgerBuilder` + `ContextPack` | 1,3,4,6 |
| P6 | Input-gate map | 1 | `SourceStaticAnalyzer` | 2,5,3(symbolic) |
| P2 | Doomed-region + suffix-WP | 2 | `ContextPackBuilder` + prompt | 1,3,4,6 |
| P3 | Plan-before-predicates schema | 2 | prompt + tolerant parse | 全 A 類 |
| P4 | Frontier digest | 2 | `FrontierDigestBuilder` | 2,3,5,6 + 診斷 |
| P8 | Single worked exemplar | 2 | `ProposalPromptBuilder` | 教程序（phase 型） |
| P7 | Anti-divergence directive | 3 | `CeSummaryBuilder` / bridge | B 止損；間接省 budget |
| P9 | Verdict-conditional throttling | 3 | `ProposalPromptBuilder` | 防 regression / safe 浪費 |
| P10 | Cross-loop relational pairing | 3 | ledger 擴充 + prompt | 4 |

#### P1 — Mechanism-grounded role brief

System message 從「身分宣告」改為 **目標函數 + 因果機制**。

BUG system 核心：

```text
You assist a CEGAR predicate-abstraction model checker. The verifier declares FALSE
only when an ABSTRACT error path passes a CONCRETE feasibility check. Your predicates
cannot "execute" the bug. They act as state splitters:
(1) atoms characterizing the complement of the doomed region let the verifier discard
    safe branches without further refinement;
(2) atoms that hold along the genuine failing execution keep its prefix abstractly
    distinct, so it becomes the next candidate error path.
Doomed region D := states from which the failed assertion is reachable. Propose atoms
describing D and its boundary, expressed at loop heads.
```

SAFE system：同結構，目標物改為 **inductive invariant / safe abstraction**。

#### P2 — Doomed-region targeting（suffix-WP elicitation）

BUG track 計算對象改為 **D(ℓ) 在 loop head 的 atom 化**；builder 切 **loop exit → assert** 的 suffix 原始碼，指示 model 將 ¬assert 往回拉過 suffix 與 exit condition。

```text
TARGET OBJECT
D(L1) := states at the head of L1 from which some continuation reaches the FAILED assertion.
Compute it backwards:
  step 1: negate the assertion:  !(x == 1)
  step 2: pull it through the suffix below and through the exit condition !(y < 1024)
  step 3: emit each atom of the result AND of its boundary as one SMT-LIB2 predicate.
SUFFIX (loop exit -> assertion, lines 9-12):
  }
  __VERIFIER_assert(x == 1);
```

#### P3 — Plan-before-predicates output schema

JSON 欄位順序強迫 model 先產生 violation plan / witness，再產生 predicates（non-thinking 的 schema-induced grounding）。

```json
{
  "violation_plan": [
    {"at": "L1 head, final visit", "must_hold": "y >= 1024 && x == 0"},
    {"at": "line 12", "must_hold": "x != 1"}
  ],
  "witness_hint": {"iterations_L1": 1024},
  "verdict_guess": "FALSE",
  "limit": "NONE",
  "predicates": [
    "(bvsge y (_ bv1024 32))",
    "(= x (_ bv0 32))",
    "(not (= x (_ bv1 32)))"
  ]
}
```

Parser tolerant：只讀 `predicates` key；`verdict_guess ∈ {FALSE, TRUE, UNSURE}`；`limit ∈ {NONE, EXPLORATION_BOUND}`。

#### P4 — Frontier digest（blocked-by + violation-depth）

從 interpolant 序列找 **blocking edge**，壓縮成一行決策梯度 + blocking class。

```text
WHY THE LAST CANDIDATE DIED
The abstract error path was refuted at edge (L8 -> L12).
The suffix required (y >= 1024); the prefix admits at most y <= 1.
Blocking class: COUNTER-BOUND. Estimated violation depth: >= 1024 iterations of L1.
RULES:
- BRANCH-GUARD / INPUT-RANGE / RELATION: propose atoms that let a DIFFERENT path
  satisfy the blocked constraint.
- COUNTER-BOUND with depth > 256: do NOT emit numeric bound chains;
  set "limit":"EXPLORATION_BOUND" and emit only doomed-region atoms.
```

#### P5 — Loop-role ledger + assertion-tension

每 loop 一張效果帳本 + 一行 assert 與 loop 效果衝突。

```text
LOOP L1 (line 8): guard (y < 1024)
  strides:    y += 1      [monotone up; exit forces y >= 1024; exact exit value y = 1024]
  resets:     x = 0       [every iteration]
ASSERTION (line 12): x == 1
TENSION: L1 establishes x = 0 at every head visit; nothing between L1-exit and line 12
writes x. If the exit is reachable, the assertion FAILS. Violation depth ~ 1024.
```

#### P6 — Input-gate map

列出 nondet 變數與通往 assert 的 guards，指示切 bug-enabling input region。

```text
INPUT GATES
n = __VERIFIER_nondet_int()   (line 3)
guards involving n on paths toward the assertion: (n > 5) at L6, (n % 2 == 0) at L9
If the violation exists it is ENABLED by an input region. Carve it: propose atoms over
inputs only (region boundaries, exact enabling values, parities).
```

#### P7 — Anti-divergence directive

對近 m 輪 interpolant 做 anti-unification；偵測 counting pattern 時給禁令 + fork。

```text
REFINER TRAJECTORY: the last 6 refinements added y <= 1, y <= 2, ..., y <= 6.
The refiner is counting iterations of L1 one by one (divergence).
Do NOT add more numeric bounds on y. Either:
(a) propose a relation holding at EVERY L1 head visit that, with the exit condition,
    decides the assertion in closed form; or
(b) declare "limit": "EXPLORATION_BOUND".
```

#### P8 — Single worked exemplar

一個約 25 行完整微型 trace（source → ledger → gates → frontier → plan → preds → 一句機制解釋），取代 example 清單。使用 **phase 型** archetype 3，與 `const_*` 錯開，並標註：`the program above is unrelated to your task`。

#### P9 — Verdict-conditional throttling

Prompt 層雙向 routing（不做 yml harness）：

- **BUG：** 若 `verdict_guess` 為 TRUE → 回傳 ≤2 proof-support atoms，不虛構 violation。UNSURE → 當 FALSE。
- **SAFE：** 若 assertion 可違反 → ≤2 泛用 support atoms。

目的：不動 merge 下緩解 SAFE atoms 淹沒 BUG、修 v1.4 2 個 FALSE regression（若 autopsy 支持 precision bloat 假說）。

#### P10 — Cross-loop relational pairing

巢狀 loop 的 counter 配對，要求 relational atoms + exit equalities。

```text
LOOP NESTING: L1(i: 0 -> 10) contains L2(j: 0 -> 10, j reset each L1 iter); s += 1 in L2.
Propose at most 2 RELATIONAL atoms tying counters across levels,
plus exact exit equalities.
```

---

### 10.5 ContextPack 擴充（TODO）

```java
// ContextPack 新增欄位（record 擴充）
String loopLedger;        // P5
String inputGates;        // P6
String suffixSlice;       // P2
String frontierDigest;    // P4
String refinerTrajectory; // P7
// ceSummary 保留但 BUG prompt 中降級為佐證（≤6 rel）
// traceSummary → P7 或廢止合併入 refinerTrajectory
```

建議新增類：

```text
org.sosy_lab.cpachecker.cpa.predicate.vguide/
  LoopLedgerBuilder.java
  FrontierDigestBuilder.java
  SourceStaticAnalyzer.java
```

不變：`VGuideRefinementBridge` 的 merge / validate / inject / schedule 邏輯。

---

### 10.6 Prompt assembly（TODO）

#### BUG_HUNT user message 順序

| # | 區塊 | Proposal |
|---|------|----------|
| 1 | Task 一行 | — |
| 2 | SOURCE（全文，行號） | — |
| 3 | LOOP LEDGER + TENSION | P5 |
| 4 | INPUT GATES | P6 |
| 5 | FRONTIER + TRAJECTORY | P4 + P7 |
| 6 | DOOMED-REGION + suffix-WP | P2 |
| 7 | ce_summary（壓縮，≤6 rel） | 降級佐證 |
| 8 | WORKED EXEMPLAR | P8 |
| 9 | RULES（P9 throttle）+ OUTPUT SCHEMA | P3 + P9 |

SAFE user message：結構維持 v1.4（control group + attribution），僅可新增共用 P5 ledger 與可選 P9 throttle 一行；不新增 P2/P3/P4/P8、BUG schema、doomed-region 塊。

---

### 10.7 Phase 0：診斷（重啟前必做）

#### FALSE regression autopsy

對象：`benchmark40_polynomial`、`benchmark53_polynomial`。對比 v1.3 adaptive vs v1.4 dual dump / logs。

| 檢查項 | 解讀 |
|--------|------|
| per-refinement abstraction 時間 | ↑ → precision bloat → P9 高優先 |
| precision 大小趨勢 | 同上 |
| refinements-to-timeout vs v1.3 | 未跑完 feasible path → bloat |
| candidate 順序 / merge 序 | 若 preds 正但順序錯 → merge 問題 |

產出：`docs/vguided-cegar/analysis/v1.4_false_regression_autopsy.md`

#### d\* audit + taxonomy

對象：unreach-call false 題（至少 unsolved + 抽樣已解）。欄位：`task`, `archetype`, `d_star_estimate`, `class_A_B`, `notes`。

產出：`docs/vguided-cegar/analysis/bug_benchmark_taxonomy.csv`

---

### 10.8 實作階段（若升級為 v1.6 plan）

#### Phase 1 — 基礎建設

| 任務 | 交付 |
|------|------|
| P1 mechanism system messages | `ProposalPromptBuilderTest` SAFE/BUG system 不同 |
| P5 loop ledger + tension | `LoopLedgerBuilder` + unit test（`const_1-2`） |
| P6 input gates | `SourceStaticAnalyzer` |
| ContextPack 擴充 | record + builder |
| Config 雛形 | `config/vguide-experiment-v1.6-false-context.properties` |

#### Phase 2 — BUG 核心

| 任務 | 交付 |
|------|------|
| P2 suffix + doomed-region block | prompt + builder |
| P3 extended JSON + tolerant parse | parser test |
| P4 frontier digest | `FrontierDigestBuilder` + 常數門檻校準 |
| P8 worked exemplar | 固定字串 + schema 對齊 |
| ce_summary 降級 | BUG prompt ≤6 rel |

#### Phase 3 — 止損、routing、評估

| 任務 | 交付 |
|------|------|
| P7 anti-divergence | bridge 傳 interpolant 歷史 |
| P9 throttling | 若 autopsy 支持 bloat |
| P10 cross-loop | 若 taxonomy 顯示 archetype 4 多 |
| Section ablation | 拔 P2/P4/P5 各一 run |
| 實驗報告 | `reports/2026-06-xx_v1.6_false_context.md` |

---

### 10.9 評估與驗收（future）

Primary 指標：property-aligned expected-false 題的 FALSE 數、new-FALSE vs stock/v1.4，以及 v1.4 2 個 FALSE regression 是否收復。

Guard 指標：

- bug 上 wrong-TRUE = 0。
- TRUE rescued 不明顯下降。
- PAR-2 不明顯惡化。

Context 有效判別：

| 訊號 | 來源 |
|------|------|
| new-FALSE 的 D-atoms 在 verdict precision 中 | dump |
| refinements-to-FALSE vs stock | summary CSV |
| `verdict_guess` / `limit` confusion matrix | `llm_rounds.jsonl` |
| Novel% 拆 SAFE-track vs BUG-track | `analyze_predicate_study.py` |
| Section ablation | smoke subset |

Future 驗收門檻（草案）：

| 項目 | 門檻 |
|------|------|
| v1.4 2 個 FALSE regression | 收復 |
| property-aligned FALSE vs stock | ≥ +2（audit 下修時 ≥ +1 並文檔說明） |
| new-FALSE（stock 非 FALSE → new FALSE） | ≥ 2（理想） |
| bug wrong-TRUE | 0 |
| Unit tests | 全綠 |
| 文檔 | plan + 實驗報告 + taxonomy CSV |

---

### 10.10 超出 context-only 的 v1.6+ 候選

#### Sentinel-triggered strategy escalation

觸發：

- (`limit == EXPLORATION_BOUND` 連續 ≥2 輪) **或** (P7 divergence ≥ k 次)
- 且 `verdict_guess == FALSE`

動作：剩餘 budget 交給 CPAchecker **falsification 配置**（BMC / value analysis / symbolic execution — SV-COMP portfolio 路線）。

價值：收割 B 類；觸發訊號來自 context 工作 → **per-task 語意驅動切換**，非固定 sequential portfolio。

風險：過早 escalate 殺 TRUE → gate 在 `verdict_guess==FALSE`。
