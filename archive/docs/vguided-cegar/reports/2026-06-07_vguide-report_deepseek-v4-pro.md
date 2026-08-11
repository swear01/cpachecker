# VGuide 進度報告（2026-06-07）

**日期**: 2026-06-07（L3-on 8 題重跑後更新）  
**專案**: CPAchecker Unified VGuide（LLM 引導 Predicate CEGAR）  
**Model**: `deepseek-v4-pro`  
**Benchmark**: `full_scalar`（217 題，ReachSafety scalar 子集）  
**Timelimit**: 300s（CPA `--timelimit`；runner 外層 `timeout 330s`）  
**Baseline**: `full_scalar_stock`（同 config，`useVocabularyGuide=false`）

---

## 1. 執行摘要

| 設定 | 解出 (T+F) | PAR-2 平均 | vs stock (verdict) |
|------|------------|------------|---------------------|
| **Stock** | 116/217 | **283.36s** | — |
| **VGuide L3-on** (`full_scalar_vguide`) | 131/217 | **272.79s** | **17↑ / 198= / 2↓** |
| **VGuide noL3** (`full_scalar_vguide_noL3`) | 145/217 | **235.65s** | **30↑ / 186= / 1↓** |

**主要發現**

1. **LLM 引導 predicate 有效**：L3-on 多解 **15 題**（131−116），noL3 多解 **29 題**；PAR-2 皆優於 stock。
2. **improved 幾乎全是 UNKNOWN→TRUE**（17/17 for L3-on vs stock）：VGuide 設計偏向補 **安全證明**，不是找新 bug。
3. **L3 entailment 雙面性**：關 L3 整體更好（145 vs 131 解出），但有 **6 題** 僅 L3-on 能證 TRUE（parity／invariant 類）；noL3 對 L3-on **21↑ / 7↓**。
4. **代價**：同 verdict 都解出時，VGuide 牆鐘中位數約 **stock 的 30–33×**（LLM + 較重 refinement）。

**歷史對照**（[`2026-06-04 deepseek-chat`](../../../archive/vguided-docs/reports/2026-06-04_vguide-report_deepseek-chat_HISTORICAL.md)）：chat 主實驗 **11↑/205=/1↓**，PAR-2 **259 vs 283**；v4-pro L3-on **17↑**，PAR-2 **272.79 vs 283**。

---

## 2. 實驗設定

| 項目 | 值 |
|------|-----|
| Config | `config/predicateAnalysis-vguide.properties` |
| VGuide | `vguide.enable=true`，`llmCallSchedule=every_n_and_interval`，`maxLlmRoundsPerAnalysis=5` |
| L3-on | `--ablation l3` 或 `--option vguide.enableL3Entailment=true` |
| **預設（noL3）** | `vguide.enableL3Entailment=false`（properties + Java 預設） |
| 輸出 | `output/vguide/experiments/full_scalar_vguide{,_noL3}/` |
| 分析 | `post_batch_analysis.sh`、`compare_official_reference.py` |

---

## 3. vs Stock 詳細結果

### 3.1 總表

| | TRUE | FALSE | INCOMPLETE | 解出 | PAR-2 avg |
|--|------|-------|------------|------|-----------|
| Stock | 76 | 40 | 101 | 116 | 283.36s |
| L3-on | 92 | 39 | 86 | 131 | 272.79s |
| noL3 | 106 | 39 | 72 | 145 | 235.65s |

Δ PAR-2 sum（stock − vguide）：L3-on **+2293s**；noL3 **+10353s**。

### 3.2 L3-on vs stock：17 improved（皆 UNKNOWN→TRUE）

`benchmark19_conjunctive`, `benchmark34_conjunctive`, `bin-suffix-5`, `count_by_nondet`, `ddlm2013`, `even`, `gr2006`, `jm2006_variant`, `mod4`, `mono-crafted_1`, `mono-crafted_11`, `mono-crafted_12`, `odd`, `overflow_1-1`, `simple_1-2`, `string_concat-noarr`, `sumt3`

### 3.3 L3-on vs stock：2 degraded

| 題目 | Stock | L3-on | 備註 |
|------|-------|-------|------|
| `gj2007b` | TRUE | UNKNOWN | LLM 開銷 + refinement 方向 |
| `linear-inequality-inv-b` | FALSE | UNKNOWN | 同上 |

`benchmark53_polynomial`：初跑 batch 曾 SMT hang（log 缺 verdict）；**2026-06-07 重跑** 得 **FALSE**（45.8s），與 stock 一致，不再計入 degraded。

### 3.4 noL3 vs stock：30 improved

除 §3.2 中 **11 題兩者皆 rescue** 外，noL3 **額外** 多解 19 題，例如：`MADWiFi-encode_ie_ok`, `benchmark04/15/20/24_conjunctive`, `bhmr2007`, `cggmp2005_variant`, `count_up_down-1`, `down`, `hhk2008`, `in-de20`, `in-de32`, `loopv2`, `loopv3`, `mono-crafted_10`, `simple_3-2`, `sum01-2`, `sumt4`, `up` 等。

noL3 vs stock **1 degraded**：`benchmark40_polynomial`（FALSE→INCOMPLETE*）。

---

## 4. L3 消融：L3-on vs noL3

### 4.1 總表

| 對照 | improved | same | degraded |
|------|----------|------|----------|
| **noL3 vs L3-on** | **21** | 189 | **7** |
| noL3 vs stock | 30 | 186 | 1 |
| L3-on vs stock | 17 | 198 | 2 |

Transition（L3-on → noL3）重點：

- INCOMPLETE → TRUE：**20**（noL3 多證出）
- TRUE → INCOMPLETE：**6**（L3-on 獨贏）
- INCOMPLETE → FALSE：**1**（`benchmark40_polynomial`：L3-on FALSE，noL3 hang）

### 4.2 L3-on 獨贏（6 題）：關 L3 後變 UNKNOWN

僅 **L3-on** 相對 stock 證出 TRUE，**noL3** 仍 UNKNOWN：

| 題目 | L3-on refs | noL3 refs |
|------|------------|-----------|
| `bin-suffix-5` | 73 | 145 |
| `mod4` | 73 | 145 |
| `mono-crafted_1` | 8 | 9 |
| `mono-crafted_12` | 1 | 29 |
| `overflow_1-1` | 1 | 129 |
| `simple_1-2` | 145 | 86 |

**解讀**：這批多為 **parity / invariant** 題。L3 **ENTAILED → strengthenInterpolants** 把 loop 不變式直接灌進插值，少次 refinement 即可 TRUE；noL3 只靠 PRECISION_ONLY 注入，refinement 多、易 timeout。

### 4.3 noL3 獨贏（19 題）：L3-on 仍 UNKNOWN

代表 **LLM predicate + 精度注入** 本身有用，**不一定需要 L3 strengthen**。例：`bhmr2007`, `sumt4`, `down`, `loopv2`, `MADWiFi-encode_ie_ok` 等（完整清單見 `output/vguide/experiments/l3_ablation_comparison.csv`）。

### 4.4 兩者皆 rescue stock（11 題）

`benchmark19_conjunctive`, `benchmark34_conjunctive`, `count_by_nondet`, `ddlm2013`, `even`, `gr2006`, `jm2006_variant`, `mono-crafted_11`, `odd`, `string_concat-noarr`, `sumt3`

### 4.5 noL3 vs L3-on：7 degraded（L3-on 較好）

| 題目 | L3-on | noL3 |
|------|-------|------|
| `bin-suffix-5` | TRUE | UNKNOWN |
| `mod4` | TRUE | UNKNOWN |
| `mono-crafted_1` | TRUE | UNKNOWN |
| `mono-crafted_12` | TRUE | UNKNOWN |
| `overflow_1-1` | TRUE | UNKNOWN |
| `simple_1-2` | TRUE | UNKNOWN |
| `benchmark40_polynomial` | FALSE | INCOMPLETE* |

前 6 題與 §4.2 對稱。`benchmark40_polynomial`：L3-on 維持 FALSE，noL3 hang。

### 4.6 noL3 vs L3-on：21 improved（節錄）

| 題目 | L3-on | noL3 | 備註 |
|------|-------|------|------|
| `gj2007b` | UNKNOWN | **TRUE** | L3-on 反而變差 |
| `linear-inequality-inv-b` | UNKNOWN | **FALSE** | noL3 恢復 stock FALSE |
| `bhmr2007` | INCOMPLETE* | **TRUE** | |
| `sumt4` | INCOMPLETE* | **TRUE** | |
| … | | | 其餘多為 UNKNOWN→TRUE |

---

## 5. LLM 用量（L3-on 主實驗）

| LLM rounds/題 | 題數 |
|---------------|------|
| 0 | 27 |
| 1 | 172 |
| 2 | 16 |
| 3 | 2 |

- 全批 **210** 次 API call（`llmSamplesPerCall=1`）
- 單次 latency：median **53.4s**，max 289s
- 明細：`output/vguide/experiments/full_scalar_vguide/llm_calls_per_task.csv`

17 題 improved vs stock：平均 **1.5** 次 LLM/題。

---

## 6. 已知問題

### 6.1 SMT hang / exception（7 題 L3-on 仍 UNKNOWN）

`bhmr2007`, `sumt4`, `sumt5`, `sumt7`, `sumt8`, `sumt9`, `watermelon`

原因：300s 到期時卡在 MathSAT `allSat`/interpolation，JVM 強殺來不及印 verdict；runner **`finalize_log_verdict`** 事後補 synthetic `UNKNOWN`（語意不變）。多數 stock 亦會 hang。`watermelon` 另因 SMT 變數名 `false` 觸發 Java exception。

**2026-06-07 重跑**（manifest `incomplete_l3on_rerun.list`，8 題 L3-on）：`benchmark53_polynomial` 改為 **FALSE**（45.8s）；其餘 7 題仍 UNKNOWN。初跑 hang 可能受 LLM predicate 路徑影響，非穩定 regression。

### 6.2 速度

同 verdict 皆解出（114 題）：L3-on 較快 **11** 題，stock 較快 **103** 題。

---

## 7. 結論與建議

1. **主線有效**：v4-pro + VGuide 在 217 題 scalar 上 consistently 優於 stock（verdict + PAR-2）。
2. **L3 預設關閉**：noL3 整體優於 L3-on；**6 題** parity 仍依賴 ENTAILED/strengthen → 用 `--ablation l3` 跑子集或 per-task 開啟。
3. **noL3 為預設**（2026-06-07 起）：整批 PAR-2 更好；6 題 parity/invariant 需 `--ablation l3` 或 `--option vguide.enableL3Entailment=true`。
4. **Runner**：**aborted log 補 verdict**（不改 verdict 語意，strict 可比）；hang 緩解（interp timelimit / 外層 grace）僅能透過 env 選用，**預設關閉**以對齊本報告 217 題 batch。

---

## 8. Predicate 機制分析（2026-06-08 補充）

在 noL3 上完成 **instrumentation + 217 題重跑** 與離線分析（與本報告 headline batch 同 config；verdict 可能有 ~15 題漂移）。

| 主題 | 結論 |
|------|------|
| Context | API median **677** prompt tokens/call；非瓶頸 |
| Overlap（Z3） | **55% Novel** / **45% Redundant**（992/807）；見 2026-06-08 報告 |
| vs stock | **33** rescued（皆有 LLM）；排程僅 **5.5%** spurious 呼叫 LLM |

詳見 **[2026-06-08_predicate-analysis_noL3.md](2026-06-08_predicate-analysis_noL3.md)**、[OVERLAP_AND_PCS.md](../analysis/OVERLAP_AND_PCS.md)。

---

## 9. 產物索引

| 路徑 | 內容 |
|------|------|
| `output/vguide/experiments/full_scalar_vguide/analysis_vs_stock.txt` | L3-on vs stock PAR-2 |
| `output/vguide/experiments/full_scalar_vguide_noL3/analysis_vs_stock.txt` | noL3 vs stock |
| `output/vguide/experiments/full_scalar_vguide_noL3/vs_l3_on_baseline.txt` | noL3 vs L3-on verdict |
| `output/vguide/experiments/l3_ablation_comparison.csv` | 三向逐題 CSV |
| `output/vguide/experiments/full_scalar_vguide/cactus_vs_stock.png` | L3-on cactus |
| `output/vguide/experiments/full_scalar_vguide_noL3/cactus_vs_stock.png` | noL3 cactus |
| `output/vguide/experiments/runner_logs/full_scalar_vguide_rerun.log` | L3-on batch log |
| `output/vguide/experiments/runner_logs/incomplete_l3on_rerun.log` | 8 題 L3-on 重跑 log |
| `output/vguide/experiments/runner_logs/full_scalar_vguide_noL3.log` | noL3 batch log |
| `docs/vguided-cegar/benchmark_sets/incomplete_l3on_rerun.list` | 重跑 manifest（8 題） |
