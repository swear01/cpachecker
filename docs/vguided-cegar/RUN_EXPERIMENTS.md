# 如何跑實驗（`scripts/vguided-cegar/run.sh`）

單一入口腳本，**不用** `run_full_experiment.sh`。資料與 benchmark 皆在 **`$HOME`**，不依賴 FMPA2 路徑。

## 0. 一次性環境

```bash
# Benchmark：官方 sv-benchmarks sparse（**非整庫 138k 檔**）
cd /home/swear01/cpachecker
chmod +x scripts/vguided-cegar/run.sh scripts/vguided-cegar/setup_benchmarks.sh
./scripts/vguided-cegar/run.sh bench-setup
./scripts/vguided-cegar/run.sh bench-reclassify   # 對齊官方樹：重 discover + classify + 重生 list

export SV_BENCHMARKS="$HOME/sv-benchmarks-vguide/c"
export DEEPSEEK_API_KEY="..."
export JAVA="$HOME/jdk-21/bin/java"   # 需 Java 21+，見 LOCAL_DEVELOPMENT_ENV.md
export PATH="$HOME/.local/ant/bin:$(dirname "$JAVA"):$PATH"

# 改 Java 後
ant -f /home/swear01/cpachecker/build.xml build-project
```

| 路徑 | 用途 |
|------|------|
| `~/sv-benchmarks-vguide/` | [sosy-lab/sv-benchmarks](https://github.com/sosy-lab/sv-benchmarks) sparse checkout |
| `~/sv-benchmarks-vguide/c/` | **`SV_BENCHMARKS`**：實際 `.i`/`.c` 程式根目錄 |
| profile `loops-full` | **ReachSafety-Loops.set** 內所有目錄 + `bitvector-loops`（loop 完整） |
| profile `reachsafety` | 全部 **`c/ReachSafety-*.set`** 任務樹（**~2GB**，含 Arrays/Heap/Loops/…） |
| `~/cpachecker` 或 clone 路徑 | 本 repo |
| `output/vguide/` | CPA artifacts、`round_*/prompt.txt` |

DeepSeek rate limit **~500/min** → 預設 **平行**（`PARALLEL=8` CPA、`16` 離線 LLM）。

---

## 1. 命令總覽

```bash
./scripts/vguided-cegar/run.sh help

./scripts/vguided-cegar/run.sh bench-setup --profile=reachsafety   # ReachSafety 全類（建議）
./scripts/vguided-cegar/run.sh bench-setup --profile=loops-full  # 僅 loop 相關完整
./scripts/vguided-cegar/run.sh bench-setup       # 同 loops-full（預設）
./scripts/vguided-cegar/run.sh bench-reclassify # **推薦**：官方樹上重跑 classifier + list
./scripts/vguided-cegar/run.sh bench-regen       # 只重生 list（不重新 classify）

./scripts/vguided-cegar/run.sh cpa --set sample                    # VGuide，8 題
./scripts/vguided-cegar/run.sh cpa --set sample --mode stock       # 對照：無 VGuide
./scripts/vguided-cegar/run.sh cpa --set full_scalar --parallel 16
./scripts/vguided-cegar/run.sh cpa --set full_array_scalar

./scripts/vguided-cegar/run.sh llm-quality
./scripts/vguided-cegar/run.sh llm-quality --tasks up,array_3-1 --runs 5 --parallel 20

./scripts/vguided-cegar/run.sh verify-pack --task array_3-1   # CPA 內真實 ContextPack + artifacts
```

---

## 2. Benchmark 測試集怎麼來（與官方 sv-benchmarks 對齊）

**SV-COMP：** `full_scalar` **不是**官方 category 名稱；程式來自 **ReachSafety-Loops 相關**的 `sv-benchmarks` loop 子樹，再經 classifier **`RUN_SCALAR`** 篩成 **217 題**子集（≠ Loops 全量 774 題）。見 [STANDARD_BENCHMARK_SUITE.md § SV-COMP](STANDARD_BENCHMARK_SUITE.md#sv-comp-與-full_scalar-的關係請先讀)。

1. **Discover**：`discover_loop_programs.py` 掃 `~/sv-benchmarks-vguide/c` 下所有 `loop*` / `loops*` 目錄（324 程式，優先 `.i`）。
2. **Classify**：`classify_bootstrap_targets.py --csv` → `results/.../scalar_classified.csv`（**請用 `bench-reclassify` 產生**，勿沿用舊 FMPA2 版）。
3. **Regen**：`regenerate_benchmark_lists.py` → `docs/.../benchmark_sets/*.list`。
4. **排除**（主路徑 full 集）：`id_build`, `half_2`, `seq-3`。

**已移除 11 題**（僅 FMPA2）：見 `benchmark_sets/excluded_fmpa2_legacy.list`。  
舊 classifier 備份：`scalar_classified_fmpa2_legacy.csv`（對照用，勿用於 regen list）。

| Set | 說明 | 題數（`bench-reclassify` 後） |
|-----|------|-------------------------------|
| `sample` | 手選 Tier S | 8 |
| `rescue_core` | 核心 rescue | 6 |
| `full_scalar` | `RUN_SCALAR` − 排除 | **217**（resolved **217/217**） |
| `full_array_scalar` | `RUN_ARRAY_SCALAR` − 排除 | **8**（8/8） |
| `frozen_exception` | half_2, seq-3 | 2 |

Classifier 摘要（324 程式）：`RUN_SCALAR` 220、`RUN_ARRAY_SCALAR` 8、其餘 SKIP/UNKNOWN 等。

更新流程：`run.sh bench-reclassify`（非只 `bench-regen`）。

---

## 3. 建議實驗順序（完整評估）

| 步驟 | 命令 | 目的 |
|------|------|------|
| L1 | `run.sh llm-quality` | 離線 JSON／L1 合約 |
| L2 | `run.sh cpa --set sample` | 主路徑 8 題 |
| L3 | `run.sh cpa --set sample --mode stock` | PredicateCPA 對照 |
| L4 | `run.sh verify-pack --task array_3-1` | **CPA 內 ContextPack**（`round_*/prompt.txt`） |
| L5 | `run.sh cpa --set full_scalar --parallel 16` | VGuide 規模實驗 |
| L5b | `run.sh cpa --set full_scalar --mode stock` | **同設定 baseline**（必與 L5 配對） |
| L6 | `run.sh cpa --set full_array_scalar` | array-scalar |
| L7 | `run.sh cpa --set frozen_exception` | frozen 對照（不計 LLM 成功率） |

輸出 CSV：`output/vguide/batch/<set>_summary.csv`（`--out` 可改 `VGUIDE_OUT_BASE`）。

---

## 4. `cpa` 參數

| 參數 | 預設 | 說明 |
|------|------|------|
| `--set` | （必填） | `sample` / `full_scalar` / … |
| `--mode` | `vguide` | `stock` = `useVocabularyGuide=false` |
| `--parallel` | `8` | `VGUIDE_PARALLEL` |
| `--timelimit` | `300` | 秒 |
| `--heap` | `2000M` | |
| `--out` | `output/vguide/batch` | |
| `--dry-run` | | 只印命令 |
| `--` 之後 | | 傳給 `cpa.sh` 的額外 `--option` |

排程預設見 `config/vguide.properties`（`tier_s_15s`：`min_interval=15`，`every_n=72`）。多抽卡見 [LLM_ENSEMBLE.md](LLM_ENSEMBLE.md)。覆寫例：

```bash
./scripts/vguided-cegar/run.sh cpa --set sample -- \
  --option vguide.llmCallSchedule=first_spurious
  --option vguide.llmSamplesPerCall=3 --option vguide.llmSampleParallelism=3
```

---

## 5. ContextPack 重驗

`verify-pack` 跑**單題** CPA，強制 `first_spurious` + `writeArtifacts`，檢查：

- `output/vguide/round_*/prompt.txt` — 含 Variable contract、loop heads、源碼
- `output/vguide/round_*/response.txt` — LLM 原始回應

與離線 `test_llm_proposal_quality.py` 的差異見 [OFFLINE_SAMPLING.md](OFFLINE_SAMPLING.md)。

---

## 6. Stock baseline 與對照（`compare_official_reference.py`）

**公平對照**：與 VGuide **相同** `--config`、timelimit、heap、benchmark 樹，僅關閉 LLM：

```bash
./scripts/vguided-cegar/run.sh cpa --set full_scalar --mode stock --parallel 8 --timelimit 300 \
  --out output/vguide/experiments/full_scalar_stock_interval15

python3 scripts/vguided-cegar/compare_official_reference.py \
  --baseline stock \
  --vguide-logs output/vguide/experiments/full_scalar_vguide_interval15/logs \
  --baseline-logs output/vguide/experiments/full_scalar_stock_interval15/logs \
  --manifest docs/vguided-cegar/benchmark_sets/full_scalar.list
```

| 項目 | 說明 |
|------|------|
| Stock | `VGUIDE_USE_VOCABULARY_GUIDE=false`；**不需** `DEEPSEEK_API_KEY` |
| 可比題數 | 兩邊皆有 `logs/<task>.log`（目標 **217/217**） |
| Legacy | `--baseline fmpa2` 用舊 FMPA2 結果檔，**不作**主報告數字 |

詳見 [報告 §4.4](2026-06-04-vguided-cegar-report.md#44-對照-baseline同設定-stock無-llm)。

---

## 7. 相關文件

- [2026-06-04-vguided-cegar-report.md](2026-06-04-vguided-cegar-report.md)（§4.4 對照基準）
- [STANDARD_BENCHMARK_SUITE.md](STANDARD_BENCHMARK_SUITE.md)
- [LOCAL_DEVELOPMENT_ENV.md](LOCAL_DEVELOPMENT_ENV.md)
- [LLM_CALL_SCHEDULING.md](LLM_CALL_SCHEDULING.md)
