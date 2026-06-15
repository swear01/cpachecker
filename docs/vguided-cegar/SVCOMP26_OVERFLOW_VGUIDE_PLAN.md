# v1.6 generalization 計劃：svcomp26-overflow-vguide（Class-A，config-only）

目標：用**最低成本、零 Java、零 prompt 改動**，驗證 v1.5.1 在 reachability 證明的
predicate-CEGAR LLM hook 能不能**直接泛化到第二個 property branch（NoOverflow）**。
這是 [`LLM_RESEARCH_ROADMAP.md`](LLM_RESEARCH_ROADMAP.md) §4.2 中唯一的 **Class-A** branch，
所以是「簡單、能泛化」的最小一刀。承接 [`SVCOMP26_VGUIDE_FULLSET_PLAN.md`](SVCOMP26_VGUIDE_FULLSET_PLAN.md) 的方法論。

日期：2026-06-15。Branch：`svcomp-integration`。

**研究問題**：同一個 `useVocabularyGuide` hook，**不改 Java、不改 prompt**，套到 overflow 的 predicate 元件上，
會不會 (a) 真的 fire、(b) 0 wrong、(c) 至少救回幾題 stock 沒解的 overflow？
- yes → Class-A 泛化**實證成立**，方法可複製到其他 Class-A。
- fire 但沒贏 → 第一個 finding：「overflow 需要 prompt/context 適配」——仍遠比 Class-B 便宜，且把「config-only 夠不夠」問清楚。

---

## 0. 為什麼 overflow 是「簡單能泛化」的唯一目標（grounded）

1. **Class-A（注入點可繼承）**：overflow 的 predicate 元件
   `config/components/predicateAnalysis--overflow.properties` 內
   `#include ../includes/predicateAnalysis-PredAbsRefiner-ABEl.properties`
   ——與 reachability vguide predicate 元件**同一顆 ABEl refiner**，正是 VGuide hook 落點
   （`PredicateCPARefinerFactory` 讀 `cpa.predicate.refinement.useVocabularyGuide`）。flip 一個 option 就生效，**零 Java**。
2. **predicate child 在 overflow 更顯眼**：`config/components/parallel-overflow.properties` 只並行 **2 個** child
   （`predicateAnalysis--overflow` + `valueAnalysis-overflow--parallel`），不像 reachability 的 5-way。
   predicate 是 1-of-2 → VGuide 影響面比 reachability 更大。
3. **property-agnostic 假設**：VGuide 在 refinement 層看到的是 **spurious counterexample + program**，
   提 predicates 去 refute 那條不可行路徑；這在 refinement 層與「目標是 unreach-call 還是 no-overflow」無關。
   所以理論上同一套 machinery / prompt 不改就能用。§5 smoke test 驗證這點。
4. **chain 已存在**：svcomp26 已有完整 overflow portfolio（§1），不必新建，只做 3 個 scoped 變體。

---

## 1. 已驗證的繼承鏈（grounded）

```text
config/unmaintained/svcomp26.properties            (overflow.config = svcomp26--overflow.properties)
 └─ config/unmaintained/svcomp26--overflow.properties   (specification = ../specification/sv-comp-overflow.spc)
      restartAlgorithm.configFiles:
        ├─ ../components/parallel-overflow.properties               ← 主分析（2-way parallel）
        │     ├─ predicateAnalysis--overflow.properties             ← #include ABEl refiner = VGuide hook 落點 ★
        │     └─ valueAnalysis-overflow--parallel.properties
        ├─ ../predicateAnalysis-bam-rec--overflow.properties::if-recursive   ← recursion → BAM fallback（vguide off）
        └─ components/svcomp26--concurrency-overflow.properties::if-concurrent
```

★ = 唯一要 flip 的點；其餘逐字保留官方檔。recursion 走 BAM（Java guard 與 config 版本無關，沿用 svcomp26-vguide 既有驗證）。

---

## 2. 要建的 3 個 scoped 變體（全在 `config/unmaintained/`）

| 新檔 | 來源官方檔 | 改動 |
|---|---|---|
| `config/unmaintained/svcomp26-overflow-vguide.properties` | `svcomp26--overflow.properties` | 複製；`restartAlgorithm.configFiles` 第一項改指 `components/svcomp26-overflow-vguide--parallel-overflow.properties`；recursion / concurrency fallback 與 spec 不變 |
| `config/unmaintained/components/svcomp26-overflow-vguide--parallel-overflow.properties` | `config/components/parallel-overflow.properties` | 複製；predicate child 改指 `svcomp26-overflow-vguide--predicateAnalysis--overflow.properties`；value child 不變 |
| `config/unmaintained/components/svcomp26-overflow-vguide--predicateAnalysis--overflow.properties` | `config/components/predicateAnalysis--overflow.properties` | **不改原邏輯**，只疊 vguide：見下方 3 行 |

predicate 變體內容（疊在官方 overflow predicate 之上，不重寫其 ABEl include）：
```properties
#include ../../components/predicateAnalysis--overflow.properties
#include ../../vguide.properties
cpa.predicate.refinement.useVocabularyGuide = true
```

⚠️ 路徑 checklist（FULLSET §2 同樣 footgun；overflow 因原檔在 `config/components/` 而非 `unmaintained/components/`，更要小心）：
- 新 predicate 變體在 `unmaintained/components/`；include 官方 overflow predicate 用 `../../components/predicateAnalysis--overflow.properties`。官方檔**自身**的 `../includes/…` 相對它自己的位置 `config/components/` 解析，仍正確（CPAchecker #include 相對「含該 include 的檔」）。
- vguide include = `../../vguide.properties`（unmaintained/components → config/，與 reachability svcomp26-vguide 一致）。
- top 變體第一項用 `components/svcomp26-overflow-vguide--parallel-overflow.properties`（相對 unmaintained/）。
- 每檔複製官方原檔的 SPDX header（REUSE/license CI 會檢查）。
- 只改「指向 vguide 變體」那幾行，其餘逐字保留。
- **smoke test 必須確認 ABEl refiner 真的被 load**（log 出現 predicate refinement + VGuide round），否則路徑錯會讓 hook 靜默不生效。

---

## 3. Runner：加兩個 mode

`scripts/vguided-cegar/run.sh`（平行於現有 svcomp26-vguide，參 `run.sh:99,134-154`）：

```text
svcomp26-overflow)        VGUIDE_SVCOMP=1
                          VGUIDE_CONFIG=config/unmaintained/svcomp26--overflow.properties
                          VGUIDE_SPEC=$REPO/config/specification/sv-comp-overflow.spc
                          # stock baseline；不 require_api
svcomp26-overflow-vguide) require_api; VGUIDE_SVCOMP=1
                          VGUIDE_CONFIG=config/unmaintained/svcomp26-overflow-vguide.properties
                          VGUIDE_SPEC=$REPO/config/specification/sv-comp-overflow.spc
```

- require_api 清單（`run.sh:99`）只加 `svcomp26-overflow-vguide`（baseline overflow 不需 API）。
- `run_benchmark_set.sh` 的 SVCOMP_MODE config-name 偵測擴充涵蓋 `*svcomp26-overflow*`（svcomp 模式**不**傳全域 `useVocabularyGuide`，避免污染非 predicate 元件）。既有 mode 行為不得變。
- `bash -n` 通過。

---

## 4. Benchmark set：建 overflow manifest（目前完全沒有）

現有 manifest 都是 reachability/loops；overflow set 要新建。來源 = 官方 `.set`：

- `NoOverflows-BitVectors.set`：`signedintegeroverflow-regression/*`(15)、`termination-crafted/*`(≤117)、`termination-crafted-lit/*`(≤159)、`termination-numeric/*`(≤22)
- `NoOverflows-Other.set`：`recursive/*`(≤27)、`recursive-simple/*`(≤77)、`bitvector/*`(≤70)、`psyco/*`(≤11)、`loop-zilu/*`(≤53)

建檔（manifest 格式同 loops：`path # yml=… expected=…`，root `$HOME/sv-benchmarks/c`）：

- `docs/vguided-cegar/benchmark_sets/no_overflow_scalar.list`：解析上述 glob，**過濾 .yml 宣告 `properties/no-overflow.prp` 的**，記錄該 property 的 `expected_verdict`。實際題數 build 時定（上界 551；多數 dir 是多 property，filter 後遠少於上界）。
- `docs/vguided-cegar/benchmark_sets/no_overflow_pilot.list`（**先跑**）：`signedintegeroverflow-regression/*`（15 題、100% no-overflow、canonical regression，TRUE/FALSE 都有）。最快證 hook 在 overflow fire + 0 wrong。

註：`recursive*/*` 會 route 到 `predicateAnalysis-bam-rec--overflow::if-recursive`（BAM fallback、vguide off）。保留無妨（soundness 已驗），但不貢獻 vguide signal——分析時要排除在 "vguide-eligible" 子集外。

---

## 5. Smoke / 驗證階梯（建 config + manifest 後、跑 full 前；任一層不過就停修）

核心要先拆掉一個陷阱：**`parallel-overflow` 有 value child，可能搶先解掉、讓 predicate child 根本沒 refine、
VGuide 永遠不 fire**。所以先用 standalone 把「hook 能不能動」跟「portfolio 會不會路由到它」分開驗。

### 5.1 四層驗證階梯（每層 gate 下一層）

| Level | 跑什麼 | 回答 | Gate |
|---|---|---|---|
| **L0 hook isolation** | standalone predicate config（**1 題**，無 portfolio）| hook 在 overflow **能不能 fire + 能不能解**（無 portfolio 干擾）| fire & 正確 → L1 |
| **L1 portfolio routing** ★ | **完整 portfolio** config `svcomp26-overflow-vguide`（**1 題，同 L0 那題**）| portfolio **會不會真的跑到 predicate child、VGuide 在 portfolio 內 fire** | fire → L2 |
| **L2 pilot effectiveness** | `no_overflow_pilot` 兩 arm | 小批 **0 wrong + fire + ≥1 win**，可重複 | 達標 → L3 |
| **L3 full effectiveness** | `no_overflow_scalar` 兩 arm + attribution | 正式有效性（new/lost/direct wins）| 出報告 |

> **澄清「full / 完整 portfolio」**：指 **config 完整度**，不是 benchmark set。§5.1 的 L0/L1 與 §5.2 的 smoke A–E
> **都是單題**（各跑 1 題）：L1/B 用完整 portfolio config（predicate+value 並行 + restart chain），L0/A 只跑 standalone
> predicate。真正跑 set 的只有 **L2（pilot 15 題）/ L3（scalar NoOverflow）**。注意 L0/L1（要看 LLM fire）仍需
> `DEEPSEEK_API_KEY`，但單題成本極小。

L0 用的 isolation 小 config（只為 smoke，不進實驗 arm）：
```properties
# config/predicateAnalysis-overflow-vguide.properties
#include predicateAnalysis--overflow.properties
#include vguide.properties
cpa.predicate.refinement.useVocabularyGuide = true
```

### 5.2 具體 smoke 案例（題怎麼選 + 預期 log + pass）

**題怎麼選**：先跑 stock baseline pilot（`--mode svcomp26-overflow`），挑 stock 下 **UNKNOWN 或 refinement 很多的 TRUE**
overflow 題當 hook-fire 題——trivial 題 value child 秒解、predicate 不 refine、VGuide 不會 fire，測不到東西。

| Smoke | mode / config | 題 | 預期 log（real markers）| Pass |
|---|---|---|---|---|
| **A 隔離 fire** | standalone `predicateAnalysis-overflow-vguide` | 需 refine 的 TRUE overflow | `VGuide LLM round #`、`VGuide predicate budget tier=`、`VGuide precision-injected <n>`、`Verification result: TRUE` | VGuide fire 且 verdict 對 |
| **B portfolio routing** ★ | full `svcomp26-overflow-vguide` | 同 A 題 | predicate child 與 value child 都啟動；predicate refine；`VGuide LLM round #` 出現；理想：`…svcomp26-overflow-vguide--predicateAnalysis--overflow.properties finished successfully.` | **VGuide 在 full portfolio 內 fire**（= 確定路由到此元件）|
| **C FALSE 不誤判** | full `svcomp26-overflow-vguide` | 一題 expected=false | `Verification result: FALSE` == expected | 0 wrong（即使 VGuide fire 也不能誤判）|
| **D recursion** | full `svcomp26-overflow-vguide` | recursive overflow | BAM fallback WARNING、dump `enabled=0`、無 `VGuide LLM round`、不 crash | fallback 正常 |
| **E baseline 對照** | stock `svcomp26-overflow` | 同 A 題 | **無**任何 `VGuide` log；verdict（UNKNOWN/較慢）| 建立 counterfactual |

★ **B 就是「確定會 portfolio 到這個 tool」的測試。** 若 B 裡 value child 先解、predicate 沒 fire：**不是 fail，是 finding**——
代表這題 value 就夠，要換更難（需 relational invariant）的題；用 L2 attribution 找哪些題 predicate 才是 decider。

### 5.3 執行 log 必含訊號（valid run 的 checklist；缺項即無效或路徑錯）

每個 vguide 題的 log（`output/.../logs/<task>.log`）要能看到：

1. **Portfolio 路由**：predicate child（`…predicateAnalysis--overflow.properties`）與 value child 都被 ParallelAlgorithm 啟動 → 證 portfolio 有 dispatch 兩個 child。
2. **Hook active（路徑對）**：predicate child 有 refinement，且 `VGuide LLM round #` 出現 → 證 ABEl refiner 被 load 且 hook fire。**路徑錯時這行會靜默消失**——這是 footgun 偵測器。
3. **VGuide internals**：`VGuide predicate budget tier=`、`VGuide precision-injected <n>`；可能有 `VGuide reject L1/L2`（候選被濾）、`VGuide SMT check failed` / `VGuide AbstractionPredicate failed`（= **Tier S 驗證在擋壞候選，看到是好事，不是錯誤**）。
4. **Decision**：`<…predicateAnalysis--overflow.properties> finished successfully.`（deciding component）+ `Verification result: <V>`。
5. **Soundness**：verdict == .yml `expected_verdict`。
6. **Dump**（設 `VGUIDE_ANALYSIS_DUMP_DIR`）：per-task JSON 有 `enabled=1`、`llm_rounds>0`、`call_start_epoch_ms`（驗 `llmMinIntervalSec`）、注入的 predicate 清單。

---

## 6. Baseline + full-set 執行

overflow 沒有現成 baseline → **兩個 arm 都要跑**：`svcomp26-overflow`（stock）與 `svcomp26-overflow-vguide`。

- set：先 `no_overflow_pilot`，過了再 `no_overflow_scalar`
- timelimit 300s、parallel 6、heap 4000M（指令格式同 FULLSET §4，換 mode/set/out）
- nohup detached

---

## 7. 有效性分析：怎麼證明是 VGuide 造成的（不是 noise）

報告 `docs/vguided-cegar/reports/<DATE>_svcomp26_overflow_vguide.md`，因果歸因四步：

1. **Attribution gate**（`attribute_svcomp_verdicts.py`）：一題算「VGuide 有效解」要同時滿足
   `deciding_component = svcomp26-overflow-vguide--predicateAnalysis--overflow.properties` **且** `llm_rounds > 0`。
   - 工具的 `verdict`（`Verification result:`）/ `deciding_component`（`… finished successfully.`）/ `llm_rounds`（`VGuide LLM round #`）的 regex **property-agnostic，對 overflow 直接可用**（已確認）。
   - ⚠️ 但 `selection_branch` / `restart_stage` 是 reachability 專用（singleLoop/bmc…），對 overflow 會回 `unknown`，不影響核心三欄；要乾淨可加一個 overflow branch case（小改、選配）。
2. **Counterfactual**：同題 stock `svcomp26-overflow` = UNKNOWN 或明顯較慢 → 證 win 來自 VGuide，而非 portfolio 本來就會解。
3. **Predicate inspection**：從 dump 取該題 LLM 注入的 predicates，展示就是它們關掉 proof（比照 reachability case study 列出確切 predicate；overflow 期待看到 bound/range 型，如 `x <= INT_MAX`、`x + y` 不溢位的關係）。
4. **Stability（診斷，非 runtime）**：對 new∪lost 小批重跑，分 stable / resource-sensitive；沿用 FULLSET 診斷語意，**不**把多跑一次當 runtime 能力。

報告同含：**0 wrong 第一**（§5.3.5 硬驗每題 `expected_verdict`，overflow FALSE 題多，這關比 reachability 更關鍵；任何 wrong = blocker）、topline（stock vs vguide：TRUE/FALSE/UNKNOWN/Solved/Wrong/PAR-2）、overlap/delta（new/lost/disagreements/net）、prompt 適配觀察（LLM 給的若是 reachability 式 invariant 而非 overflow bound 且沒用 → 記為適配 finding）。

---

## 8. 結果判定矩陣（泛化成立 / 失敗 / inconclusive）

v1.6 的 claim 是「**hook 泛化是否成立**」，不是「+N 題」。對照 §5 階梯的觀察：

| 觀察 | 結論 | 動作 |
|---|---|---|
| **L0 isolation 就不 fire** | hook 沒接上（路徑 / config bug）| 先修，別往下跑 |
| **fire + 0 wrong + ≥1 direct LLM win** | **Class-A 泛化實證成立** | roadmap §4.2 標「已實證、可複製」；推進其他 Class-A |
| fire + 0 wrong + 0 win | hook 動但 predicate 對 overflow 沒用 | finding：「config-only 不足，需 prompt/context 適配」（仍是有效結論）|
| portfolio 內 predicate 從不 decide（value 全搶先）| 這批題 value 就夠，hook 無從表現 | 換需 relational invariant 的更難題；inconclusive，非 fail |
| **任何 wrong verdict** | **blocker** | 停、查；Tier S 下理論不該發生，發生即真 bug，必究 |

最低達標線（宣稱泛化成立）：**0 wrong + 在 full portfolio 內 fire + ≥1 direct LLM-decided new solve**，且無大量 stable lost solves。

---

## 9. 風險 / 什麼會推翻假設

| 風險 | 症狀 | 緩解 |
|------|------|------|
| predicate child 在 overflow 很少 decide（value child 先解）| vguide 沒機會 fire | pilot 先看 attribution；必要時看 predicate-only 子集 |
| prompt 非 property-agnostic | LLM predicate 對 no-overflow 沒用 | 降級為「config + 小 prompt 改」，仍遠比 Class-B 便宜 |
| 路徑 footgun | ABEl refiner 沒 load、hook 靜默 | §5 step 1 專門擋；確認 log 有 refinement + VGuide round |
| overflow FALSE 題誤判 | wrong verdict | predicate 是 Tier S（over-approx 只會讓 proof 失敗、不誤判 FALSE）；§7.1 硬驗 |

---

## 10. 工作順序

1. 建 §2 的 3 個 config（注意 `../../` 路徑）+ §5.1 isolation 小 config。
2. §4 manifest（先 `no_overflow_pilot`）。
3. §3 runner 兩 mode + `bash -n`。
4. **L0/L1 smoke**：先跑 stock pilot 選 hook-fire 題 → Smoke A 隔離 fire → **Smoke B portfolio routing（確定路由到 predicate）** → C/D/E。
5. **L2 pilot**：pilot 兩 arm full → §8 矩陣判定（fire？0 wrong？≥1 win？）。
6. **L3 full**：過了再跑 full scalar NoOverflow + §7 因果歸因報告。
7. 全程不改 Java、不改 `vguide.properties` prompt（除非 §8 finding 要求）、不改官方 svcomp26/27 檔、不 merge main。

---

## 11. 實作狀態

| 項目 | 狀態 |
|------|------|
| 3 個 svcomp26-overflow-vguide config + isolation 小 config | **DONE**（`config/unmaintained/svcomp26-overflow-vguide.properties` + 2 components + `config/predicateAnalysis-overflow-vguide.properties`）|
| Runner 兩 mode（`svcomp26-overflow` / `svcomp26-overflow-vguide`）| **DONE**（run.sh + run_benchmark_set.sh 偵測；`bash -n` 過；dry-run 確認 config/spec/無全域 flag）|
| overflow manifest | **DONE**（`no_overflow_pilot` 15 題、`no_overflow_scalar` 452 題；filter no-overflow.prp + expected）|
| Smoke L0/L1 + counterfactual + C/D | **DONE**（見下方）|
| L2 pilot + L3 full-set | **DONE**（pilot 15/15 0-wrong；full 452 題 → **+6 / 6 new / 0 lost / 0 wrong**，6 全 direct LLM win）|
| 因果歸因報告 | **DONE** → [`reports/2026-06-15_svcomp26_overflow_vguide.md`](reports/2026-06-15_svcomp26_overflow_vguide.md) |

> **v1.6 結果：Class-A 泛化實證成立。** stock 357 → vguide 363 solved（+6），0 lost、0 wrong，6 個 new solves
> 全部 stock-UNKNOWN→vguide-TRUE（1 refinement、~4–6s、deciding=vguide predicate、llm_rounds=1）。
> 注入的是 overflow-相關 predicate（非負、`x ≤ 2^30−1` bound）→ config-only 即可，無需 prompt 適配。詳見上方 report。
> **能否再往上？** 提升評估與計劃見 [`SVCOMP26_OVERFLOW_VGUIDE_IMPROVEMENT_PLAN.md`](SVCOMP26_OVERFLOW_VGUIDE_IMPROVEMENT_PLAN.md)
> ——37 個 fired-but-UNKNOWN 是目標，最大 lever 是 overflow-aware prompt（現 prompt 反而勸退 overflow 要的 bound）。

### Smoke 結果（2026-06-15）

**結論：Class-A 泛化實證成立**——同一個 `useVocabularyGuide` hook，零 Java、零 prompt 改動，在 NoOverflow 上 fire 並產生 sound 的 net-new 解。

| Level | 結果 |
|---|---|
| **L0 隔離 fire** | 10 個 loop-zilu TRUE：6 fire（`FIRST_SPURIOUS_LLM`），4 fire+TRUE；conjunctive 穩定觸發，linear 太易（`NO_SPURIOUS_GIVE_UP` 不 fire）|
| **L1 portfolio routing** | benchmark09/17/18/19 在 full portfolio：**4/4 fire 且 deciding = vguide predicate child**（`…svcomp26-overflow-vguide--predicateAnalysis--overflow.properties finished successfully.`），TRUE 正確——**確定 portfolio 路由到此元件** |
| **Counterfactual** | benchmark09/19 stock 也解（非 net-new）；**benchmark17/18 stock UNKNOWN → vguide TRUE = 2 個 direct LLM net-new 解**；注入 overflow-相關 predicate（`i<n`、`k==i`、非負 sign-bit）|
| **C FALSE soundness** | AdditionIntMax/IntMin/Division-1（false）→ 全 FALSE 正確，**0 wrong** |
| **D recursion** | Ackermann01-2/02 → BAM fallback、LLM 不 fire、0 uncaught exception、clean UNKNOWN（非 wrong）|

判定矩陣（§8）：fire + 0 wrong + ≥1（實際 2）direct LLM net-new win → **Class-A 泛化成立**。
