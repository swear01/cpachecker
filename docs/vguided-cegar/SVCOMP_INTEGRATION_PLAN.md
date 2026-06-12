# SV-COMP 競賽 config 整合計劃（svcomp27 × VGuide v1.5）

目標：讓 v1.5 + LLM（unified VGuide）在競賽用 strategy-selection config（`config/svcomp27.properties`）
下正確運作，做研究比較用（不考慮比賽離線/網路限制）。本文件含：已驗證的架構事實、
必修項（P0）、原始碼不合理處的修正（P1）、config 變體設計、參數重調與實驗設計。

日期：2026-06-13。基於 commit `ffd36de723`（main）。

---

## 0. 已驗證的架構事實（調查結論）

1. **Predicate 核心兩邊相同。** 現行 `predicateAnalysis-vguide.properties` → `predicateAnalysis.properties`
   → `includes/predicateAnalysis-PredAbsRefiner-ABEl.properties`；svcomp27 的 predicate 元件
   （`svcomp27--singleLoop-predicateAnalysis.properties` 等）include 的是同一個檔案。
   不需要動分析演算法，只需注入 vguide 選項。

2. **競賽 config 是四層巢狀：**
   ```
   svcomp27.properties
    └─ SelectionAlgorithm（loop-free / 單迴圈 / 多迴圈 / complexLoop 四選一）
        └─ RestartAlgorithm（±recursion/concurrency 特化）
            └─ ParallelAlgorithm（5 個分析並行，predicate 是其中之一，
                                  limits.time.cpu.thread = 200s）
   ```
   Predicate（非 cex-check）出現在：
   - `components/svcomp27--singleLoop-predicateAnalysis.properties`（單迴圈 portfolio）
   - `components/svcomp27--multipleLoops-predicateAnalysis.properties`（多迴圈 portfolio）
   - `components/svcomp27--configselection-restartcomponent-predicateAnalysis-end.properties`
     （loop-free 鏈最後 fallback）
   - `components/svcomp27--recursion.properties`（**BAM** predicate，見 P0-3）
   - complexLoop 鏈（valueAnalysis chain）**沒有** predicate 主分析，只有 cex-check。

3. **選項傳遞：** `NestingAlgorithm.buildSubConfig()`（NestingAlgorithm.java:105）先
   `copyFrom(globalConfig)` 再 `loadFromFile()` → **命令列 `--option` 會傳進所有巢狀分析**
   （子檔案同名選項優先）。例外：counterexample check
   （CounterexampleCPAchecker.java:216 只 `loadFromFile`，不繼承全域）→ vguide 不會漏進 cex-check。

4. **Interrupt 安全已確認：** ParallelAlgorithm 用 `future.cancel(true)`（interrupt）收掉輸家，
   `HttpClient.send()` 可被 interrupt（丟 InterruptedException），bridge 把
   InterruptedException 原樣往上丟 → LLM 等待中被取消不會卡住 portfolio。**不需修。**

5. **資源模型：** svcomp 全域 `limits.time.cpu = 900s`（`includes/resource-limits.properties`），
   predicate thread `limits.time.cpu.thread = 200s`。LLM 等待是 wall time、不耗 thread CPU。

---

## 1. P0 必修（不修會出錯或數據亂掉）

### P0-1 `vguide.frozenDir` 相對路徑
`FrozenPredicateLoader` 用 `Path.of(string)` 相對 CWD 解析（預設
`docs/vguided-cegar/predicate_sets`）。换目錄執行（benchexec、不同 runner CWD）即失效。

**修法：** `VGuideOptions.frozenDir` 改為
`@FileOption(FileOption.Type.OPTIONAL_INPUT_FILE) private Path frozenDir`，
讓 sosy-lab config 系統以 rootDirectory 解析；`FrozenPredicateLoader` 建構子收 `Path`。
檔案：`VGuideOptions.java`、`FrozenPredicateLoader.java`、`VGuideRefinementBridge.java:110`。

### P0-2 Dump taskName 衝突 + shutdown hook 堆積
競賽 config 一次 run 會建**多個** bridge（portfolio 的 predicate、restart 後的
predicateAnalysis-end、recursion 的 BAM predicate）。問題：
- `VGuideAnalysisDumper` 的 taskName 取 CFA 檔名 base name → 多個 bridge 寫同一個
  `tasks/<name>/` 目錄，refinements.jsonl / llm_rounds.jsonl 互相污染。
- 每個 bridge 在建構時 `Runtime.addShutdownHook()`（VGuideRefinementBridge.java:148-152），
  不曾移除；被 ParallelAlgorithm 取消的分析其 hook 留到 JVM 結束才 fire，寫出過期資料。

**修法：**
- taskName 加 bridge 序號（static `AtomicInteger`）與來源 config 識別，例如
  `<base>__b0`, `<base>__b1`；manifest 記錄 component config 名。
- `finishTask` 正常完成後 `removeShutdownHook`（注意 JVM shutdown 進行中不能 remove，
  包 try/IllegalStateException）。
檔案：`VGuideRefinementBridge.java`、`VGuideAnalysisDumper.java`。

### P0-3 BAM（recursion config）下禁用 vguide
`BAMPredicateRefiner` 也走 `PredicateCPARefinerFactory` → 全域開
`useVocabularyGuide=true` 會把 vguide 帶進 BAM。`LoopHeadPrecisionInjector` 對 BAM 的
巢狀 reached set 從未驗證，注入點語意大概率錯誤。

**修法：** factory 建 bridge 前檢測 predicate CPA 是否為 `BAMPredicateCPA`；是則
log WARNING 並不建 bridge（fallback 為 stock refiner），不要丟 exception
（restart 鏈才不會整條死掉）。檔案：`PredicateCPARefinerFactory.java`。

### P0-4 跨元件 LLM 總量上限
`maxLlmRoundsPerAnalysis = 5` 是 per-bridge。restart 鏈可能 portfolio predicate 先燒 5
rounds、失敗後 predicateAnalysis-end 再燒 5 rounds → 成本與行為都跟單分析實驗不可比。

**修法：** 新增 `vguide.maxLlmRoundsPerProcess`（JVM 全域 static `AtomicInteger`，
0 = 不限制，建議預設 10）。`LlmCallScheduler.shouldCall()` 同時檢查全域 cap，
skip reason 記 `process_round_cap`。檔案：`VGuideOptions.java`、`LlmCallScheduler.java`。

### P0-5 runner 的全域 `--option` 與 scoped config 衝突
`run_benchmark_set.sh:204` 無條件加 `--option cpa.predicate.refinement.useVocabularyGuide=true`。
因為全域選項會傳進所有巢狀分析（事實 3），這會把 recursion BAM 等也打開，
抵銷 scoped config 的用意。

**修法：** runner 加 `svcomp` 模式：使用 scoped config（見 §3）時**不**傳全域
useVocabularyGuide，由 config 檔自己控制。（P0-3 的 guard 是第二道防線。）

---

## 2. P1 原本就不合理、順手修正

### P1-1 `WallClockBudget` 註解與實作不符
選項說明寫「0 = use remaining CPAchecker time limit only」，實作是
`budgetMs = Long.MAX_VALUE`（無限）。**修：** 文件改為「0 = unlimited」；
若要真語意需接 ShutdownNotifier 的剩餘時間，現階段不必要。

### P1-2 LLM client 設定散落在環境變數
`DEEPSEEK_MODEL`、`VGUIDE_LLM_THINKING`、`VGUIDE_LLM_REASONING_EFFORT`、
`VGUIDE_LLM_TIMEOUT_SEC` 走 env；`llmMaxCompletionTokens` 已是 option 但
`PredicateProposalClient(logger)` 單參數建構子又讀 env default。
env 不會被 CPAchecker 的 config dump 記錄，傷實驗可重現性。

**修：** 全部移成 `vguide.llm*` options（env 保留為 override、優先序 env > option），
manifest 記錄最終生效值。檔案：`PredicateProposalClient.java`、`VGuideOptions.java`。

### P1-3 API key 檢查重複
`PredicateCPARefinerFactory.java:174-178` 直接 `System.getenv("DEEPSEEK_API_KEY")`，
client 建構子又檢查一次。**修：** 整併到一處（factory 呼叫
`PredicateProposalClient.createOptional` 判斷），錯誤訊息保留。

### P1-4 frozen-seed 注入時機是 dead code
`onAnalysisEnd`（refinementCount==0 時注入 frozen predicates）是從
`PredicateCPARefiner` 的 **printStatistics**（PredicateCPARefiner.java:697）呼叫——
分析已結束，注入對該 run 的 verdict 無效；在 svcomp restart 鏈下也不會被後續元件
看到。**修：** 至少加註解標明這條路徑只影響 dump/outcome 統計；若 FROZEN_SEED
路線還要繼續做，需改成在分析開始時（initial precision）注入，另開工作項。

### P1-5 taskName 唯一性
sv-benchmarks 不同目錄可能有同 base name 的 .c 檔。與 P0-2 一起解
（taskName 加序號 + manifest 記完整路徑）。

---

## 3. Config 變體（scoped 注入，正式實驗用）

原則：只在「會跑 CEGAR 的 predicate 主分析」開 vguide；recursion（BAM）、
concurrency、cex-check、complexLoop 鏈一律不動。

新增檔案（複製官方檔、只改 include 鏈，9 個）：

| 新檔案（config/ 下） | 改動 |
|---|---|
| `svcomp27-vguide.properties` | 複製 top；4 個 `heuristicSelection.*` 指向下列變體 |
| `components/svcomp27-vguide--singleLoopConfig.properties` | restart 第一項指向 vguide parallel |
| `components/svcomp27-vguide--multipleLoopsConfig.properties` | 同上 |
| `components/svcomp27-vguide--parallel-singleLoop.properties` | predicate 項指向 vguide 元件 |
| `components/svcomp27-vguide--parallel-multipleLoops.properties` | 同上 |
| `components/svcomp27-vguide--singleLoop-predicateAnalysis.properties` | 原檔 + 2 行（見下） |
| `components/svcomp27-vguide--multipleLoops-predicateAnalysis.properties` | 同上 |
| `components/svcomp27-vguide--configselection-restart-bmc-fallbacks.properties` | 末項指向 vguide predicate-end |
| `components/svcomp27-vguide--configselection-restartcomponent-predicateAnalysis-end.properties` | 原檔 + 2 行 |

predicate 元件變體加的兩行：
```properties
#include ../vguide.properties
cpa.predicate.refinement.useVocabularyGuide = true
```
注意：`vguide.properties` 內 `frozenDir` 走 P0-1 的 @FileOption 解析後路徑才正確。

recursion / concurrency 的 `::if-recursive` / `::if-concurrent` 項保持指向**官方原檔**。
`heuristicSelection.complexLoopConfig` 與 `svlib.config`、memsafety/overflow/termination
等 property-specific config 全部維持官方原檔（reachability 研究不涉及）。

煙霧測試可先走「路 A」免建檔：
```bash
bin/cpachecker --config config/svcomp27.properties \
  --spec config/specification/sv-comp-reachability.spc \
  --option cpa.predicate.refinement.useVocabularyGuide=true \
  --option vguide.enable=true ...
```
（需 P0-3 的 BAM guard 先進去，否則遇到遞迴案例行為未定義。）

---

## 4. 排程參數重調

現行 `llmMinIntervalSec=15` / `every_n=72` 的推導（LLM_CALL_SCHEDULING.md）假設
單分析、CPU≈wall、300s 預算。svcomp 下差異：

| 維度 | 單分析（現行） | svcomp portfolio |
|---|---|---|
| predicate 預算 | 300s CPU ≈ wall | thread CPU 200s；wall 受 5 thread 搶核影響 |
| LLM 等待 | 占用唯一分析的 wall | 不耗 thread CPU（其他分析照跑） |
| 總時限 | 300s | 全域 900s CPU |

含意：min_interval 以 wall 計，但 predicate 的 CPU 進度比 wall 慢 →
相對其 CPU 進度 LLM 會更頻繁。先跑校準實驗（§5 Phase 3）收 `llm_rounds.jsonl`
再決定是否把 interval 拉高或 maxRounds 降低；不要先驗調參。

---

## 5. 執行步驟

**Phase 0 — 煙霧測試（路 A，半天）**
2–3 個 Loops 案例 + 1 個遞迴案例跑 `svcomp27.properties` + 全域 option：
- log 出現 "Unified VGuide CEGAR enabled" 且 verdict 正確
- witness.graphml / witness.yml 正常產出
- 找一個 sibling 先解掉的案例，確認 cancel 期間 LLM 不卡（對照事實 4）
- 遞迴案例觀察 BAM 路徑行為（P0-3 的動機驗證）

**Phase 1 — P0 程式修正**（P0-1…P0-4 + 單元測試；P1 視時間插入，P1-1/P1-3 便宜可一起）

**Phase 2 — 建 §3 的 9 個 config 變體**，重跑 Phase 0 案例驗證 scoped 行為
（遞迴案例不得出現 vguide log）。

**Phase 3 — 校準實驗（~20 個 Loops tasks）**
`svcomp27-vguide` vs `svcomp27`（stock），900s，收 LLM round 頻率/成本/
哪個 portfolio 元件給 verdict，決定 §4 參數。

**Phase 4 — 正式三組比較（full Loops set）**
1. `svcomp27.properties`（stock baseline）
2. `svcomp27-vguide.properties`
3. 現行 `predicateAnalysis-vguide.properties`（既有 v1.5 數據對照）

指標：PAR-2、solved、LLM rounds/tokens、**predicate-decided subset**（見 §6）。
Runner：`VGUIDE_CONFIG=config/svcomp27-vguide.properties`、
`VGUIDE_SPEC=$REPO/config/specification/sv-comp-reachability.spc`、
svcomp 模式不傳全域 useVocabularyGuide（P0-5）；時限統一 900s 與競賽一致
（若要與既有 300s 數據對照，組 3 另跑 300s）。

---

## 6. 風險與研究註記

- **效果稀釋**：portfolio 中很多 Loops 案例會被 IMC/BMC/k-induction 先解掉，
  vguide 只在 predicate 元件勝出的子集上有機會發揮。報告需單獨統計
  「由 predicate 元件給 verdict」的子集（從 ParallelAlgorithm 的
  "One of the parallel analyses has finished successfully" log + 元件名解析），
  否則整體 PAR-2 差異會被淹沒。這本身就是研究問題：**LLM 引導在競賽
  portfolio 的邊際價值**，預期主戰場在 BMC/IMC 都炸掉的長收斂案例。
- **SelectionAlgorithm 分流**：部分 Loops 案例可能被 heuristic 分到
  complexLoop 鏈（無 predicate 主分析）→ vguide 完全不參與；統計分流比例。
- **比賽環境**（本計劃不處理，僅記錄）：正式 SV-COMP 無網路，線上 LLM 不可行；
  離線路線為本地模型或 frozenDir 預算 predicate sets（P1-4 需先修好注入時機）。

---

## 7. Implementation status（2026-06-13）

Branch：`svcomp-integration`

| Item | Status | Commit | Diff summary |
|------|--------|--------|--------------|
| P0-1 `vguide.frozenDir` path resolution | DONE | `e0aa0491dd` | `VGuideOptions.frozenDir` is now `Path` with `@FileOption(FileOption.Type.OPTIONAL_INPUT_FILE)`; `FrozenPredicateLoader` accepts `Path`; loader tests updated. |
| P0-2 dump taskName + shutdown hook lifecycle | DONE | `f3c5ddd47d` | First bridge keeps the original task name; later bridges use `__bN`; dump rows/task summary include `task_base` and `bridge_index`; run manifest records bridge naming policy; normal completion removes shutdown hook and ignores `IllegalStateException` during JVM shutdown. |
| P0-3 BAM fallback | DONE | `d899736704` | `PredicateCPARefinerFactory` detects `BAMPredicateCPA`, logs `WARNING`, and falls back to the standard refiner without throwing. |
| P0-4 process LLM round cap | DONE | `a6a60bc29e` | Added `vguide.maxLlmRoundsPerProcess` default `0 = unlimited`; scheduler checks the process cap and reports `process_round_cap`; added cross-scheduler unit test. |
| P1-1 wall budget option description | DONE | `047c9e0b6d` | Description now states `0 = unlimited`; behavior unchanged. |
| P1-3 API key check consolidation | DONE | `047c9e0b6d` | Factory uses `PredicateProposalClient.createOptional(...)`; missing key still raises `InvalidConfigurationException` with the original `useVocabularyGuide=true requires DEEPSEEK_API_KEY` meaning. |
| P1-4 frozen-seed timing comment | DONE | `b9a76c317b` | `onAnalysisEnd` documents that current frozen injection happens after verdict and only affects dump/outcome accounting. |
| 9 scoped `svcomp27-vguide` configs | DONE | `4baeb087c1` | Added top-level and component variants; only predicate CEGAR components include VGuide; recursion/concurrency/complexLoop/property-specific configs remain official originals; top-level sets `vguide.maxLlmRoundsPerProcess = 10`. |
| Runner svcomp scoped mode | DONE | `65ffdba921` | Added `--mode svcomp27-vguide` / `VGUIDE_SVCOMP=1`; scoped mode omits global `useVocabularyGuide` option and defaults to `sv-comp-reachability.spc`; existing stock/vguide/svcomp26 behavior preserved. |

Verification report：[`reports/2026-06-13_svcomp27_vguide_integration.md`](reports/2026-06-13_svcomp27_vguide_integration.md)。

Known smoke-test limitation：the recursive BAM fallback smoke runs did not reach TRUE/FALSE within the intentionally short 60s limit, but both demonstrated non-crashing behavior and the expected BAM fallback/no-VGuide-log evidence.

---

## 8. Phase 3 / full-set readiness status（2026-06-13）

Branch：`svcomp-integration`

| Item | Status | Commit | Diff / result summary |
|------|--------|--------|-----------------------|
| Sample workflow regression | DONE | `3c9ce56019` | Compared `main` vs branch for `run.sh cpa --set sample`; 8/8 verdicts match, summary CSV header unchanged, single-analysis dump task dirs have no `__bN` suffix, no `process_round_cap` logs. |
| Portfolio verdict attribution | DONE | `0b96741d32` | Added `scripts/vguided-cegar/attribute_svcomp_verdicts.py`; parses log dirs or single logs into `task,verdict,selection_branch,restart_stage,deciding_component,vguide_fired,llm_rounds`; validated on smoke logs including scoped recursive no-VGuide path. |
| Stock svcomp27 runner mode | DONE | `50211b3e9c` | Added `run.sh cpa --mode svcomp27-stock`; uses official `config/svcomp27.properties`, sv-comp reachability spec, no global VGuide option, no API-key requirement. |
| 20-task reachability pilot | DONE | `95f6eb0e3f` | Added `svcomp27_pilot_20.list` with 10 TRUE + 10 FALSE `unreach-call.prp` tasks from `full_scalar`; ran stock and scoped VGuide at 900s, `--heap 4000M`, `--parallel 6`; VGuide solved 12/20 vs stock 11/20, no wrong verdicts, no process cap hits. |
| Full-set launcher | DONE | `33f19c06e7` | Added `run_svcomp_full_nohup.sh`; default `full_scalar`, both stock+VGuide arms, 900s, `--parallel 6`, `--heap 4000M`, detached nohup log, automatic attribution CSV; dry-run and 2-task smoke verified. |

Calibration / readiness report：[`reports/2026-06-13_svcomp27_pilot_calibration.md`](reports/2026-06-13_svcomp27_pilot_calibration.md)。

Full-set status：ready for user-triggered launch; **not launched** during preparation. Recommended command:

```bash
cd /home/swear01/cpachecker
./scripts/vguided-cegar/run_svcomp_full_nohup.sh --arm both
```
