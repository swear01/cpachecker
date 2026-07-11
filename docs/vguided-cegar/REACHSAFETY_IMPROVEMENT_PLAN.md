# ReachSafety 提升計畫（止血優先）

> **狀態:本探索階段 PAUSED 於 v1.7.1(2026-06-20)。** A1 = v1.7.0 stock-first + v1.7.1 peel 觸發器①,都已實作並設預設。
> 完整 764 `svcomp27-vguide`(只換 schedule/peel):old 482 → **493** → **504**(**累積 +22 / 0 wrong**)。
> **cheap LLM-on-predicate 槓桿已用盡。** 階段總結(含 nla-digbench 非線性 out-of-scope、FALSE/fuzzing 調查):
> [`reports/2026-06-20_reachsafety_exploration_summary.md`](reports/2026-06-20_reachsafety_exploration_summary.md)。
> 這裡的 nonlinear「out-of-scope」只指既有 PredicateCPA injection mechanism。後續
> [`VGUIDE_NLA_PLAN.md`](VGUIDE_NLA_PLAN.md) 曾以 polynomial search space + k-induction
> probe新 capability，但 exact-BV與 exact NIA oracle gate皆為 0/12，已於 2026-07-11 STOP。
> 個別報告 [stockfirst_guard](reports/2026-06-20_reachsafety_stockfirst_guard.md)、[peel_trigger](reports/2026-06-20_reachsafety_peel_trigger.md)。
> **已評估後砍/降優先**:A2 CPU 隔離(§3.2/§6)、nla-digbench 非線性、peel-aware prompt、FALSE/bug-finding(CPAchecker 無 fuzzer)。
> 再投需**新能力**(非線性合成 / k-induction 新注入點 / execution-based bug-finding),皆高成本。

目標：把 reachability / Loops 的 predicate 注入這塊的 solve 數再往上推。
承接 [`reports/2026-06-14_svcomp26_vguide_case_studies.md`](reports/2026-06-14_svcomp26_vguide_case_studies.md)
與 [`SVCOMP26_PORTFOLIO_LLM_PLAN.md`](SVCOMP26_PORTFOLIO_LLM_PLAN.md)。

## 0. 範圍與前提

- **只談 reachability / Loops 的 predicate 注入**（`PredicateCPA` CEGAR refinement 那條）。
- **不考慮競賽限制**：網路隔離、single-run no-retry、offline/distilled model、family hint cache 等
  「為了 SV-COMP 正式跑」而生的方向，本計畫一律不做。研究目標是純粹提高 764-task set 的 solve 數，
  允許 runtime LLM、允許重跑量測。
- **唯一不變的 gate：0 wrong verdict**（Tier S/R/X 守則，見 [`LLM_RESEARCH_ROADMAP.md`](LLM_RESEARCH_ROADMAP.md) §1）。
  止血用的機制全是 **Tier R**（只動「跑什麼元件、何時跑」），不碰 verdict。

## 1. 現況分解：net = new − lost

| 量測 | 數字 |
|------|------|
| Loops ReachSafety 764（isolated） | stock 486 → vguide 493 = **+7 net** |
| 拆解 | **+17 new − 10 lost** |
| Competition-grade combined（參考） | +15 |
| Win 的機制 | stock 數十次 refinement → vguide **2–4 次**（打破 CEGAR 不收斂） |

**關鍵洞察（case study + 論文 ablation 都確認）**：剩下的差距**不是 predicate 品質問題**，
cheap levers 已用盡——
- prompt **+0**：加 context／指令會讓模型退步（plain source + CE context 最好）；
- adaptive budget：full-set 只剩邊際，且可能增加 precision pollution。

真正卡住的是 **portfolio 動態 + noisy-but-correct predicate**，不是「predicate 不夠好」。

## 2. 為什麼「止血」是最高 CP 的第一刀

「止血」= 把 **−10 lost** 救回來。理由：

1. **同一組 wins 下的免費上漲。** lost 全是 stock 本來就會解、被 VGuide 弄丟的 baseline 題。
   救回它們**不需要任何新 LLM 能力、不需要新注入點**：同樣 17 個 win,net 從 **+7 → 最多 +17**（翻倍以上）。
2. **soundness 不受影響。** 止血機制全是 Tier R（只決定哪個元件跑、何時 fire），verdict 仍由底層 CPA 決定，
   **0-wrong gate 不動**。
3. **已有診斷。** case study 已把 10 個 lost 分成兩類：**~5 個 resource-sensitive + ~5 個真 regression**。
   知道確切要修什麼,不是盲猜。

對比之下,推 new solves 天花板（§5 的 B 方向）要新 Java hook、不確定性高;止血是 config/routing 層、
高信心、低成本——所以**先止血**。

## 3. 兩個出血點（grounded）

### 3.1 出血點 A：noisy-but-correct predicate regression（~5,`nested-3` 型）

**證據**

| Task | stock | vguide full-set | 說明 |
|------|-------|-----------------|------|
| `nested-3` | TRUE,**2 refinements / 1.278s** | **UNKNOWN,41–42 refinements / 56s** | LLM 注入互斥等式（`st==0` 與 `st==1` 各一條）,把 refinement trajectory 炸開 |
| `sum_by_3` | TRUE,8 ref / 2.236s | UNKNOWN,6 ref / 61s（重跑可回 TRUE） | 同 config 重跑能解 → 非語意 regression,是被干擾 |

**根因**：VGuide 在**第一個 spurious CE** 就 fire,搶在 stock interpolation 找到它原本會找到的乾淨小
predicate set 之前。注入的 predicate **不是錯的**（個別都成立）,但擴大了 predicate vocabulary,改變了
refinement 軌跡。本質上是「LLM 去幫一個根本不需要幫的題,而且越幫越糟」。

**win/loss 第一眼的邊界像是 refinement count**：win 是 stock 要跑**數十次**的題（`count_up_down-1` 69 次、
`overflow_1-1` 86 次）;loss 是 stock **2 次**就解掉的題（`nested-3`）。但 count 只是表象——真正的判準是
**發散行為(peel)而非次數**(見 A1.1),且還要加上時間軸(見 A1.2),才能涵蓋「少次但很貴」的題。

**修法（A1）：雙軸觸發的 stock-first guard**

目前的開火決策只看次數：`LlmCallScheduler.shouldCall(int refinementIndex)`,default `FIRST_SPURIOUS`
在 `refinementIndex == 1` 就開火——這就是 `nested-3` 中槍主因。改法不是「等 K 次」(K 次是錯的軸:
若每次 refinement 很貴,等 K 次會等到 budget 燒光、LLM 永遠輪不到),而是把開火條件改成**對「收斂/發散」
與「時間壓力」雙軸判斷**。

#### A1.1 「不收斂」的操作型定義

收斂 = refinement 加的 predicate 會 **generalize**,讓 ARG 達 fixpoint。
發散 = 每次只砍當前那條 CE,典型是**把 loop 多攤開一圈**(interpolants 變成只差常數的序列),抽象永不收斂。
→ **「不收斂」= refinement 在「攤開 loop」而不是「關閉 ARG」。** 次數本身不是訊號,**peel 行為**才是。

#### A1.2 兩個觸發器,OR（誰先到算誰）

開火 = **觸發器①(發散) OR 觸發器②(時間)**,兩者都再過 A1.3 的 budget veto 與 `maxLlmRoundsPerAnalysis` 上限。

| 觸發器 | 條件 | 抓哪種卡住 | 訊號來源（皆現成）|
|--------|------|-----------|-------------------|
| **① 發散(次數/peel)** | `refinementIndex ≥ K` **∧** CE 的 loop-head 攤開次數在最近 R 輪嚴格遞增 | 多次便宜 refinement 在 peel | `abstractionStatesTrace` + 既有 `LoopHeadIndex`;(升級版)`getInterpolants()` 比對「同變數只換常數」 |
| **② 時間(每 D 秒一次)** | 距上次 LLM call（首次則距 analysis 起點）≥ **D 秒** 就觸發一次 | **少次但每次很貴**,refinement 稀疏 → 不靠次數,純看 wall-clock,到點就開火 | 既有 `llmMinIntervalSec` / `LlmCallScheduler.matchesIntervalSchedule` + `WallClockBudget.analysisStartMs` |

觸發器② = 「執行多久就觸發一次 LLM」:**每 D 秒開一次**,與 refinement 次數脫鉤,專門救「少次但很貴」的題;
第一輪沒幫上,下一個 D 秒會再開一次(受 max rounds 限制)。

**為什麼 `nested-3` 仍不會中槍**:它 1.3s / 2 refinements 就**收斂出 TRUE**——D 設成數秒以上時觸發器②還沒到、
觸發器①的 K + peel 也沒成立,**在兩個觸發器跳之前它已經贏了**。排除依據是「它已做完」,不是「次數少」。

> 註:觸發器②的 interval 機制**已存在**(`llmMinIntervalSec` / `MIN_INTERVAL` schedule),但目前
> (a) `refinementIndex == 1` 會自動開火、(b) `lastLlmCallMs == 0` 時立刻開火(等於不等 D)、
> (c) 是互斥的 enum mode,不能跟發散觸發器 OR。本計畫把它改成:**首次開火也要等 D**(從 analysis 起點量),
> 並與觸發器① **OR 組合**,而非互斥。

#### A1.3 「留夠 budget」= 兩個觸發器共用的上界 veto

「留夠 budget」的意思:LLM 開火會吃掉剩餘時間的**兩段**——(a) API call 本身的 latency、(b) 拿到 predicate
後 CEGAR **還要再跑幾輪 refinement** 才能關閉 ARG 吐 TRUE。太晚開火 → call 超時、或沒時間收尾 → 白花。

所以不管哪個觸發器跳,開火前都要過 `WallClockBudget.hasRemainingForLlm()`:它算
`remaining = budget − elapsed − llmUsed`,要求 ≥ `MIN_MS_FOR_LLM (15s)`(bridge 第 313 行已在用)。意涵:
- 觸發器②的 **D 不能設太大**,否則會撞上 15s 否決線、永遠來不及開;D 要明顯小於單題 budget。
- 若某題貴到 **D 還沒到、就已剩 <15s**(一次 refinement 直接跨過整個窗口)→ 序列式觸發無解;
  這種就是 A1.4 並排會解、但目前不做的 case(見下)。

#### A1.4 並排 stock∥vguide —— 暫不做（太難 / 未實作）

理論上「窗口太窄」的病態題(D 還沒到就剩 <15s)可用 parallel stock∥vguide child 繞過時序決策
(LLM 自己 child 立刻開火、stock 隔壁同時跑,provable 0 predicate-regression)。但:
- **目前 vguide config 是「取代」不是「並排」**:portfolio 的 predicate child 已被換成 vguide 版
  (parallel 清單裡只有 `…-vguide--…-predicateAnalysis`,沒有 stock predicate),這正是 predicate regression 會變 loss 的結構主因;
- 並排 = 把 stock predicate child 加回 parallel 清單(config-only 一行),但**目前無此 config、無 ablation 驗證**,
  且多拆一個 child 會**惡化 portfolio CPU starvation**;
- 成本/風險 vs 它只救「窄窗病態題」這一小群 → **暫不做**。先靠 A1.2 兩觸發器涵蓋絕大多數;
  若 observe-only(A1.5)顯示窄窗題佔比夠大,再回來評估。

#### A1.5 實作步驟（phased）

1. ✅ **時間觸發器②(`EVERY_N_OR_INTERVAL`)** — 已實作(2026-06-20)。`LlmCallSchedule` 新增
   `EVERY_N_OR_INTERVAL`;`LlmCallScheduler.shouldCall` 對該 mode =
   觸發器①(every-N floor:在 #N、#2N… 開火,**不在 #1**) **OR**
   觸發器②(沿用 `llmMinIntervalSec` 的 interval,改成**首次也等 D**、從 analysis 起點量,拿掉 #1 自動開火)。
   為可測試注入了 clock;單元測試在 `LlmCallSchedulerTest`。
2. ✅ **發散偵測(觸發器①的 peel)= v1.7.1** — `countLoopHeadVisits` 在 `onSpuriousBeforeRefinement` 數 CE
   經過 loop head 次數;`peelFire`(scheduler)= refinement ≥2 ∧ `loopHeadVisits ≥ peelLoopHeadThreshold`,
   折進 `every_n_or_interval` 第三個 OR branch。校準 threshold=4(收斂題 nested-3 峰值 3、發散題在 #2–4 跨 4)。
3. ✅ **校 threshold = 4**(observe-only LLM-off 校準 + 764 A/B 驗證,見下)。
4. (A1.4 並排暫不做。)

> 實作現況(2026-06-20):**A1 兩步都完成、單元測試 12/12**。完整 764 `svcomp27-vguide`(只換 schedule/peel):
> - v1.7.0 stock-first(`every_n_or_interval` K=10/D=15s):482 → **493**(+11 / 0 wrong);
> - v1.7.1 peel(`peelLoopHeadThreshold=4`,早開火):493 → **504**(+11 = +18 new − 7 lost / 0 wrong)。
> - **累積 +22(482→504),0 wrong**。
>
> 兩者都已設為 `config/vguide.properties` 預設。peel 把 v1.7.0 那 6 個 #1-need 回歸(`heapsort`/`nested9` 等)
> 救回。v1.7.1 的 −7 是 resource-sensitive noise → **不處理**(A2 已評估後砍,見 §3.2/§6)。報告
> [`...stockfirst_guard.md`](reports/2026-06-20_reachsafety_stockfirst_guard.md)、
> [`...peel_trigger.md`](reports/2026-06-20_reachsafety_peel_trigger.md)。

#### A1.6 邊界（誠實）

有些題每次 refinement 貴到**LLM 換上完美 predicate 也來不及在時限內收尾**(瓶頸是 abstraction blowup,
非 predicate 品質)→ **任何排程都救不回**,歸「structurally out of reach」,別為它們過度工程化 guard。

全程仍是 **Tier R**:只改「何時 fire」,predicate 一樣要 SMT 驗證,**0-wrong 不動**。

### 3.2 出血點 B：portfolio CPU starvation —— **評估後砍（A2, 2026-06-20 結案）**

現象:`freire1`(kInduction)、`prodbin`/`nested_5`(symbolicExecution)等被 VGuide 搶 CPU 而丟、重跑又解回。
根因(已確認):portfolio 是 5-child 並行、**共用一個全域 CPU 限**(`ParallelAlgorithm` 無 per-child 上限),
VGuide 的 predicate child 多燒 CPU → 會解的 sibling 拿不到足夠 CPU → UNKNOWN。

**決定不做。** 理由:
- race 是 CPAchecker portfolio 的**標準機制**,vguide 只把 predicate child 換成較重的版本,**沒壞、0-wrong 不受影響**。
- VGuide 的「貪」是**同一枚硬幣兩面**:多燒 CPU 正是贏下 +18 的原因;同樣的多燒在贏不了的題上才擠到 sibling。
  runtime 分不出「會贏」vs「該讓位」,鈍的上限會**連 +18 一起砍**(可能淨負),progress-aware 版又複雜。
- −7 是 **resource-sensitive noise**(run 間會跳),ROI 低、量測吵。v1.7.1 的 **+22 / 0-wrong** 已是乾淨收手點。

## 4. 驗收與量測

- **先做 targeted `new ∪ lost` ablation**：把每個 delta 分類成 stable / resource-sensitive / config-sensitive,
  確認假設（A 已驗證修 regression;resource-sensitive 的部分歸 §6 不做）。
- **full-set acceptance**：**0 wrong** + **lost < 10**（目標把 lost 壓到 0–3）+ new 不掉。
- 因為存在 resource-sensitivity,borderline delta 用**較低 outer-parallelism / BenchExec** 量,避免 wall
  contention 汙染——這是量測嚴謹,與競賽無關。

## 5. 止血之後：推 new solves 天花板（次階段,Tier S）

止血只把 net 推到 ~+17（現有 win 集合的上限）。要超過,得開**新注入點**：

| 方向 | 機制 | Tier | 成本 |
|------|------|------|------|
| ~~**B1 — k-induction / IMC 候選 invariant**~~ | **Rejected by final oracle-capacity gates（2026-07-11）**：ordinary KI、conjunctive KI-PDR與direct PDR均0/12 delta；只保留test-only oracle loader，不做LLM hook | S | 不執行 |
| **B2 — predicate 以外抽象域 routing/hints** | value / interval / octagon 的 relational template 候選或 domain 選擇 | S/R | 中–高 |

這些要新 Java hook、不確定性高,**等止血數據出來再評估值不值得**。

## 6. 明確不做

- ❌ prompt engineering / 加 context（ablation 證明退步）。
- ❌ 加大 predicate budget（full-set 邊際 + precision pollution）。
- ❌ 競賽導向方向：offline candidate cache、distilled/local model、網路隔離適配、把「single-run no-retry」
  當硬限制——本計畫不考慮競賽。
- ❌ **A2 portfolio CPU 隔離(2026-06-20 砍)**:race 是標準機制、沒壞;capping VGuide 會連贏下的 +18 一起砍
  (同一枚硬幣兩面),−7 又是 resource noise,ROI 低、量測吵。詳見 §3.2。
