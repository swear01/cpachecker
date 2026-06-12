# 如何跑實驗（`scripts/vguided-cegar/run.sh`）

單一入口腳本，**不用** `run_full_experiment.sh`。資料與 benchmark 皆在 **`$HOME`**，不依賴 FMPA2 路徑。

## 0. 一次性環境

```bash
# Benchmark：官方 sv-benchmarks sparse（**非整庫 138k 檔**）
cd /home/swear01/cpachecker
chmod +x scripts/vguided-cegar/run.sh scripts/vguided-cegar/setup_benchmarks.sh
./scripts/vguided-cegar/run.sh bench-setup
./scripts/vguided-cegar/run.sh bench-reclassify   # 對齊官方樹：重 discover + classify + 重生 list

export SV_BENCHMARKS="$HOME/sv-benchmarks/c"
export DEEPSEEK_API_KEY="..."
export JAVA="$HOME/.local/bin/java"   # 需 Java 21+，見 LOCAL_DEVELOPMENT_ENV.md
export PATH="$HOME/.local/ant/bin:$(dirname "$JAVA"):$PATH"

# 改 Java 後
ant -f /home/swear01/cpachecker/build.xml build-project
```

| 路徑 | 用途 |
|------|------|
| `~/sv-benchmarks/` | [sosy-lab/sv-benchmarks](https://github.com/sosy-lab/sv-benchmarks) sparse checkout |
| `~/sv-benchmarks/c/` | **`SV_BENCHMARKS`**：實際 `.i`/`.c` 程式根目錄 |
| profile **`recommended`** | **ReachSafety + P1**（建議；含 NoOverflows、uthash-ReachSafety） |
| profile `reachsafety` | 全部 **`c/ReachSafety-*.set`**（~2GB） |
| profile `p1` | **NoOverflows-*** + **SoftwareSystems-uthash-ReachSafety** |
| profile `loops-full` | **ReachSafety-Loops** + `bitvector-loops`（較小） |
| `~/cpachecker` 或 clone 路徑 | 本 repo |
| `output/vguide/experiments/` | batch 產物（`logs/<task>.log`、summary CSV） |

DeepSeek rate limit **~500/min** → 預設 **平行**（`PARALLEL=8` CPA、`16` 離線 LLM）。預設 model：**`deepseek-v4-pro`**（`DEEPSEEK_MODEL` 可覆寫）。

---

## 1. 命令總覽

```bash
./scripts/vguided-cegar/run.sh help

./scripts/vguided-cegar/run.sh bench-setup --profile=recommended  # ReachSafety + P1（預設）
./scripts/vguided-cegar/run.sh bench-setup --profile=reachsafety
./scripts/vguided-cegar/run.sh bench-setup --profile=p1           # 僅 P1 加購
./scripts/vguided-cegar/run.sh bench-setup --profile=loops-full
./scripts/vguided-cegar/run.sh bench-reclassify # **推薦**：官方樹上重跑 classifier + list
./scripts/vguided-cegar/run.sh bench-regen       # 只重生 list（不重新 classify）

./scripts/vguided-cegar/run.sh cpa --set sample                    # -> sample_vguide（8 題）
./scripts/vguided-cegar/run.sh cpa --set sample --mode stock       # -> sample_stock
./scripts/vguided-cegar/run.sh cpa --set full_scalar --parallel 16  # -> full_scalar_vguide

./scripts/vguided-cegar/run.sh llm-quality
./scripts/vguided-cegar/run.sh llm-quality --tasks up,array_3-1 --runs 5 --parallel 20

./scripts/vguided-cegar/run.sh verify-pack --task array_3-1   # CPA 內真實 ContextPack + artifacts
```

---

## 2. Benchmark 測試集怎麼來（與官方 sv-benchmarks 對齊）

**SV-COMP：** `full_scalar` **不是**官方 category 名稱；程式來自 **ReachSafety-Loops 相關**的 `sv-benchmarks` loop 子樹，再經 classifier **`RUN_SCALAR`** 篩成 **217 題**子集（≠ Loops 全量 774 題）。見 [STANDARD_BENCHMARK_SUITE.md § SV-COMP](evaluation/STANDARD_BENCHMARK_SUITE.md#sv-comp-與-full_scalar-的關係請先讀)。

1. **Discover**：`discover_loop_programs.py` 掃 `~/sv-benchmarks/c` 下所有 `loop*` / `loops*` 目錄（324 程式，優先 `.i`）。
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
| `frozen_exception` | half_2, seq-3 | 2 |

Classifier 摘要（324 程式）：`RUN_SCALAR` 220、`RUN_ARRAY_SCALAR` 8、其餘 SKIP/UNKNOWN 等。

更新流程：`run.sh bench-reclassify`（非只 `bench-regen`）。

---

## 3. 建議實驗順序（完整評估）

| 步驟 | 命令 | 目的 |
|------|------|------|
| L1 | `run.sh llm-quality` | 離線 JSON／L1 合約 |
| L2 | `run.sh cpa --set sample` | 8 題 → `experiments/sample_vguide/` |
| L2c | `post_batch_analysis.sh`（sample） | 同 full_scalar：verdict + PAR-2 + cactus |
| L3 | `run.sh cpa --set sample --mode stock` | 對照 → `experiments/sample_stock/` |
| L4 | `run.sh verify-pack --task array_3-1` | **CPA 內 ContextPack**（`verify_pack_*/cpa.log`） |
| L5 | `run.sh cpa --set full_scalar --parallel 16` | VGuide 規模實驗 |
| L5b | `run.sh cpa --set full_scalar --mode stock` | **同設定 baseline**（必與 L5 配對） |
| L5c | `post_batch_analysis.sh`（§6.2） | **PAR-2 + cactus + verdict**（必跑） |
| L6 | `run.sh cpa --set frozen_exception` | frozen 對照（不計 LLM 成功率） |

**預設輸出目錄**（`--out` 可覆寫）：

| `--set` | VGuide | stock |
|---------|--------|-------|
| `sample` | `output/vguide/experiments/sample_vguide/` | `.../sample_stock/` |
| `full_scalar` | `.../full_scalar_vguide/` | `.../full_scalar_stock/` |

每目錄含 `logs/<task>.log`、`<set>_summary.csv`。

---

## 4. `cpa` 參數

| 參數 | 預設 | 說明 |
|------|------|------|
| `--set` | （必填） | `sample` / `full_scalar` / … |
| `--mode` | `vguide` | `stock` = `useVocabularyGuide=false` |
| `--parallel` | `8` | `VGUIDE_PARALLEL` |
| `--timelimit` | `300` | 秒 |
| `--heap` | `2000M` | |
| `--out` | `output/vguide/experiments/<set>_vguide` 或 `_stock` | 見上表 |
| `--dry-run` | | 只印命令 |
| `--` 之後 | | 傳給 `cpa.sh` 的額外 `--option` |

排程與 LLM 預設見 `config/vguide.properties`。**v1.4 計劃**：`dualPromptMode=true`，`llmSamplesPerCall=1` = **SAFE×1 + BUG×1** / 輪。見 [DUAL_PROMPT_V1_PLAN.md](analysis/DUAL_PROMPT_V1_PLAN.md)、[LLM_ENSEMBLE.md](llm/LLM_ENSEMBLE.md)、[PREDICATE_BUDGET.md](llm/PREDICATE_BUDGET.md)。覆寫例：

```bash
# 僅 first spurious、單次 draw（省 API，對照舊 batch）
./scripts/vguided-cegar/run.sh cpa --set sample -- \
  --option vguide.llmCallSchedule=first_spurious \
  --option vguide.llmSamplesPerCall=1

# 單輪更多 predicate（仍 1 API）
./scripts/vguided-cegar/run.sh cpa --set sample -- \
  --option vguide.minPredicatesPerCall=4 --option vguide.maxPredicatesPerCall=8

# v1.4 計劃：dual + K=3 → SAFE×3 + BUG×3 = 6 HTTP/輪（每軌 1 sync + 2 parallel）
# ./scripts/vguided-cegar/run.sh cpa --set sample -- \
#   --option vguide.dualPromptMode=true --option vguide.llmSamplesPerCall=3

# v1.3.0（已跑）：freq10/n24 + adaptive
export VGUIDE_CONFIG=config/vguide-experiment-freq10-n24.properties
export VGUIDE_LLM_THINKING=disabled

# v1.4（已跑 20260610）：dual + ce_summary — 155 solved，FALSE 目標未達
# export VGUIDE_CONFIG=config/vguide-experiment-dual-prompt-v1.properties
# 報告：docs/vguided-cegar/reports/2026-06-10_dual_prompt_v1_noL3.md

# 下一版 freq20/n12（未含 dual，待跑）
export VGUIDE_CONFIG=config/vguide-experiment-freq20-n12.properties

./scripts/vguided-cegar/run.sh cpa --set full_scalar --ablation no-l3 --parallel 8 --timelimit 300 \
  --out output/vguide/experiments/full_scalar_vguide_noL3_freq20_n12_adaptive_<date>
```

---

## 5. ContextPack 重驗

`verify-pack` 跑**單題** CPA，強制 `first_spurious`，log 寫入 `output/vguide/verify_pack_<task>/cpa.log`，檢查：

- `VGuide LLM model:`、`VGuide LLM round`、`VGuide predicate` 行

與離線 `test_llm_proposal_quality.py` 的差異見 [OFFLINE_SAMPLING.md](llm/OFFLINE_SAMPLING.md)。

---

## 6. Stock baseline 與批次後分析（**必跑**）

### 6.1 跑 stock（與 VGuide 同設定、無 LLM）

```bash
# full_scalar（預設寫入 full_scalar_stock/）
./scripts/vguided-cegar/run.sh cpa --set full_scalar --mode stock --parallel 8 --timelimit 300

# sample 冒煙（預設寫入 sample_stock/）
./scripts/vguided-cegar/run.sh cpa --set sample --mode stock --parallel 8 --timelimit 300
```

| 項目 | 說明 |
|------|------|
| Stock | `VGUIDE_USE_VOCABULARY_GUIDE=false`；**不需** `DEEPSEEK_API_KEY` |
| 可比題數 | 兩邊皆有 `logs/<task>.log`（目標 **217/217**） |

### 6.2 批次後分析（**每次 VGuide + stock 跑完都要做**）

不要只跑 `compare_official_reference.py`。請用 **`post_batch_analysis.sh`** 一次產出：

| 產物 | 內容 |
|------|------|
| `vs_stock_baseline.txt` | Verdict 桶：變好 / **持平** / 變差（持平 = 桶相同，≠ 時間相同） |
| `analysis_vs_stock.txt` | **PAR-2**、解出題數、牆鐘、逐題 PAR-2 勝負 |
| `cactus_vs_stock.png` | Cactus plot（累積解出 vs 時間） |

```bash
# full_scalar（217 題）
./scripts/vguided-cegar/post_batch_analysis.sh \
  --vguide-out output/vguide/experiments/full_scalar_vguide \
  --stock-out  output/vguide/experiments/full_scalar_stock \
  --set full_scalar \
  --timelimit 300

# sample（8 題，目錄結構相同）
./scripts/vguided-cegar/post_batch_analysis.sh \
  --vguide-out output/vguide/experiments/sample_vguide \
  --stock-out  output/vguide/experiments/sample_stock \
  --set sample \
  --timelimit 300
```

**PAR-2**（SV-COMP 常用）：解出題 = 牆鐘；未解出 = `2 × timelimit`；**平均愈低愈好**。

`run_stock_baseline_nohup.sh` / `run_full_experiments_nohup.sh` 結尾已自動呼叫 `post_batch_analysis.sh`。

Legacy：`compare_official_reference.py --baseline fmpa2` 僅歷史對照，不作主報告。

對照解讀：stock = 同 config、無 LLM；主數字以 `post_batch_analysis.sh` 輸出為準。歷史報告見 [`archive/.../2026-06-04_vguide-report_deepseek-chat_HISTORICAL.md`](../../archive/vguided-docs/reports/2026-06-04_vguide-report_deepseek-chat_HISTORICAL.md)；現行見 [`reports/README.md`](reports/README.md)。

---

## 7. 相關文件

- [STANDARD_BENCHMARK_SUITE.md](evaluation/STANDARD_BENCHMARK_SUITE.md)
- [LOCAL_DEVELOPMENT_ENV.md](LOCAL_DEVELOPMENT_ENV.md)
- [LLM_CALL_SCHEDULING.md](llm/LLM_CALL_SCHEDULING.md)
