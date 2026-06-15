# v1.6 termination 泛化 feasibility probe（safety-reduction 路）

定位：原本把 `terminationToSafety` 當成第二個 **Class-A**（config-only，像 overflow）。
**Grounding 後發現它不是。** 本文件是誠實的 reclassification + feasibility probe 計劃，
**不是**像 [`SVCOMP26_OVERFLOW_VGUIDE_PLAN.md`](SVCOMP26_OVERFLOW_VGUIDE_PLAN.md) 那種「確定能做」的執行計劃。
承接 [`LLM_RESEARCH_ROADMAP.md`](LLM_RESEARCH_ROADMAP.md) §4.2/§4.3（feasibility-first）。

---

## Phase 0 結果（2026-06-15）：RED — termination-safety = Class-B

Probe config（terminationToSafety + `analysis.algorithm.CEGAR=true` + predicate refiner + vguide）建好，
跑了 8 個 termination 題（terminating + non-terminating，static refinement on/off 兩組）。**結論 RED**：

| 證據 | 數據 |
|------|------|
| VGuide fire | **0/8**（全 `NO_SPURIOUS_GIVE_UP`）|
| CEGAR refinements | **0**（所有非 crash 題；static refinement on/off 皆然）|
| crash | `NonTermination3-1`：`java.util.NoSuchElementException` @ `PredicateStaticRefiner` / `PredicateCPARefiner.filterAbstractionStates`（static off 仍 crash）|
| soundness | 無 wrong verdict（全 UNKNOWN 或 crash），但也 0 solve |

**結構性原因（不是「題太簡單」）**：terminationToSafety 的證明引擎是 `TerminationToReachCPA`
（memory-based recurrent-state 偵測），**不是 predicate-CEGAR refinement**。即使把 CEGAR + predicate refiner
接進 composite、VGuide hook 確實進了 path（log 有 `Unified VGuide CEGAR enabled (first-spurious LLM path)`），
CEGAR 仍做 **0 次 refinement**——reduction 直接 UNKNOWN，從不交 spurious counterexample 給 predicate refiner，
所以 VGuide 沒有可介入的點；部分題還因 predicate-abstraction ARG 結構不存在而 crash。

**判定（§2.3）**：0 fire + CEGAR inert + crash → **RED → termination-safety = Class-B**。config 救不回來。
termination 的真正 LLM 機會在 **ranking-function 路（§5，v2.0 需 Java hook）**。

> **feasibility-first 的價值**：~30 分鐘 probe 擋掉了一整套（scoped variant + baseline + full-set）白工。
> 對比 overflow（同方法但 GREEN，[+6 result](reports/2026-06-15_svcomp26_overflow_vguide.md)）：差別就在「引擎是不是 predicate-CEGAR」。

---

## 0. 重要更正：terminationToSafety 預設不在 VGuide hook 的 path 上

逐檔 + 逐 Java 確認的事實：

| 層 | 事實 |
|----|------|
| dispatch | `svcomp26.properties` → `termination.config = svcomp26--termination.properties`（`analysis.algorithm.termination=true`）|
| portfolio | `svcomp26--parallel-termination.properties` = `terminationToSafety` ‖ `lassoBasedAnalysis`（2-way，像 overflow）|
| terminationToSafety 元件 | composite = LocationCPA, **PredicateCPA**, ValueAnalysisCPA, CallstackCPA, **TerminationToReachCPA**；設 `analysis.algorithm.terminationToSafety=true`；**但無 `#include …PredAbsRefiner-ABEl`、無 `analysis.algorithm.CEGAR`** |
| Java（`CoreComponentsFactory`）| `useTerminationToSafetyAlgorithm` 只 `shareTheSolverBetweenCPAs(cpa)`（line 651-652）；base algorithm = `CPAAlgorithm.create(...)`（655）；**CEGAR 是另一個獨立 wrap（`if (useCEGAR)`, 687），terminationToSafety 預設沒開** |

**結論**：terminationToSafety 預設跑的是 **CPAAlgorithm（無 CEGAR）** + TerminationToReachCPA 的 memory-based reduction。
PredicateCPA 在 composite 裡，但**沒有 predicate-CEGAR refinement** → `PredicateCPARefiner`（VGuide hook 落點）**不在 path 上** →
單純加 `cpa.predicate.refinement.useVocabularyGuide=true` **不會 fire**。

對比 overflow（為什麼 overflow 是乾淨 Class-A 而這個不是）：

| | overflow predicate child | terminationToSafety |
|--|--|--|
| ABEl predicate-CEGAR refiner | `#include …PredAbsRefiner-ABEl`（現成）| **無** |
| CEGAR | refiner include 自帶 | **預設關** |
| VGuide hook 在 path | **是** → flip 一個 option 就 fire | **否** → 要先把 CEGAR+refiner 接進來 |

→ roadmap §4.2 的「Termination safety 路 = A?（待確認 refiner）」**正式 resolve 為：不是乾淨 Class-A**。

---

## 1. 要讓 VGuide 在 termination-safety fire，需要什麼（為何是 probe 而非 clone）

**不是** config-only。至少要：

1. `analysis.algorithm.CEGAR = true`（開 CEGAR wrap）。
2. 把 predicate refiner 接進 termination composite —— `predicateAnalysis-PredAbsRefiner.properties` 的 **refiner 部分**
   （`predicateAnalysis-PredAbsRefiner-ABEl` = `predicateAnalysis-ABEl`（composite/ABE）+ `predicateAnalysis-PredAbsRefiner`（refiner））。
   **不能整包 include**，因為 ABE 那半會 clobber 既有 composite（它含 `TerminationToReachCPA`）。只能挑 refiner/CEGAR 選項。
3. `#include vguide.properties` + `useVocabularyGuide = true`。
4. **驗證 soundness**：predicate-CEGAR refinement 與 `TerminationToReachCPA` 的 state-tracking 共存時，termination verdict 是否仍正確。

第 2、4 點是真正的不確定性：官方從不在這條 path 上跑 predicate CEGAR，所以「refinement 介入 termination-to-reach reduction 是否 sound」是**未驗證**的。

---

## 2. Phase 0 — Feasibility probe（go/no-go，先做這個）

### 2.1 Probe config

`config/unmaintained/components/svcomp26-term-vguide--terminationToSafety.properties`（probe-only）：
複製 `svcomp26--termination-terminationToSafety.properties`，在**保留原 composite**（含 TerminationToReachCPA）的前提下加：
```properties
analysis.algorithm.CEGAR = true
#include ../../includes/predicateAnalysis-PredAbsRefiner.properties   # 只 refiner 半，不含 ABE composite
#include ../../vguide.properties
cpa.predicate.refinement.useVocabularyGuide = true
```
⚠️ 若 `predicateAnalysis-PredAbsRefiner.properties` 內含 composite/CPA 行會 clobber → 改成手動只抄 refiner 選項
（`cegar.refiner=…`, predicate refinement 選項），不抄 CPA 行。probe 階段先試整包 include，crash 再退手抄。

### 2.2 Probe 題（各 1–2 題，需要 refinement 的）

- **terminating TRUE**：`termination-crafted` / `termination-numeric` 裡需要 invariant 才證終止的（非 trivial）。
- **non-terminating FALSE**：一個已知 non-terminating 題（驗 soundness 最關鍵——predicate refinement 不能把 FALSE 弄成 TRUE）。
- 用 `config/properties/termination.prp` spec。

### 2.3 三個檢查 + go/no-go

| 檢查 | 通過條件 |
|------|----------|
| (a) 不 crash / composite 不衝突 | 跑完出 verdict，無 CPA 組裝 exception |
| (b) VGuide fire | log 出現 `VGuide LLM round #` + `precision-injected` |
| (c) **soundness** | terminating 題 → TRUE/正確；**non-terminating 題 → FALSE/正確**；**0 wrong** |

- **GREEN**（a+b+c 全過）→ termination-safety 是 **Class-A\***（config 可行，雖比 overflow 多幾行）→ 進 Phase 1。
- **RED**（不 fire / 不 compose / 任何 wrong verdict）→ 結論 **Class-B**：safety 路也救不回來，記錄並 pivot（§5）。

soundness（c）是 hard gate：只要出現一個 wrong termination verdict，立刻 RED，不論 fire 與否。

---

## 3. Phase 1 —（僅 GREEN 才做）mirror overflow

若 Phase 0 GREEN，照 overflow 方法做 scoped 變體 + runner mode + termination set + smoke 梯 + baseline + full-set + report：

| 步 | 內容 |
|----|------|
| 變體 | `svcomp26-term-vguide.properties`（top）→ parallel-termination 變體（terminationToSafety child 指 vguide 版；lasso child 不變）→ 上面 probe config 轉正 |
| runner | `svcomp26-termination` / `svcomp26-termination-vguide`，spec=`termination.prp` 對應 spec |
| set | termination 官方 `.set`（`Termination-*`）∩ termination property → `termination_scalar.list` |
| smoke | L0 隔離（standalone terminationToSafety+vguide）→ L1 portfolio（fire + terminationToSafety child 決定）→ FALSE/non-term soundness → recursion |
| full | stock vs vguide，**0-wrong 第一**（termination FALSE 更難驗）、new/lost、direct LLM wins |

---

## 4. 風險：soundness 是頭號風險（比 overflow 高一個量級）

- **termination-to-reach + predicate refinement 的共存正確性未驗證**：refinement 改變 abstraction，可能影響 `TerminationToReachCPA` 偵測「重複 state → 非終止」的邏輯 → **可能產生 WRONG termination verdict**。這是 hard blocker，Phase 0 的 (c) 專門擋。
- termination 的 FALSE（non-termination）witness 比 reachability/overflow 複雜；0-wrong 驗證成本更高。
- 即使 GREEN，payoff 可能小：terminationToSafety 的力量多半來自 memory-reduction + value，不一定靠 predicate；VGuide 的 predicate 未必常是 decider（像 overflow 的 value child 競爭）。Phase 1 attribution 才知道。

---

## 5. 若 RED：termination 的真正 LLM 機會在 ranking function（Class-B，v2.0）

terminationToSafety 救不回來的話，termination 的高槓桿介入點是另一條 parallel child：
**`lassoBasedAnalysis` 的 candidate ranking function**——但那是 **Class-B**（native artifact = ranking function，
無 predicate-CEGAR hook，要在 Java 寫「接受候選 ranking function + 交 prover 驗 decrease+bounded」的 sound hook）。
見 roadmap §4.2/§4.3。這留給 v2.0，不在本 probe 範圍。

---

## 6. 工作順序

1. **Phase 0 probe first**：建 §2.1 probe config（先試整包 refiner include，clobber 再退手抄）→ 跑 §2.2 的 2–3 題 → §2.3 go/no-go。
2. GREEN → Phase 1（§3，mirror overflow）。RED → 更新 roadmap §4.2（termination safety = Class-B），記錄，停。
3. 全程不改 Java（Phase 0/1 都是 config 探索）；soundness 任何 wrong 立即停。

---

## 7. 實作狀態

| 項目 | 狀態 |
|------|------|
| Grounding（terminationToSafety ≠ 乾淨 Class-A）| **DONE**（§0）|
| Phase 0 probe config | **DONE**（已建已跑、確認結構性不可行後刪除 dead-end config）|
| Phase 0 probe 跑 + go/no-go | **DONE → RED**（0 fire / CEGAR inert / crash；見頂部）|
| Phase 1（條件）| **N/A**（RED）|
| 結論 | termination-safety = **Class-B**；pivot 到 ranking-function hook（§5，v2.0）|
