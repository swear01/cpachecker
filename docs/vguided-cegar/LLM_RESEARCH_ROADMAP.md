# VGuide 廣域研究地圖：LLM 在這個 verifier 還能介入哪裡

這份文件是**長 horizon** 的研究地圖，不是 v1.5.2 的 sprint plan。

兩份既有計劃的關係：

| 文件 | Horizon | Scope |
|------|---------|-------|
| [`SVCOMP26_VGUIDE_FULLSET_PLAN.md`](SVCOMP26_VGUIDE_FULLSET_PLAN.md) | v1.5.1（done） | reachability / Loops 上把 LLM 放進 PredicateCPA refinement |
| [`SVCOMP26_PORTFOLIO_LLM_PLAN.md`](SVCOMP26_PORTFOLIO_LLM_PLAN.md) | v1.5.2+（tactical） | 仍在 reachability，但把 LLM 從 predicate 擴到 portfolio routing / budget / guard / hints（A–G 層） |
| **本文件** | v1.6 → v2.0 → exploratory | **跨 property category、跨 CPA domain、跨 task type(TRUE/FALSE)、跨 artifact(witness)、跨時間(offline learning)** |

目的不是現在就做，而是把「LLM 在 CPAchecker 這個 verifier 的可介入面」完整攤開，
每個方向標注 **soundness tier / 依賴 / 風險 / horizon**，讓之後挑方向時有地圖而不是臨時起意。

---

## 1. 統一守則：LLM 永遠只產生「待驗證候選」或「只影響資源/config」

整份地圖只允許兩種 LLM 介入，外加一條紅線。任何新方向都必須先歸到 Tier S 或 Tier R。

| Tier | 意義 | 錯誤後果 | 例子 |
|------|------|----------|------|
| **S — verified candidate** | LLM 給候選，sound checker 驗證後才採用 | 最壞只是浪費 CPU，**永不產生錯 verdict** | predicate、loop invariant、ranking function、witness invariant |
| **R — resource/config only** | LLM 只選策略 / budget / routing，verdict 由底層 CPA 決定 | 最壞只是選錯策略、效率差，**verdict soundness 不受影響** | portfolio routing、adaptive budget、stock-first guard、interleaving 優先序 |
| **X — forbidden（紅線）** | LLM 輸出被直接當事實相信 | 可能產生**錯 verdict** → 違反 SV-COMP soundness | LLM 直接判 TRUE/FALSE、LLM invariant 當 assumption 不驗證、witness 不過 validator 就採用 |

v1.5.1 的 predicate 介入是 Tier S（spurious predicate 只是沒用，不會讓 proof 出錯）。
本文件每個方向都會標 **[S]** 或 **[R]**；沒有任何方向可以是 X。

---

## 2. Portfolio 現實：六個 property branch，只碰了一個

`config/.../svcomp2x.properties` top config 不是單一 solver，而是依 property 分流（已逐行確認）：

```text
svcomp2x.properties
├── (reachability)      heuristicSelection.{singleLoop,loop,loopFree,complexLoop}Config  ← v1.5.x VGuide 只動這條的 predicate 元件
├── memorysafety.config   = …--memorysafety.properties      (SMG2: cpa.smg2.*)
├── memorycleanup.config  = …--memorycleanup.properties     (SMG2)
├── overflow.config       = …--overflow.properties          (predicate / bmc / value 組合)
├── datarace.config       = …--datarace.properties          (BDD / sequentialization)
├── termination.config    = …--termination.properties       (ranking-function termination algorithm)
└── svlib.config          = …--svlib.properties             (SoftwareSystems：大型真實碼)
```

**關鍵不對稱**：v1.5.1 只把 LLM hook 換進 reachability 分支的 predicate 元件。
其餘五個 property 分支 + svlib 分支，LLM **完全沒介入**。
這不是缺陷，是還沒探索的整片面積——而且 §4 會說明同一套 `svcomp26-vguide` 方法可以平移到任一分支。

---

## 3. 七個 broaden 維度

### 3.1 維度一：跨 property category（最大的未開發面）

每個 property class 都有一個「creative guess + 便宜驗證」的 LLM 切入點：

| Category | spec / config | 現有解法 | LLM 候選（Tier S 為主） | Tier | Leverage |
|----------|---------------|----------|--------------------------|------|----------|
| ReachSafety（現在） | `unreach-call` | PredicateCPA + portfolio | loop-head predicate（已做） | S | （baseline）|
| **Termination** | `termination` / `terminationAnalysis.properties` | ranking-function termination algorithm | **候選 ranking function / variant**；prover 驗 decrease+bounded | **S** | **最高** |
| MemSafety | `valid-memsafety`（deref/free/memtrack）, SMG2 | symbolic memory graph | pointer aliasing 假設、buffer/index bound、memory shape 候選 | S | 高 |
| NoOverflow | `no-overflow` | predicate/bmc/value | 變數 range / overflow-free invariant 候選 | S | 中 |
| MemCleanup | `valid-memcleanup`, SMG2 | symbolic memory graph | alloc/free pairing、leak-free 不變量候選 | S | 中 |
| Concurrency / DataRace | `no-data-race` | BDD / sequentialization | 哪些 shared var / lock / interleaving 重要；reduction 提示 | R/S | 中（高風險）|
| SoftwareSystems | `svlib.config` | 大型真實碼 portfolio | 函式 summary、相關變數子集、entry 假設候選 | S/R | 探索 |

**Termination 是最高槓桿的新 category，但它是 Class B（要建 hook，見 §4.2）**，理由：
- ranking function synthesis 正是 LLM 強項——「猜一個遞減函數」是創造性的，但**驗證極便宜**（prover 檢查 `f` 在 loop 內遞減且有下界）。
- 高槓桿 ≠ 免費：lasso/ranking 路（`lassoRankerAnalysis`）**沒有** VGuide 那種 predicate 注入點，要在 Java 寫一個「接受候選 ranking function + 交既有 prover 驗證」的 sound hook。
- 與 reachability predicate 互補：reachability 要 invariant（over-approx），termination 要 ranking function（well-founded）。

⚠️ **不是每個 category 都能像 reachability 一樣 config-only。** 只有已經在跑 VGuide 所 hook 的 ABEl
predicate-CEGAR refiner 的 branch（例如 **Overflow**）才繼承注入點、零 Java；ranking function / SMG memory
要各自建一個 sound 注入 hook。完整分級見 §4.2。

### 3.2 維度二：跨 CPA domain（predicate 以外的抽象域）

reachability 內部，LLM 也不必只服務 PredicateCPA：

| Domain | LLM 機會 | Tier |
|--------|----------|------|
| ValueAnalysis / Interval | 該精確追蹤哪些變數、interval/range 提示 | S/R |
| Octagon / Polyhedra（關聯域）| relational template 候選（`x-y<=c` 形狀）| S |
| Domain selection | 依 task feature 選抽象域（value vs predicate vs interval）| R |
| Loop acceleration / summary | 候選 closed-form / loop summary，驗證後當 summary 用 | S |

意義：v1.5.x 證明了 LLM→predicate 有正增益，但 predicate 只是 portfolio 裡一個元件。
若 LLM 能對「該用哪個抽象域」給 routing（Tier R），等於介入 portfolio 更上游。

### 3.3 維度三：FALSE / counterexample / test-generation（現在只做 TRUE）

VGuide 目前 TRUE-oriented；`vguide.dualPromptMode=true` 已有 BUG prompt，但目前只當 diagnostics。
broaden 方向：

- **錯誤路徑候選 [S]**：LLM 提議具體 input / error path → 餵 symbolic execution 當 seed；任何具體 input 都會被 re-execution 驗證，不可能假陽性。
- **搜尋導引 [R]**：LLM 提示「往哪個 branch / 哪個 unrolling depth 找 bug」，只影響搜尋順序。
- **Test-Comp 外溢**：同一套 input-candidate 機制可服務 test generation（不同賽道，但共用基礎）。

這把 BUG prompt 從 diagnostic 升級成真正的 FALSE-task 助力，且仍 Tier S/R。

### 3.4 維度四：Witness / proof artifact（SV-COMP 評分的一部分）

SV-COMP 不只算 verdict，也算 correctness/violation witness 的可驗證性。
CPAchecker 已有 witness validation 管線（`correctness-witness-validation`、`violation-witness-validation`、`witness2test`、`*witnesses-k-induction`）。

- **Witness invariant 強化 [S]**：correctness witness 裡的 invariant **必須過 validator**，所以 LLM 補強 witness invariant 是 sound 的——validator 是 ground truth。
- **Witness 修復 [S]**：對 validator 拒絕的 witness，LLM 提議補強 annotation，再交 validator 判。
- **Witness→test [S]**：協助 violation witness 轉可執行 test。

價值：即使 verdict 不變，更強的 witness 也能提升分數與可信度，且風險低（一切過 validator）。

### 3.5 維度五：Offline 學習的 dispatcher / 跨年 generalization

整個 SV-COMP benchmark corpus 是公開且有 label 的——這是個 algorithm-selection 學習問題：

- **Learned dispatcher [R]**：用歷史 run 訓練「source feature → strategy」選擇器；LLM 當 feature extractor 或 router。對應 portfolio plan 的 A（pre-run advisor），但用 corpus-level 學習而非單題 heuristic。
- **Family hint library [S]**：portfolio plan §F 的 family templates 泛化到**所有 category**，離線 precompute、runtime 只查表（無 per-task 網路）。
- **跨年 generalization**：svcomp26 → 27 → 28 用 leave-one-year-out / leave-one-family-out 驗證，避免 overfit 到固定 764 set。

這條的產出可能不是 runtime LLM，而是一個**離線學到、runtime 純查表/純規則**的 dispatcher——對「比賽時無網路」特別重要（見 §3.6）。

### 3.6 維度六：模型 / 成本 / on-device（比賽現實）

SV-COMP 正式跑通常**網路隔離 + 嚴格 CPU/wall limit**，這直接約束 LLM 用法：

- **離線 precompute**：family hint / dispatcher 在賽前算好，runtime 不呼叫 API（呼應 §3.5）。
- **本地 / 蒸餾模型**：把 predicate/ranking-function 提案能力蒸餾到可離線跑的小模型。
- **Budget-aware 排程**：現有 `llmMinIntervalSec` / `maxLlmRoundsPerAnalysis` / `wallBudgetSec` 已是雛形；要擴成「在 portfolio 總 CPU budget 下，LLM 呼叫成本可被 accounting」。

不解決這條，前面所有 runtime-LLM 方向都只能算 research demo，不能進正式 submission。

### 3.7 維度七：研究基礎建設（讓上面可行的閉環）

承 portfolio plan §G（log-to-strategy），泛化成一個**封閉研究 loop**：

- attribution / ablation harness（已有 `attribute_svcomp_verdicts.py`，擴成 per-category）。
- regression dashboard：per-family / per-category new vs lost，盯 0-wrong gate。
- **controlled-resource eval**：case study 已暴露 retry/resource sensitivity；長期要有 BenchExec 級、可重現、低 outer-parallelism 的量測模式，否則 borderline delta 無法判定。
- LLM 自身當「實驗設計助手」[R]：讀 logs/attribution 自動提下一組 ablation。

---

## 4. 怎麼泛化：泛化的是「soundness 角色」，不是 config recipe

⚠️ 先更正一個直覺陷阱：把 v1.5.1 的成功想成「一套 config 平移到別的 branch」。**不是。**

reachability 之所以「不用改 Java」，是因為 LLM→engine 的**注入點早就存在**——VGuide 把 predicate
注入 `PredicateCPA` 的 CEGAR refinement，hook 在 `PredicateCPARefinerFactory`，由
`cpa.predicate.refinement.useVocabularyGuide` 開。其他五個 branch「沒被碰」**不是因為沒人寫 config，
而是因為多數根本不跑 predicate-CEGAR**，所以沒有同一個 hook 可 flip。
「平移 recipe、多數不用改 Java」剛好說反了：那個「不用改 Java」是 reachability 的特例，不是通則。

真正會泛化的是**soundness 角色**，不是 config：

> LLM 當 **verified-candidate provider**：提出候選，**既有 sound engine 驗證後才採用**。

這個角色在每個 engine 的「候選 artifact」不同，而**注入點存不存在**才是 feasibility 的關鍵變數：

| Engine 範式 | 候選 artifact | 驗證者 | 注入點現況 |
|---|---|---|---|
| predicate-CEGAR | predicate | interpolation / refinement | **已存在**（VGuide hook）|
| ranking-function（lasso）| ranking function | decrease + bounded 證明 | 無 → 要建 |
| SMG memory | memory invariant / aliasing 假設 | SMG2 一致性 | 無 → 要建 |
| concurrency | （多半無 verified-candidate，只有 routing）| — | 不適用 / Tier-R |

### 4.1 Feasibility 分級（v1.6 的第一個動作就是把五個 branch 歸類）

- **Class A — 注入點可繼承**（config-only）：該 branch 的 portfolio 已在跑 VGuide 所 hook 的同一個 ABEl
  predicate-CEGAR refiner → 直接在那個 predicate 元件 flip `useVocabularyGuide=true`，**零 Java**。
  剩下成本只有 prompt / ContextPack 語意要從 reachability 改成該 property；而且注入機制本身 Tier S，
  最壞只是 predicate 沒用，不會錯 verdict。
- **Class B — 要建新的 sound 注入 hook**（Java）：engine 的 native artifact 不是 predicate-CEGAR 的 predicate
  （ranking function、memory invariant）→ 必須在 Java 寫一個「接受外部候選 + 交既有 prover 驗證」的 hook。
  **這才是真正成本，且每個 engine 範式各寫各的。**
- **Class C — 無 verified-candidate artifact**：LLM 最多做 Tier-R routing/reduction 提示，沒有可注入的待證候選。

### 4.2 五個 branch 的 grounded 分級（已逐檔確認注入點）

| Branch | 候選 artifact | 繼承 predicate-CEGAR hook？ | Class | 主要成本 |
|---|---|---|---|---|
| **Overflow** | bound / range predicate | **是**——其 predicate 元件 `#include predicateAnalysis-PredAbsRefiner-ABEl.properties`，與 reachability vguide **同一個 refiner** | **A** | config + prompt 語意；待確認 overflow portfolio 實際 route 多少進該 predicate child |
| Termination（safety-reduction 路）| safety 編碼的 predicate | 可能——`terminationToSafety` 走 PredicateCPA | A?（待確認其 refiner 即 VGuide hook 的那顆）| config + 確認 refiner |
| **Termination（lasso 路）** | **ranking function** | 否——`lassoRankerAnalysis`，非 predicate-CEGAR | **B** | **新 sound ranking-function 注入 hook**（最高槓桿）|
| MemSafety / MemCleanup | memory invariant / aliasing | 否——SMG2 | B | 新 sound memory-invariant 注入 hook |
| DataRace | （interleaving / reduction 提示）| 否——BDD / sequentialization | C | 無待證候選，只 Tier-R |

所以「泛化」其實有兩種命運：**Overflow（+ 可能 termination 的 safety 路）幾乎免費繼承注入點**；
**ranking function / SMG memory 要各自建一個 sound 注入 hook**——後者才是 v2.0 的真實工作量，跟 config 無關。

### 4.3 更正後的進場流程（feasibility-first，不是 baseline-first）

1. **先問注入點**：這個 branch 的 verified-candidate artifact 是什麼？注入點存在嗎？
   （grep「有沒有跑 VGuide hook 的那顆 ABEl refiner」就能分 A vs B。）
2. **A/B/C 歸類**：決定是 config-only 還是要寫 Java hook，以及該 branch 值不值得做。
3. **只對可行 branch** 才建同時限 stock baseline（FULLSET §0 的教訓仍成立，但它是第 3 步、不是第 1 步；
   對連注入點都沒有的 branch 先建 baseline 是浪費）。
4. 建 scoped `*-vguide` variant（Class A）或先做注入 hook 的 PoC（Class B）。
5. soundness-first：0 wrong → attribution → new/lost。
6. 最後才 tune。

跟原本那條 recipe 的關鍵差異：原本把「config plumbing」當主成本，真相是
**Class A 的 config 幾乎免費、Class B 的 Java hook 才是主成本**，而分到 A 還是 B 完全由「注入點是否已存在」決定。

---

## 5. Horizon 排程（依賴與風險）

| Horizon | 主題 | 項目 | 進場 gate |
|---------|------|------|-----------|
| **v1.5.2（現在）** | 收緊 reachability predicate portfolio | adaptive budget ablation、stock-first guard、SAFE-only injection | 見 `SVCOMP26_PORTFOLIO_LLM_PLAN.md` P0–P1 |
| **v1.6** | **跨 branch 泛化 feasibility 研究** | 把 5 個 branch 做 §4.2 的 A/B/C 分級；**Overflow Class-A scoped variant**（config-only，最快實證泛化）；確認 termination safety-路的 refiner；輸出每個 Class-B 的 hook scope。可並行 reachability 內 broaden（§3.2 domain routing[R]、§3.4 witness invariant[S]）| 需 v1.5.2 predicate 層已穩；每個 Class-A branch 需同時限 baseline |
| **v2.0** | 建 Class-B sound 注入 hook | **Termination lasso 路 candidate ranking-function hook[S]（最高槓桿）**、MemSafety memory-invariant hook[S]、§3.3 FALSE-task seeding[S] | 需 v1.6 矩陣判定該 branch 值得；需新 Java + per-engine 驗證 |
| **exploratory** | 跨 corpus 學習 | §3.5 learned dispatcher[R]、跨年 generalization、§3.6 離線/本地模型 | 需 §3.7 harness 成熟、需離線 precompute 管線 |

排序理由：先把已證明有效的 predicate 層收緊（v1.5.2），再在同 category 內擴介入點（v1.6），
再開新 category（v2.0，Termination 先因為驗證最便宜、LLM 最擅長），最後才是高成本的 corpus-level 學習。

---

## 6. 風險守則與 non-goals

**守則**

1. **Soundness 永遠是 gate**：每個方向上線前的硬條件是 **0 wrong verdict**；Tier S/R 是設計層保證，0-wrong 是驗收層保證。
2. **不 overfit**：不對固定 764 set 調到死、不 hard-code 單題 replay；用 leave-one-family/year-out。
3. **Single-run 現實**：正式執行沒有外部 retry，所有策略必須在一次 execution 內成立（呼應 portfolio plan §0）。
4. **比賽約束優先**：任何 runtime-LLM 方向都要先回答「網路隔離 + CPU limit 下怎麼跑」（§3.6），否則只是 demo。
5. **保守 claim**：增益要可 attribution、可重現；resource-sensitive delta 標清楚、不當 runtime 能力宣稱。

**Non-goals（紅線）**

- LLM 直接給 verdict（Tier X）。
- LLM invariant / ranking function 不經 prover 驗證就當 assumption（Tier X）。
- witness 不過 validator 就採用（Tier X）。
- 為了 +1 題做 detection evasion 或踩比賽規則灰區。

---

## 7. 一句話總結

v1.5.1 證明了**一個 branch（reachability）× 一個元件（predicate）× 一種 task（TRUE）**上，
LLM 當 verified-candidate provider 有正增益。
這份地圖的命題是：同一個 soundness 安全的**角色**（verified-candidate provider），可以平移到**其餘五個
property branch、其他抽象域、FALSE task、witness、以及離線 corpus 學習**。
但泛化的是角色（§1 的 S/R/X），**不是 config recipe**——能不能泛化、要多少 Java，由 §4 的
「注入點是否已存在」分級決定：Overflow 幾乎免費繼承，ranking function / SMG memory 要各建一個 sound hook。
