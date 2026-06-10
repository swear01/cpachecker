# Benchmark manifest 清單

與 **官方** `~/sv-benchmarks`（[`sosy-lab/sv-benchmarks`](https://github.com/sosy-lab/sv-benchmarks) sparse）對齊。

| 路徑 | 內容 |
|------|------|
| `~/sv-benchmarks/` | git clone 根目錄 |
| **`~/sv-benchmarks/c/`** | **`SV_BENCHMARKS`** — 所有 benchmark 原始檔 |
| `c/ReachSafety-*.set` | SV-COMP **ReachSafety** 子類定義（競賽 category） |

下載：`run.sh bench-setup --profile=reachsafety`（全 ReachSafety）或 `--profile=loops-full`（僅 Loops 類）。  
重生 manifest：`./scripts/vguided-cegar/run.sh bench-reclassify`

## `full_scalar` 是 SV-COMP 的哪個 category？

**不是。** `full_scalar` 是 VGuide **專案內的 set 名稱**（`--set full_scalar`），不是 SV-COMP 競賽表上的 category 欄位。

| 對照 | 說明 |
|------|------|
| **SV-COMP track（成績對照用）** | **ReachSafety-Loops**（reachability + loops 子類） |
| **實驗數字對照 baseline** | 本機 **`--mode stock`** batch（同 config、無 LLM），輸出 `full_scalar_stock/`；`compare_official_reference.py --baseline stock`。FMPA2 僅 `--baseline fmpa2` legacy。見報告 **§4.4** |
| **我們的 `full_scalar`** | 從上述 loop 目錄 discover 後，classifier **`RUN_SCALAR`**，再排除 `id_build` / `half_2` / `seq-3` → **217 題** |

217 題的檔案路徑分佈在 `loop-zilu`、`loops-crafted-1`、`loops`、`loop-acceleration` 等多個 **sv-benchmarks 子目錄**；詳見 [STANDARD_BENCHMARK_SUITE.md § SV-COMP 與 full_scalar](../evaluation/STANDARD_BENCHMARK_SUITE.md#sv-comp-與-full_scalar-的關係請先讀)。

## 實驗用 set

| 檔案 | 用途 | 題數 |
|------|------|------|
| `sample.list` | Tier S 手選（CI / smoke） | 8 |
| `regression_nothink.list` | non-thinking / budget 實驗 regression | 19 |
| `rescue_core.list` | 核心 rescue | 6 |
| **`full_scalar.list`** | 主路徑 scalar（`RUN_SCALAR` − 排除） | **217** |
| `frozen_exception.list` | frozen 對照（`half_2`, `seq-3`） | 2 |

## 排除（不進 `full_scalar`）

| 檔案 | 說明 |
|------|------|
| `excluded_fmpa2_legacy.list` | **11 題**：僅曾出現在 FMPA2 舊快照，**官方 repo 已無** — 已移除，勿補檔 |
| （邏輯排除） | `id_build`（太易）、`half_2` / `seq-3`（frozen，見 `frozen_exception.list`） |

## 特殊題備註（仍留在 manifest）

| 題目 | 說明 |
|------|------|
| **`watermelon`** | 源碼有 `int true` / `int false` 全域變數；PredicateCPA 插值原子化時與 **SMT-LIB2 保留字**衝突 → **ERROR**（infrastructure crash）。**不**當 VGuide 方法失敗；彙總時備註即可。見報告 §4.5.1。 |

## 不納入 VGuide 主路徑（另類）

Classifier 另有多類，**未**寫入 `full_*` manifest，例如：

- `RUN_ARRAY_SELECT_EXPERIMENTAL`（需 select）
- `PARSER_RISK`、`SKIP_*`

見 `results/vguided-cegar/classifier/scalar_classified.csv`。

## 舊資料

- `scalar_classified_fmpa2_legacy.csv` — 舊 96 題分類，僅對照用
- `regen_report.txt` — 由 `bench-regen` 產生（可忽略；歷史副本在 `archive/vguided-docs/benchmark_sets/`）
