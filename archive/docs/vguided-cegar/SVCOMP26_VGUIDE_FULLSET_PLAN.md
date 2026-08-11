# svcomp26-vguide full-set 計劃（loops_reachsafety_unreach × VGuide v1.5）

目標：在你已有的 **svcomp26 strong baseline** 之上，做一個 scoped VGuide 變體
`svcomp26-vguide`，在同一個 764 題官方 Loops set、同一個 300s 時限下跑，
乾淨歸因「把 LLM predicate 引導加進 svcomp26 portfolio」的邊際貢獻。

日期：2026-06-14。Branch：`svcomp-integration`。

---

## 0. 為什麼是 svcomp26 而非 svcomp27

你的 strong baseline 是用 `config/unmaintained/svcomp26.properties` 跑出來的
（[reports/2026-06-13_v1.5_loops_reachsafety_unreach.md](reports/2026-06-13_v1.5_loops_reachsafety_unreach.md)）：

| Mode | Config | Solved (764 題, 300s) |
|------|--------|----------------------:|
| stock 單分析 | `predicateAnalysis-vguide.properties` (LLM off) | 225 |
| **svcomp26 portfolio** | `unmaintained/svcomp26.properties` | **486** |
| v1.4 VGuide 單分析 | `vguide-experiment-dual-prompt-v1.properties` | 262 |

乾淨對照 = **同 config base、只差 predicate 元件換成 LLM 版**。所以變體要做在
svcomp26（對照 486），不是 trunk 的 svcomp27（無同時限 baseline）。
svcomp27-vguide 的工作保留不動，作為未來 trunk 對齊用。

研究問題（承 v1.5 報告結論 4–5）：svcomp26 portfolio 已達 486（278 UNKNOWN），
VGuide 的機會只在「predicate 元件能碰到、且其他 4 個並行分析都沒解掉」的 UNKNOWN
子集。預期淨增量是個位數～數十題，全部 TRUE 取向（VGuide 不 target FALSE）。
關鍵看點：v1.5 那 **33 個 VGuide-only solves** 在 portfolio 內是否保留/擴張。

---

## 1. 已驗證的結構事實

svcomp26 與 svcomp27 **完全同構**（已逐檔確認）：

1. `svcomp26--singleLoop-predicateAnalysis.properties` include
   `../../includes/predicateAnalysis-PredAbsRefiner-ABEl.properties`
   —— 與 svcomp27 / 現行 vguide 同一個 ABEl include。**演算法零差異。**
2. `svcomp26--parallel-singleLoop.properties` = 5 分析並行
   （symbolicExecution、valueAnalysis-Cegar、predicateAnalysis、dataFlow、IMC），
   與 svcomp27 一致。
3. `svcomp26--singleLoopConfig.properties` restart chain =
   `parallel-singleLoop + recursion::if-recursive + concurrency::if-concurrent`。
4. 9 個變體的對應官方檔在 svcomp26 全部存在（singleLoop/multipleLoops-predicateAnalysis、
   parallel-singleLoop/multipleLoops、singleLoopConfig/multipleLoopsConfig、
   restart-bmc-fallbacks、restartcomponent-predicateAnalysis-end）。
5. recursion 走 BAM —— Java 層 BAM guard（`d899736704`）與 config 版本無關，
   svcomp26 recursion 一樣會被擋、fallback 成 stock refiner。

**唯一差異 = 路徑深度。** svcomp26 top 在 `config/unmaintained/`，components 在
`config/unmaintained/components/`，比 svcomp27（`config/` 與 `config/components/`）深一層。

---

## 2. 要建的 9 個變體（平行移植 svcomp27-vguide）

原則同 svcomp27-vguide：只在跑 CEGAR 的 predicate 主分析開 vguide；
recursion(BAM)/concurrency/complexLoop/cex-check/property-specific 全部指向**官方 svcomp26 原檔**。

| 新檔（路徑） | 來源官方檔 | 改動 |
|---|---|---|
| `config/unmaintained/svcomp26-vguide.properties` | `svcomp26.properties` | 複製；4 個 `heuristicSelection.*` 的 singleLoop/loop/loopFree 指向下列變體；complexLoop 與 specification/property configs 不變 |
| `config/unmaintained/components/svcomp26-vguide--singleLoopConfig.properties` | 同名官方 | restart 首項指向 `svcomp26-vguide--parallel-singleLoop.properties` |
| `…svcomp26-vguide--multipleLoopsConfig.properties` | 同名 | 首項指向 vguide parallel-multipleLoops |
| `…svcomp26-vguide--parallel-singleLoop.properties` | 同名 | predicate 項指向 `svcomp26-vguide--singleLoop-predicateAnalysis.properties`；其餘 4 分析不變 |
| `…svcomp26-vguide--parallel-multipleLoops.properties` | 同名 | predicate 項指向 vguide 版 |
| `…svcomp26-vguide--singleLoop-predicateAnalysis.properties` | 同名 | 僅 `useVocabularyGuide=true`（**不**再 `#include vguide.properties`） |
| `…svcomp26-vguide--multipleLoops-predicateAnalysis.properties` | 同名 | 同上 |
| `…svcomp26-vguide--configselection-restart-bmc-fallbacks.properties` | 同名 | 末項指向 `svcomp26-vguide--…predicateAnalysis-end` |
| `…svcomp26-vguide--configselection-restartcomponent-predicateAnalysis-end.properties` | 同名 | 僅 `useVocabularyGuide=true` |

predicate 元件只加一行（`vguide.*` 在 top `svcomp26-vguide.properties` `#include ../vguide.properties`，CLI `--option` 才能覆寫排程）：
```properties
cpa.predicate.refinement.useVocabularyGuide = true
```

⚠️ 路徑檢查清單：
- predicate 元件 → vguide.properties：`../../vguide.properties`（unmaintained/components → config/）
- ABEl include 維持官方原樣 `../../includes/…`
- top config `specification = ../specification/sv-comp-reachability.spc`（保留 svcomp26 原值）
- top config `heuristicSelection.* = components/svcomp26-vguide--…`（相對 unmaintained/）
- 每檔加 SPDX header（複製官方原檔的）；REUSE/license CI 會檢查
- 變體鏈只改「指向 vguide 變體」那幾行，其餘逐字保留

---

## 3. Runner：加 `--mode svcomp26-vguide`

`scripts/vguided-cegar/run.sh`：平行於現有 `svcomp27-vguide` 分支，新增
```
svcomp26-vguide) require_api;  VGUIDE_SVCOMP=1
                 VGUIDE_CONFIG=config/unmaintained/svcomp26-vguide.properties
                 VGUIDE_SPEC=$REPO/config/specification/sv-comp-reachability.spc
                 out 預設 <set>_svcomp26_vguide
```
`scripts/vguided-cegar/run_benchmark_set.sh`：SVCOMP_MODE 的 config-name 偵測
（目前 `*svcomp27-vguide*`）擴充涵蓋 `*svcomp26-vguide*`（svcomp 模式不傳全域
`useVocabularyGuide`）。既有模式行為不得變。

煙霧驗證（建 config 後）：
- 1 題 loops（會觸發 LLM）`--mode svcomp26-vguide`：log 出現
  `svcomp26-vguide--singleLoop-predicateAnalysis.properties` + `VGuide LLM round`，verdict 正確
- 1 題 recursive：出現 BAM fallback WARNING、無 vguide log、不 crash

---

## 4. Full-set 執行

對照已有 baseline，**只需跑 svcomp26-vguide 這一個 arm**（svcomp26 stock 486 已存在）。

- Set：`loops_reachsafety_unreach`（764 題）
- Timelimit：**300s**（與三組 baseline 同）
- Parallel：建議 **6**（pilot 已驗證同構 portfolio @parallel6 在 32 核/125G 記憶體安全；
  依本機規格調，見 pilot 報告 §Task D）。
  注意：baseline svcomp26 是 parallel 1，但 **solved/verdict 由每進程 CPU-limit 決定、與 batch
  parallel 無關**，所以 solved/correct 對比可比；只有 wall-based 次要指標受 parallel 影響。
- Heap：`4000M`

```bash
VGUIDE_TIMEOUT_GRACE=180 \
VGUIDE_ANALYSIS_DUMP_DIR=output/vguide/analysis_dumps/loops_reachsafety_unreach_svcomp26vguide_<DATE> \
VGUIDE_ANALYSIS_BENCHMARK_SET=loops_reachsafety_unreach \
VGUIDE_ANALYSIS_TIMELIMIT_SEC=300 \
./scripts/vguided-cegar/run.sh cpa --set loops_reachsafety_unreach --mode svcomp26-vguide \
  --parallel 6 --timelimit 300 --heap 4000M \
  --out output/vguide/experiments/loops_reachsafety_unreach_svcomp26vguide_<DATE>
```
最壞時長 ≈ 764×300/6 ≈ 10.6h（實際更短：baseline solved wall avg 6.49s，多數秒解，
僅 UNKNOWN 跑滿 300s）。建議 nohup detached（可借用既有 `run_*_nohup.sh` 慣例）。

---

## 5. 分析與產出

報告 `docs/vguided-cegar/reports/<DATE>_svcomp26_vguide_loops.md`，含：

1. **Soundness 第一**：掃 wrong verdict（對 `loops_reachsafety_unreach.list` 的
   `expected=`）。有則高亮 + 保留 log（baseline 三組皆 0 wrong）。
2. **Topline**：併入 v1.5 那張表，新增一列 `svcomp26-vguide`
   （TRUE/FALSE/UNKNOWN/Solved/Correct/PAR-2）。主對照 = vs svcomp26(486)。
3. **Overlap/delta vs svcomp26**：new solves / lost solves / disagreements / net
   （格式同 v1.5 報告）。重點看有沒有 lost solves（VGuide 把原本 portfolio 解的弄成 UNKNOWN）。
4. **predicate-decided subset**：用 `attribute_svcomp_verdicts.py` 統計由
   `svcomp26-vguide--…predicateAnalysis` 元件決定的題；只在此 subset 上談 LLM 貢獻。
5. **LLM 淨貢獻清單**：svcomp26-vguide solved 但 svcomp26 沒 solved、且
   deciding=vguide 元件 **且 `llm_rounds>0`** 的題。對照 v1.5 的 33 個 VGuide-only solves。
6. **LLM 間隔分析**：用 dump 的 `call_start_epoch_ms`（commit `c13cadc132` 起有）算
   多輪題的相鄰呼叫間隔，驗證 `llmMinIntervalSec=15`。
7. **分流統計**：各 selection branch 題數；特別記 complexLoop（無 predicate 主分析）佔比。

---

## 6. 工作順序

1. 建 §2 的 9 個 svcomp26-vguide config（注意 `../../` 路徑）
2. §3 的 run.sh / run_benchmark_set.sh 改動 + 2 題煙霧驗證（含 recursive）
3. `ant build-project` 不需要（純 config/script）；但跑前確認 HEAD 含 `c13cadc132`
4. §4 full-set 執行（nohup）
5. §5 分析報告
6. 全程不改 svcomp26/svcomp27 官方檔、不改 `vguide.properties` 參數、不改 Java、不 merge main

---

## 7. 實作狀態（2026-06-14）

| 項目 | 狀態 | 摘要 |
|------|------|------|
| 9 個 svcomp26-vguide config 變體 | DONE | top `#include ../vguide.properties` + `maxLlmRoundsPerProcess=10`；predicate 元件僅 `useVocabularyGuide=true`（vguide 選項不可在 nested 重複 include，否則 `--option` 排程失效） |
| Runner `--mode svcomp26-vguide` | DONE | `run.sh` 加 mode（require_api、`VGUIDE_SVCOMP=1`、`config/unmaintained/svcomp26-vguide.properties`、reachability spec、out `<set>_svcomp26_vguide`）；`run_benchmark_set.sh` 的 SVCOMP_MODE fallback 加 `*svcomp26-vguide*`（**不**動 svcomp26.properties stock 的 baseline 跑法）；既有 mode 行為不變；`bash -n` 通過 |
| svcomp27-vguide 標記 | DONE | `config/svcomp27-vguide.properties` header 加 NOTE：非當前實驗主線，保留供未來 trunk 對齊；當前實驗用 svcomp26-vguide |
| 3 向煙霧驗證 | DONE | (1) `overflow_1-1` svcomp26-vguide → **TRUE** + vguide fired；(2) 同題 svcomp26 stock → UNKNOWN（對照，印證 v1.5 VGuide-only solve；`aggregateBasicBlocks` mismatch INFO 官方 stock 亦有，非變體引入）；(3) `recursive/Ackermann01-2` svcomp26-vguide → BAM fallback 觸發、vguide 完全未開（enabled=0, LLM rounds=0）、零 exception、不 crash |
| Full-set 執行 | DONE | `loops_reachsafety_unreach_svcomp26vguide_20260614`：764/764 completed；341 TRUE / 152 FALSE / 271 UNKNOWN = **493 solved**；0 wrong；PAR-2 avg 216.90s |
| 分析報告 | DONE | [`reports/2026-06-14_svcomp26_vguide_loops.md`](reports/2026-06-14_svcomp26_vguide_loops.md)：vs svcomp26 baseline +7 solved；17 new / 10 lost；16 direct LLM predicate wins；`watermelon` UNKNOWN exception caveat |

Java 層完全未改（BAM guard / process cap / `call_start_epoch_ms` timestamp 皆與 config 版本無關，沿用 svcomp27 既有驗證）。

---

## 8. Full-set 結果（v1.5.1, 2026-06-14）

正式 full-set 已完成；完整分析見 [`reports/2026-06-14_svcomp26_vguide_loops.md`](reports/2026-06-14_svcomp26_vguide_loops.md)。

| Run | TRUE | FALSE | UNKNOWN | Solved | Wrong | PAR-2 avg |
|-----|-----:|------:|--------:|-------:|------:|----------:|
| svcomp26 baseline | 334 | 152 | 278 | 486 | 0 | 222.45s |
| **svcomp26-vguide** | **341** | **152** | **271** | **493** | **0** | **216.90s** |

Delta vs svcomp26：**17 new solves / 10 lost solves / 0 disagreements / net +7 solved**。
其中 **16 new solves** 由 `svcomp26-vguide--*predicateAnalysis.properties` 在 `llm_rounds > 0` 下直接決定，
是本次 v1.5.1 的主要 claim。

保守 claim 邊界：這不是 strict superset（10 lost solves），也不是正式離線 SV-COMP submission；
但它是同一個 svcomp26 portfolio base 上的乾淨正增益。


---

## 9. v1.5.2+ 後續方向

本文件記錄 v1.5.1 full-set（reachability）。後續分兩條線：

- **v1.5.2（調 PredicateCPA / portfolio）**：[`SVCOMP26_PORTFOLIO_LLM_PLAN.md`](SVCOMP26_PORTFOLIO_LLM_PLAN.md)。
  targeted rerun 只作為診斷；正式 runtime 沒有外部 retry，要做 single-run 的 routing / budget / guard / fallback。
- **v1.6（泛化到其他 property branch）**：[`LLM_RESEARCH_ROADMAP.md`](LLM_RESEARCH_ROADMAP.md) +
  現行第一刀 [`SVCOMP26_OVERFLOW_VGUIDE_PLAN.md`](SVCOMP26_OVERFLOW_VGUIDE_PLAN.md)——
  把這裡證明的 predicate-CEGAR hook，零 Java 套到 NoOverflow（Class-A）上，驗證能否泛化。
