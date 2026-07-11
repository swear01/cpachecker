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
| `output/vguide/experiments/` | **active raw**：batch 產物（`logs/<task>.log`、summary CSV）；git-ignored |
| `archive/raw-legacy/` | **retired raw 保存區**：舊 run 不刪、`mv` 到這裡保存；git-ignored |

> **Raw 約定**：raw 一律留在 git-ignored 處，永不進 git。退役舊 run 用
> `mv output/vguide/experiments/<old_run> archive/raw-legacy/`（**移，不要刪**——
> 反正已 ignored，移走可保存、之後要查還在）。詳見 `docs/notes.md` 的
> raw-output-lifecycle gotcha。

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

./scripts/vguided-cegar/run.sh nla-oracle validate
./scripts/vguided-cegar/run.sh nla-oracle run --arm both --timelimit 60
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

## 2.1 VGuide-NLA oracle-capacity harness

12-task frozen catalog 先走 stock k-induction，再把 reference polynomial candidates 經
`bmc.kinduction.predicatePrecisionFile` 餵回同一 engine：

```bash
# catalog + source/YAML SHA-256
./scripts/vguided-cegar/run.sh nla-oracle validate

# exact bit-vector/MathSAT；stock + oracle sequentially
./scripts/vguided-cegar/run.sh nla-oracle run \
  --output output/vguide/experiments/nla_oracle_capacity_smoke_current \
  --arm both --timelimit 60

# candidate dependency probes
./scripts/vguided-cegar/run.sh nla-oracle run \
  --arm oracle --timelimit 60 --candidate-shape supporting-first --task sqrt1-ll
./scripts/vguided-cegar/run.sh nla-oracle run \
  --arm oracle --timelimit 60 --candidate-shape conjunction --task sqrt1-ll

# exact integer-with-wraparound/range-constraints encoding
./scripts/vguided-cegar/run.sh nla-oracle run \
  --arm both --timelimit 60 --encoding nia
```

`--encoding nia` 使用 repository nonlinear-integer options + Z3。若 solver/config/parse 失敗，
harness 回傳 exit code 2，不得把它算成 UNKNOWN。2026-07-11 已從 official `z3-4.15.4`
commit `745087e` 在 host GLIBC 2.35 重建 Java runtime，安裝於
`~/.local/opt/z3-4.15.4`，`~/.local/bin/z3` 指向該版本。修復後 frozen NIA gate仍為
stock 0/12、oracle 0/12 @60s，因此 ordinary k-induction polynomial path STOP；見
[`reports/2026-07-11_nla_oracle_capacity_smoke.md`](reports/2026-07-11_nla_oracle_capacity_smoke.md)。
注意 `ant build-project` / `ant tests` 的 Ivy refresh會覆寫 ignored
`lib/java/runtime/libz3*.so` symlinks；refresh後需恢復 user-local links，並先從CPA log確認
`Using predicate analysis with Z3 4.15.4.0.`。

Ordinary k-induction的0/12不等同於 mutually-inductive conjunction或 direct PDR。Final consumer
matrix沿用同一 frozen catalog與 exact-BV/MathSAT semantics：

```bash
# K2：每個loop head只產生一個 mutually-inductive conjunction candidate
./scripts/vguided-cegar/run.sh nla-oracle run \
  --output output/vguide/experiments/nla_oracle_matrix_k2_bv_60s \
  --arm oracle --timelimit 60 --consumer kinduction --oracle-mode conjunction

# KP0/KP2：property-directed KI-PDR，stock與conjunctive oracle
./scripts/vguided-cegar/run.sh nla-oracle run \
  --output output/vguide/experiments/nla_oracle_matrix_kp2_bv_60s \
  --arm both --timelimit 60 --consumer kipdr --oracle-mode conjunction --jobs 4

# Direct PDR；pdr-abstraction明確開啟ALLSAT abstraction與abstraction-based lifting
./scripts/vguided-cegar/run.sh nla-oracle run \
  --output output/vguide/experiments/nla_oracle_matrix_p4_bv_60s \
  --arm both --timelimit 60 --consumer pdr-abstraction --oracle-mode both --jobs 4
```

`--oracle-mode root|conjunctive_root|abstraction|both`只適用 direct PDR；vocabulary mode只把
reference formulas加入 location-scoped predicate abstraction precision，不把它們當成真。
`--jobs N`只平行不同tasks；每個 CPAchecker process仍受自己的1-process timelimit約束。

Final matrix all oracle delta 0後，現行fallback是deterministic predicate usefulness gate。Targeted
confirmation與win controls：

```bash
./scripts/vguided-cegar/run.sh cpa \
  --set predicate_usefulness_loss7 --mode usefulness-gate-on --parallel 4 --timelimit 300 \
  --out output/vguide/experiments/predicate_usefulness_loss7_gate_current

./scripts/vguided-cegar/run.sh cpa \
  --set predicate_usefulness_win2 --mode usefulness-gate-on --parallel 2 --timelimit 300 \
  --out output/vguide/experiments/predicate_usefulness_win2_gate_current
```

Expected current result：loss7為7/7 TRUE且每個log都有`VGuide usefulness-rejected`、沒有
`VGuide precision-injected`；win2為2/2 TRUE且兩個logs都有precision injection。

### 2.2 Paired-response causal run

Frozen provenance（commits、recursive expanded-config hashes、manifest hash、model/solver/resources）在
`evaluation/predicate_usefulness_gate_frozen_20260711.json`。Primary run固定parallel4、heap15000M：

先由gate-off arm做live call並record。Cache key包含完整request body SHA-256與同task內ordinal；
batch runner自動把task名設成namespace：

```bash
export PAIR_CACHE="$PWD/output/vguide/llm-cache/usefulness_full764_frozen_20260711"

VGUIDE_LLM_RECORD_DIR="$PAIR_CACHE" \
VGUIDE_ANALYSIS_DUMP_DIR="$PWD/output/vguide/analysis_dumps/usefulness_full764_gate_off" \
VGUIDE_ANALYSIS_BENCHMARK_SET=loops_reachsafety_unreach \
VGUIDE_ANALYSIS_TIMELIMIT_SEC=300 \
./scripts/vguided-cegar/run.sh cpa \
  --set loops_reachsafety_unreach --mode usefulness-gate-off \
  --parallel 4 --timelimit 300 --heap 15000M \
  --out output/vguide/experiments/usefulness_full764_gate_off_record
```

Gate-on arm不需要API key，重播相同response prefix：

```bash
env -u DEEPSEEK_API_KEY \
VGUIDE_LLM_REPLAY_DIR="$PAIR_CACHE" \
VGUIDE_LLM_REPLAY_PRESERVE_LATENCY=true \
VGUIDE_ANALYSIS_DUMP_DIR="$PWD/output/vguide/analysis_dumps/usefulness_full764_gate_on" \
VGUIDE_ANALYSIS_BENCHMARK_SET=loops_reachsafety_unreach \
VGUIDE_ANALYSIS_TIMELIMIT_SEC=300 \
./scripts/vguided-cegar/run.sh cpa \
  --set loops_reachsafety_unreach --mode usefulness-gate-on \
  --parallel 4 --timelimit 300 --heap 15000M \
  --out output/vguide/experiments/usefulness_full764_gate_on_replay
```

`VGUIDE_LLM_RECORD_DIR`與`VGUIDE_LLM_REPLAY_DIR`互斥。Replay schema/hash/ordinal miss會讓該CPA
process失敗，不會改呼叫live API或悄悄跑stock。預設保留recorded latency；所有paired報告必須確認：

1. gate-on每題的`(request_hash,response_hash)`序列等於gate-off序列的prefix；
2. `response_source`分別為`live_recorded`與`replay`；
3. logs沒有`LLM response replay failed`；
4. 不能把response-cache replay稱為真正held-out或fresh-model evidence。

前三項的hash/source檢查以腳本執行：

```bash
python3 scripts/vguided-cegar/verify_llm_response_pair.py \
  --record-dump output/vguide/analysis_dumps/usefulness_full764_gate_off \
  --replay-dump output/vguide/analysis_dumps/usefulness_full764_gate_on
```

2026-07-11 loss7 TDD smoke已符合以上四項：gate-off **0/7**、gate-on **7/7 TRUE**、0 wrong；
18個recorded API entries、14個replayed calls，7題的gate-on序列全部是gate-off的exact hash
prefix。這仍是已曝光的
development set，只驗證cache與causal wiring。

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
| `--ablation` | （無 = noL3） | 歷史消融：`l3` / `no-l3`（主線不用 L3） |
| `--` 之後 | | 傳給 `cpa.sh` 的額外 `--option` |

排程與 LLM 預設見 `config/vguide.properties`。**Portfolio**（`--mode svcomp26-vguide` / `svcomp27-vguide`）：`vguide.*` 由頂層 config include；排程消融用 `--` 後的 `--option`（nested predicate 元件不再 include `vguide.properties`）。若 log 出現 `Mismatch … 'vguide.` 表示覆寫失效。**L3 不用**：驗證只跑 L1/L2；主線 svcomp26 / full_scalar 皆 noL3。**v1.4 計劃**：`dualPromptMode=true`，`llmSamplesPerCall=1` = **SAFE×1 + BUG×1** / 輪。見 [LLM_ENSEMBLE.md](llm/LLM_ENSEMBLE.md)、[PREDICATE_BUDGET.md](llm/PREDICATE_BUDGET.md)；已完成的 v1.4 計劃文件不再是現行入口。覆寫例：

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

# ── 消融實驗：source-prior mode（順序跑，一個一個） ──────────────────────────
# LLM 在分析開始前（CEGAR 第 0 輪前）以純 source code 猜 predicates，
# 注入 initial precision，無 CE context。對比 first_spurious（有 CE context）。
# 規則：不能同時跑多個 JVM 群——base+vguide 上限 8、svcomp26+vguide 上限 2。
#
# 全部 4 組順序跑（copy-paste 整塊）：
bash -ic '
  cd ~/cpachecker
  ./scripts/vguided-cegar/run.sh cpa --set loops_reachsafety_unreach  --mode source-prior-loops            --parallel 8 --timelimit 300 &&
  ./scripts/vguided-cegar/run.sh cpa --set no_overflow_scalar          --mode source-prior-overflow          --parallel 8 --timelimit 300 &&
  ./scripts/vguided-cegar/run.sh cpa --set loops_reachsafety_unreach  --mode source-prior-svcomp26-loops    --parallel 2 --timelimit 300 &&
  ./scripts/vguided-cegar/run.sh cpa --set no_overflow_scalar          --mode source-prior-svcomp26-overflow --parallel 2 --timelimit 300
'
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

對照解讀：stock = 同 config、無 LLM；主數字以 `post_batch_analysis.sh` 輸出為準。歷史報告見本機 `archive/vguided-docs/reports/`；現行見 [`reports/README.md`](reports/README.md)。

---

## 7. 相關文件

- [STANDARD_BENCHMARK_SUITE.md](evaluation/STANDARD_BENCHMARK_SUITE.md)
- [LOCAL_DEVELOPMENT_ENV.md](LOCAL_DEVELOPMENT_ENV.md)
- [LLM_CALL_SCHEDULING.md](llm/LLM_CALL_SCHEDULING.md)

## v1.5 Loops broad-set completed runs（2026-06-13）

Dataset：`loops_reachsafety_unreach`（764 entries from official SV-COMP `Loops.set` with `unreach-call.prp`）。v1.5 三組結果見 [reports/2026-06-13_v1.5_loops_reachsafety_unreach.md](reports/2026-06-13_v1.5_loops_reachsafety_unreach.md)；svcomp26-vguide v1.5.1 結果見 [reports/2026-06-14_svcomp26_vguide_loops.md](reports/2026-06-14_svcomp26_vguide_loops.md)。

| Mode | Output | Result |
|------|--------|--------|
| stock | `output/vguide/experiments/loops_reachsafety_unreach_stock_20260612/` | 165 TRUE / 60 FALSE / 539 UNKNOWN = 225 solved |
| `--svcomp26` | `output/vguide/experiments/loops_reachsafety_unreach_svcomp26_20260612/` | 334 TRUE / 152 FALSE / 278 UNKNOWN = 486 solved |
| v1.4 VGuide | `output/vguide/experiments/loops_reachsafety_unreach_v14_20260612/` | 202 TRUE / 60 FALSE / 502 UNKNOWN = 262 solved |
| **svcomp26-vguide** | `output/vguide/experiments/loops_reachsafety_unreach_svcomp26vguide_20260614/` | **341 TRUE / 152 FALSE / 271 UNKNOWN = 493 solved**；0 wrong；vs svcomp26 +7 |

Re-run commands:

```bash
./scripts/vguided-cegar/run.sh cpa --set loops_reachsafety_unreach --mode stock --parallel 8 --timelimit 300   --out output/vguide/experiments/loops_reachsafety_unreach_stock_YYYYMMDD

./scripts/vguided-cegar/run.sh cpa --set loops_reachsafety_unreach --mode svcomp26 --parallel 1 --timelimit 300   --out output/vguide/experiments/loops_reachsafety_unreach_svcomp26_YYYYMMDD

bash -ic './scripts/vguided-cegar/run.sh cpa --set loops_reachsafety_unreach --mode vguide --parallel 4 --timelimit 300   --out output/vguide/experiments/loops_reachsafety_unreach_v14_YYYYMMDD'

VGUIDE_TIMEOUT_GRACE=180 \
VGUIDE_ANALYSIS_DUMP_DIR=output/vguide/analysis_dumps/loops_reachsafety_unreach_svcomp26vguide_YYYYMMDD \
VGUIDE_ANALYSIS_BENCHMARK_SET=loops_reachsafety_unreach \
VGUIDE_ANALYSIS_TIMELIMIT_SEC=300 \
./scripts/vguided-cegar/run.sh cpa --set loops_reachsafety_unreach --mode svcomp26-vguide --parallel 6 --timelimit 300 --heap 4000M \
  --out output/vguide/experiments/loops_reachsafety_unreach_svcomp26vguide_YYYYMMDD
```
