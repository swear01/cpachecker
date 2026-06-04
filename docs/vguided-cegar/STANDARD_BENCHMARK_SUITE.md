# VGuide 標準測試集（Standard Benchmark Suite）

> **用途：** 評估 Unified VGuide 主路徑（spurious → Java LLM → 驗證 → loop-head 注入）。  
> **不是** SV-COMP 官方池；舊稱「官方 20 題」= **Legacy timeout-context pool（v1）**，見 [NO_SPURIOUS_STATISTICS.md](NO_SPURIOUS_STATISTICS.md)。

## Tier 結構（請勿把 8 題當「完整標準」）

| Tier | 題數 | 用途 |
|------|------|------|
| **S-Sample** | **8** | CI、離線 LLM 抽樣、單機快速回歸 |
| **Rescue-Core** | 6 | 核心 rescue（略少於 sample） |
| **Full-Scalar** | classifier `RUN_SCALAR`（本機 manifest 已解析子集，見下） | 盡量多跑 scalar 候選 |
| **Full-Array-Scalar** | ~8–10 | array-scalar 瓶頸題 |
| **F-Frozen** | 2 + Legacy 20 | Exception／frozen；**不**計 LLM 主路徑成功率 |

Manifest：`docs/vguided-cegar/benchmark_sets/*.list`（`run.sh bench-regen` 重生）  
執行：**`scripts/vguided-cegar/run.sh`**。首次請 `bench-setup` 再 **`bench-reclassify`**（見 [RUN_EXPERIMENTS.md](RUN_EXPERIMENTS.md)）。

---

## Tier S-Sample（8 題）— 僅為 **sample 標準**

| ID | 任務 | 路徑 | 類別 |
|----|------|------|------|
| S1 | `up` | `loop-invgen/up.i` | scalar rescue |
| S2 | `down` | `loop-invgen/down.i` | scalar rescue |
| S3 | `string_concat-noarr` | `loop-invgen/string_concat-noarr.i` | scalar rescue |
| S4 | `array_3-1` | `loop-acceleration/array_3-1.i` | array-scalar |
| S5 | `large_const` | `loop-invgen/large_const.i` | array-scalar |
| S6 | `heapsort` | `loop-invgen/heapsort.i` | array-scalar |
| S7 | `array_3-2` | `loop-acceleration/array_3-2.i` | array-scalar |
| S8 | `array_4` | `loop-acceleration/array_4.i` | array-scalar |

**Bench root：** `SV_BENCHMARKS`（預設 **`$HOME/sv-benchmarks/c`**）。

```bash
# Loop 相關完整（ReachSafety-Loops.set + bitvector-loops）
./scripts/vguided-cegar/run.sh bench-setup --profile=loops-full

# 建議完整包：ReachSafety + P1（NoOverflows + uthash-ReachSafety）
./scripts/vguided-cegar/run.sh bench-setup --profile=recommended

# 僅 ReachSafety
./scripts/vguided-cegar/run.sh bench-setup --profile=reachsafety
```

### 排除（不在 sample）

| 任務 | 原因 |
|------|------|
| `id_build` | 太易 |
| `half_2`, `seq-3` | Tier F frozen |
| Legacy 20 池 | 100% NO_SPURIOUS |
| `doc/examples/example.c` | 啟動 smoke only |

---

## SV-COMP 與 `full_scalar` 的關係（請先讀）

| 名稱 | 是什麼 |
|------|--------|
| **`full_scalar`** | **本專案 manifest 名稱**，不是 SV-COMP 競賽表上的 category |
| **SV-COMP 對照 track** | **ReachSafety-Loops**（例如 SV-COMP 2025 該類 CPAchecker 參考分 **922 / 774 題**） |
| **程式來源** | 官方 [`sosy-lab/sv-benchmarks`](https://github.com/sosy-lab/sv-benchmarks)，安裝於 **`~/sv-benchmarks/`**（見下表 profile） |
| **安裝路徑** | **`$HOME/sv-benchmarks/c`** = `export SV_BENCHMARKS` 的程式根目錄；repo 根為 `~/sv-benchmarks` |
| **下載 profile** | 見下表；`bench-setup --profile=…` |

### 建議下載哪些 SV-COMP category？

| 優先 | Profile / set | 適合 VGuide 的原因 |
|------|----------------|-------------------|
| **P0** | **`reachsafety`** | 老師建議的 **ReachSafety** 全類；與 `default.spc`（unreach-call）一致；PredicateCPA 主戰場 |
| **P0** | **`loops-full`** | 僅 **ReachSafety-Loops** + `bitvector-loops`；論文主線、較小、已含 `full_scalar` 來源 |
| **P1** | **`p1`** profile（已併入 **`recommended`**） | `NoOverflows-BitVectors` + `NoOverflows-Other` + `uthash-2.0.2`；溢出題需另選 `.prp` |
| **P2** | `Termination-Main*` | **終止性**（不同 property）；僅在要擴充研究範圍時 |
| **通常略過** | `MemSafety-*`、`ConcurrencySafety-*` | property 不同（記憶體／資料競爭），需改 spec，與現行 VGuide 管線不一致 |
| **通常略過** | `SoftwareSystems-*`（整包） | 超大、偏產品碼；可只挑單一 `SoftwareSystems-uthash-ReachSafety` 等小 set |

你目前已用 **`reachsafety`（~2GB）** 即已涵蓋 **Loops + Arrays + Heap + ControlFlow + BitVectors + …**；**不必**再為 loop 單獨下載一份，除非想縮小磁碟用量改 `--profile=loops-full`。
| **篩選規則** | Classifier 標 **`RUN_SCALAR`** → 再排除 `id_build`, `half_2`, `seq-3` → **217 題** |

因此：

- **`full_scalar` ⊂（loop 相關 benchmarks 的 scalar 子集）**，**≠** ReachSafety-Loops 全量（774 題）。
- 217 題橫跨多個 **sv-benchmarks 子目錄**（資料夾名，非 SV-COMP category），例如 `loop-zilu`（53）、`loops-crafted-1`（50）、`loops`（28）、`loop-acceleration`（28）、`loop-lit`（15）、`loop-invgen`（14）等；完整分布見 `full_scalar.list`。
- **陣列相關但只抽象 index scalar** 的題在 **`full_array_scalar.list`**（`RUN_ARRAY_SCALAR`，8 題），**不**併入 `full_scalar`。
- 論文／報告應寫：**「在 SV-COMP loop benchmarks（ReachSafety-Loops 來源）上，我們的 scalar 主路徑子集 217 題」**；勿稱 `full_scalar` 等於官方某一 SV-COMP category 全體。

---

## Tier Full — 官方 sv-benchmarks 對齊（已重跑 classifier）

來源：`run.sh bench-reclassify` → `scalar_classified.csv` + `~/sv-benchmarks/c`

| Manifest | 題數 | 說明 |
|----------|------|------|
| **`full_scalar.list`** | **217** | `RUN_SCALAR`（220）− `id_build,half_2,seq-3`；**0 missing** |
| **`full_array_scalar.list`** | **8** | `RUN_ARRAY_SCALAR` 全收錄 |
| `excluded_fmpa2_legacy.list` | **11** | 僅 FMPA2 舊樹有、**官方 repo 無** — **已移除，不補檔** |

清單說明：[benchmark_sets/README.md](benchmark_sets/README.md)

**不納入 Full 主路徑：** `PARSER_RISK`、`RUN_ARRAY_SELECT_EXPERIMENTAL`（需 select，與 VGuide 假設不符）。

---

## Tier F — Frozen / Exception

| 任務 | 說明 |
|------|------|
| `half_2`, `seq-3` | 0 ref；frozen 對照 |
| Legacy 20 池 | 舊 v1 診斷；勿稱官方 |

---

## LLM 排程（依延遲設計，非 every_n=5）

**實測：** LLM p50 ~**1s**、p99 ~**1.5s**；`array_3-1` refinement ~**0.21s/次**（60s 內 4 ref）。

→ 快題必以 **`min_interval` 為主**；`every_n` 應 **很大**（否則數秒內連打 API）。

詳細公式與預設：**[LLM_CALL_SCHEDULING.md](LLM_CALL_SCHEDULING.md)**  
`config/vguide.properties` 預設（**tier_s_15s**）：

| 參數 | 值 |
|------|-----|
| `llmCallSchedule` | `every_n_and_interval` |
| `llmEveryNSpuriousRefinements` | **72** |
| `llmMinIntervalSec` | **15** |
| `maxLlmRoundsPerAnalysis` | **5**（每 **輪** spurious 計 1，非每 HTTP） |
| `llmSamplesPerCall` | **1**（>1 時見 [LLM_ENSEMBLE.md](LLM_ENSEMBLE.md)） |
| `llmSampleParallelism` | **4** |

單題覆寫範例仍可用 CLI `--option vguide.*=...`。

---

## 離線抽樣 vs CPA 內 LLM

**為何會不一致？** 離線腳本沒有真實 `ContextPack`／SSA 合約／spurious 當下狀態，prompt 與時機都不同。  
說明全文：**[OFFLINE_SAMPLING.md](OFFLINE_SAMPLING.md)**

離線（cheap regression）：

```bash
export DEEPSEEK_API_KEY=...
export VGUIDE_BENCH_ROOT="$SV_BENCHMARKS"
export VGUIDE_LLM_QUALITY_TASKS=up,down,array_3-1,string_concat-noarr
# 預設 VGUIDE_LLM_QUALITY_PARALLEL=16（題目 + 各 run 平行）
python3 scripts/vguided-cegar/test_llm_proposal_quality.py
```

CPA 驗收：`vguide.writeArtifacts=true` → `output/vguide/round_*/`.

---

## 標準 CPA 指令（單題）

```bash
export JAVA=/path/to/jdk-21/bin/java
export DEEPSEEK_API_KEY=...
export SV_BENCHMARKS=$HOME/sv-benchmarks/c

scripts/cpa.sh \
  --heap 2000M \
  --config config/predicateAnalysis-vguide.properties \
  --option cpa.predicate.refinement.useVocabularyGuide=true \
  --option vguide.writeArtifacts=true \
  --timelimit 300s \
  --spec config/specification/default.spc \
  --no-output-files \
  "$SV_BENCHMARKS/loop-acceleration/array_3-1.i"
```

（排程預設已寫入 `vguide.properties`，不必每次手打 everyN/minInterval。）

---

## 執行實驗（`run.sh`）

```bash
./scripts/vguided-cegar/run.sh bench-setup
./scripts/vguided-cegar/run.sh cpa --set sample
./scripts/vguided-cegar/run.sh cpa --set sample --mode stock
./scripts/vguided-cegar/run.sh cpa --set full_scalar --parallel 16
./scripts/vguided-cegar/run.sh verify-pack --task array_3-1
```

詳見 [RUN_EXPERIMENTS.md](RUN_EXPERIMENTS.md)。

---

## 相關文件

- [LLM_CALL_SCHEDULING.md](LLM_CALL_SCHEDULING.md) — 排程推導
- [OFFLINE_SAMPLING.md](OFFLINE_SAMPLING.md) — 離線 vs CPA
- [LLM_QUALITY_SAMPLE.md](LLM_QUALITY_SAMPLE.md) — 抽樣結果
- [NO_SPURIOUS_STATISTICS.md](NO_SPURIOUS_STATISTICS.md) — Legacy / Exception
