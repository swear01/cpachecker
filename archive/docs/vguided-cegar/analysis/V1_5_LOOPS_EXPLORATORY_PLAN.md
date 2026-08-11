# v1.5 計劃：SV-COMP Loops Exploratory Evaluation

- **狀態**：v1.5 broad-set 實測完成（2026-06-13）；clean/applicable tier metadata 仍列 TODO
- **版本標**：`vguide-v1.5.0`
- **前置**：v1.4 dual SAFE/BUG + `ce_summary`（tag `vguide-v1.4.0`）
- **主軸修正**：v1.5 **先不往 FALSE / bug-finding context 工程探索**；改為建立更大、更官方、更可分層解釋的 SV-COMP Loops evaluation。

**相關**：[DUAL_PROMPT_V1_PLAN.md](DUAL_PROMPT_V1_PLAN.md)、[CE_SUMMARY_COMPRESSION.md](CE_SUMMARY_COMPRESSION.md)、[../evaluation/STANDARD_BENCHMARK_SUITE.md](../evaluation/STANDARD_BENCHMARK_SUITE.md)

---

## 0. 目標一句話

v1.5 的目標是把 VGuide 從 `full_scalar` 217 題推進到 **官方 SV-COMP Loops 來源的 500+ / 700+ 題 exploratory evaluation**，新增 **strong baseline `CPAchecker --svcomp26`**，並用 static feature tiers 分析 VGuide 真正有效與失效的範圍。

---

## 0.1 實測結果（2026-06-13，tag `vguide-v1.5.0`）

Broad set `loops_reachsafety_unreach` 已完成三組 run：stock/simple baseline、strong baseline `--svcomp26`、v1.4 VGuide。完整報告見 [reports/2026-06-13_v1.5_loops_reachsafety_unreach.md](../reports/2026-06-13_v1.5_loops_reachsafety_unreach.md)。

| Run | TRUE | FALSE | UNKNOWN | Solved | PAR-2 avg | 結論 |
|-----|-----:|------:|--------:|-------:|----------:|------|
| stock | 165 | 60 | 539 | 225 | 426.21s | simple PredicateCPA baseline |
| `--svcomp26` | 334 | 152 | 278 | 486 | 222.45s | strong portfolio baseline |
| v1.4 VGuide | 202 | 60 | 502 | 262 | 399.72s | +37 solved vs stock |

Key observations:

- v1.4 VGuide vs stock：新增 42 個 stock-UNKNOWN → solved（全為 expected TRUE），但 lost 5 個 stock TRUE；net **+37 solved**。
- `--svcomp26` vs stock：net **+261 solved**，其中新增解包含 174 TRUE + 92 FALSE。
- 三組 run 均無 expected TRUE/FALSE mismatch。
- VGuide 在 broad set 的提升仍集中在 **TRUE / invariant discovery**；FALSE context 工程維持 out-of-scope / future work。
- 即使 `--svcomp26` overall 大幅領先，v1.4 VGuide 仍有 **33 個 VGuide-only TRUE solves**，可作為後續 tier/case-study 分析對象。

## 1. 為什麼 v1.5 暫停 FALSE 探索

v1.4 的 dual SAFE/BUG prompt 證明了兩件事：

| 觀察 | 結論 |
|------|------|
| v1.4 solved 155/217，PAR-2 183s，優於 stock 與 v1.3 | VGuide 對證 TRUE / invariant discovery 有效 |
| FALSE 40→38，0 new FALSE | 現行 spurious-only VGuide 不適合直接當 bug-finding 改良 |

因此 v1.5 先不把工程成本投入 doomed-region / feasible-CE / BUG_HUNT context。當前更重要的是回答：

> VGuide 在官方 SV-COMP Loops ReachSafety 題上，除了手工 `full_scalar` 217 題之外，能不能在更大的 500+ set 上穩定展示價值？

FALSE 導向仍重要，但移到 TODO；等 v1.5 建立 dataset 與 strong baseline 後，再決定是否進 v1.6。

---

## 2. v1.4 基線事實

`full_scalar` 217 題，timelimit 300s：

| Run | TRUE | FALSE | UNKNOWN | Solved | PAR-2 avg |
|-----|------|-------|---------|--------|-----------|
| stock | 76 | 40 | 101 | 116 | 283.36s |
| v1.3 adaptive | 110 | 40 | 67 | 150 | 192.03s |
| **v1.4 dual** | **117** | **38** | 62 | **155** | **183.05s** |

v1.5 評估要保留這個結論：

- VGuide 的主提升是 **UNKNOWN → TRUE**。
- VGuide 目前不是 portfolio replacement。
- 與 `--mode stock` 比是「同一 PredicateCPA 管線加 LLM」的增益。
- 與 `--svcomp26` 比是「與 CPAchecker strong portfolio 的距離與互補」。

---

## 3. Dataset 設計

### 3.1 官方來源

使用官方 SV-COMP `c/Loops.set`：

```text
loops/*.yml
loop-acceleration/*.yml
loop-crafted/*.yml
loop-invgen/*.yml
loop-lit/*.yml
loop-new/*.yml
loop-industry-pattern/*.yml
loops-crafted-1/*.yml
loop-invariants/*.yml
loop-invariants64/*.yml
loop-simple/*.yml
loop-zilu/*.yml
nla-digbench/*.yml
nla-digbench-scaling/*.yml
```

本機 `~/sv-benchmarks/c` 統計：

| Set | yml |
|-----|----:|
| official Loops.set expanded | **818** |

注意：一個 yml 可能含多個 property entry；v1.5 以 property entry 為準，而不是只看 yml 第一個 property。

### 3.2 主 set：`loops_reachsafety_unreach`

| 項目 | 值 |
|------|---:|
| 來源 | official `Loops.set` |
| filter | 含 `unreach-call.prp` property entry |
| entries | **764** |
| expected TRUE / FALSE | **532 / 232** |

這是 v1.5 **broad main set**。它大、官方、property 與 VGuide reachability 主線一致。

### 3.3 Clean set：`loops_reachsafety_clean`

從 `loops_reachsafety_unreach` 中排除明顯 out-of-scope / 高風險 tier：

- pointer / heap / struct
- float / concurrency
- array-content/select-store experimental
- severe parser-risk

保留：

| Tier | entries |
|------|--------:|
| `CORE_SCALAR` | 399 |
| `CORE_ARRAY_SCALAR` | 67 |
| `UNKNOWN_REACH` | 29 |
| `SIMPLE_REACH_OTHER` | 22 |
| **Total** | **517** |

這是 v1.5 的 **500+ clean VGuide-friendly set**。

### 3.4 Mechanism set：`loops_reachsafety_applicable`

只取 VGuide 現行最合理的核心能力：

| Tier | entries |
|------|--------:|
| `CORE_SCALAR` | 399 |
| `CORE_ARRAY_SCALAR` | 67 |
| **Total** | **466** |

不到 500，但用於 mechanism-level 解釋。

### 3.5 Exploratory side sets

| Set | 內容 | 用途 |
|-----|------|------|
| `loops_reachsafety_array_select_exp` | array assertion / select-store 類 | 判斷是否值得擴 array predicate support |
| `loops_reachsafety_parser_risk` | bitshift / pointer syntax risk | 檢查 classifier 是否太保守 |
| `loops_reachsafety_expected_false` | expected false subset | 僅統計，不作 v1.5 主優化 |
| `loops_reachsafety_true_rescue` | expected true + stock UNKNOWN | 找 VGuide 最強 rescue pattern |

---

## 4. Classifier 修正：從 run/skip 改成 tier/tag

現有 `scripts/vguided-cegar/classify_bootstrap_targets.py` 是 regex classifier，分類名像 `RUN_SCALAR` / `SKIP_*`，語意偏 gatekeeping。v1.5 改成 **stratifier**：所有題都可跑，但依 tier 報告。

### 4.1 現有 classifier 特徵

目前抽取：array、malloc/free、struct/union、float/double、bitshift、pthread/atomic、pointer syntax、assertion 是否提 array、loop 數、counter update、accumulator、assertion vars 與 loop/counter vars 重疊。

### 4.2 v1.5 tier

| v1.5 tier | 來源條件 | 主實驗 |
|-----------|----------|--------|
| `CORE_SCALAR` | 原 `RUN_SCALAR` | yes |
| `CORE_ARRAY_SCALAR` | 原 `RUN_ARRAY_SCALAR` | yes |
| `EXP_ARRAY_SELECT` | 原 `RUN_ARRAY_SELECT_EXPERIMENTAL` | exploratory |
| `EXP_BV_OR_PARSER_RISK` | 原 `PARSER_RISK` | exploratory / tag |
| `RISK_POINTER_HEAP` | 原 `SKIP_POINTER_HEAP` | tag only |
| `RISK_FLOAT_CONCURRENCY` | 原 `SKIP_UNSUPPORTED_THEORY` | tag only |
| `UNKNOWN_REACH` | 原 `UNKNOWN`，property 是 unreach-call | clean set included |
| `SIMPLE_REACH_OTHER` | 原 `SKIP_ARRAY_CONTENT`，但 property 是 unreach-call | clean set included |

重點：**不要再把非 scalar 直接丟掉；先標籤化，跑完再看結果。**

---

## 5. Manifest 與 runner 需求

### 5.1 新 manifest 格式

新增 CSV manifest，而不只 `.list` source path：

```csv
task_id,yml,input_file,property_file,expected_verdict,tier,tags
```

原因：

- 同一 yml 可能有多個 property。
- `unreach-call.prp` 的 expected verdict 可能不同於 `no-overflow.prp`。
- `--svcomp26` strong baseline 應 property-aware。
- 分析需要依 tier / expected verdict 分層。

### 5.2 產物

| 產物 | 路徑 |
|------|------|
| generator | `scripts/vguided-cegar/generate_svcomp_loop_sets.py` |
| broad CSV | `docs/vguided-cegar/benchmark_sets/loops_reachsafety_unreach.csv` |
| clean CSV | `docs/vguided-cegar/benchmark_sets/loops_reachsafety_clean.csv` |
| applicable CSV | `docs/vguided-cegar/benchmark_sets/loops_reachsafety_applicable.csv` |
| summary | `docs/vguided-cegar/benchmark_sets/loops_reachsafety_summary.md` |

---

## 6. Baselines

### 6.1 Stock PredicateCPA

目的：衡量 VGuide 對同一 PredicateCPA 管線的增益。

```bash
./scripts/vguided-cegar/run.sh cpa --set loops_reachsafety_clean --mode stock --timelimit 300 --parallel 8
```

### 6.2 VGuide

目的：主方法；先用 v1.4 最佳可重現設定。

```bash
./scripts/vguided-cegar/run.sh cpa --set loops_reachsafety_clean --mode vguide --timelimit 300 --parallel 8
```

建議 config 起點：

- dual prompt + `ce_summary`
- adaptive budget
- noL3 作主要結果；L3 作消融或不跑
- thinking disabled

### 6.3 Strong baseline：CPAchecker `--svcomp26`

新增 mode：

```bash
./scripts/vguided-cegar/run.sh cpa --set loops_reachsafety_clean --mode svcomp26 --timelimit 300 --parallel 8
```

要求：

- 優先使用 CPAchecker CLI `--svcomp26`。
- 若當前 checkout 只提供 unmaintained config，fallback 到 `config/unmaintained/svcomp26.properties`。
- 必須記錄實際使用的 command/config 到 run manifest。

---

## 7. 實驗順序

### Phase 0 — Dataset generation only

產生三個主 CSV + summary，驗收：

- no missing source
- no duplicate `task_id`
- 每列有 `property_file=unreach-call.prp`
- broad set 約 764，clean set 約 517，applicable 約 466
- expected TRUE/FALSE 分布寫入 summary

### Phase 1 — Smoke run

從 broad set 抽 30 題：

| tier | 數量 |
|------|----:|
| CORE_SCALAR | 8 |
| CORE_ARRAY_SCALAR | 6 |
| UNKNOWN_REACH | 4 |
| SIMPLE_REACH_OTHER | 4 |
| EXP_ARRAY_SELECT | 3 |
| EXP_BV_OR_PARSER_RISK | 3 |
| expected false 任意 tier | 2 |

跑 stock / VGuide / svcomp26。驗收：runner、log parser、summary、PAR-2、tier join 都正常。

### Phase 2 — Clean set full run

先跑 `loops_reachsafety_clean` 517 題三組 baseline。

輸出目錄：

```text
output/vguide/experiments/loops_reachsafety_clean_stock/
output/vguide/experiments/loops_reachsafety_clean_vguide/
output/vguide/experiments/loops_reachsafety_clean_svcomp26/
```

### Phase 3 — Broad set full run

跑 `loops_reachsafety_unreach` 764 題三組 baseline。

### Phase 4 — Exploratory side sets

依結果決定是否跑 array-select / parser-risk / expected-false / true-rescue side sets。

---

## 8. 分析指標

每個 set 報：

| 指標 | 說明 |
|------|------|
| TRUE / FALSE / UNKNOWN | verdict distribution |
| solved | TRUE + FALSE |
| PAR-2 avg / sum | timelimit 300s |
| improved / same / degraded vs stock | verdict bucket |
| VGuide-only solved | stock UNKNOWN，VGuide TRUE/FALSE |
| svcomp26-only solved | strong baseline 解但 VGuide 沒解 |
| overlap | VGuide 與 svcomp26 都解 |
| expected TRUE accuracy | 證安全能力 |
| expected FALSE accuracy | 只統計，不作 v1.5 主優化 |
| degradation by tier | 風險定位 |
| improvement by tier | VGuide 有效範圍 |

核心表：

```text
tier × verdict transition × baseline
```

範例：

| tier | stock solved | VGuide solved | Δ | VGuide-only TRUE | VGuide degraded | svcomp26 solved |
|------|-------------:|---------------:|--:|-----------------:|----------------:|----------------:|
| CORE_SCALAR | | | | | | |
| CORE_ARRAY_SCALAR | | | | | | |
| UNKNOWN_REACH | | | | | | |
| EXP_ARRAY_SELECT | | | | | | |

---

## 9. 成功標準

### 9.1 Broad set

在 `loops_reachsafety_unreach`：

- VGuide solved > stock solved。
- PAR-2 低於 stock。
- degraded 題數可解釋且集中在非 core tier。
- improvement 主要集中在 `CORE_SCALAR` / `CORE_ARRAY_SCALAR`。

### 9.2 Clean set

在 `loops_reachsafety_clean`：

- VGuide 相對 stock 有明顯 solved / PAR-2 改善。
- UNKNOWN→TRUE 是主要提升來源。
- `CORE_ARRAY_SCALAR` 至少有非零 VGuide-only solved。

### 9.3 vs `--svcomp26`

不要求 VGuide 贏 `--svcomp26` overall。成功標準是：

- 找出 VGuide-only solved 或 VGuide faster cases。
- 說明 VGuide 與 strong CPAchecker portfolio 的互補性。
- 找出 svcomp26-only solved 題的 tier，作為後續策略整合方向。

---

## 10. 報告敘事

建議論文 / advisor 報告說法：

> We evaluate VGuide on a broad 764-entry SV-COMP Loops ReachSafety benchmark derived from official `Loops.set` by selecting `unreach-call.prp` properties. Because VGuide targets predicate-guided loop invariant discovery rather than replacing CPAchecker’s full SV-COMP portfolio, we stratify results by static feature tiers. The clean 517-entry subset isolates tasks where VGuide is expected to be applicable, while the full set measures robustness and out-of-scope behavior.

---

## 11. 實作 checklist

### Dataset / classifier

- [ ] 新增 `generate_svcomp_loop_sets.py`
- [ ] 正確 parse yml 多 property entries
- [ ] 輸出 broad / clean / applicable CSV
- [ ] 把現有 classifier 包裝成 tier/tag stratifier
- [ ] 產生 `loops_reachsafety_summary.md`

### Runner

- [ ] `run_benchmark_set.sh` 支援 CSV manifest
- [ ] summary CSV 增加 `task_id,yml,property_file,expected_verdict,tier,tags`
- [x] `run.sh cpa --mode svcomp26`
- [ ] log/manifest 記錄實際 config 與 command

### Analysis

- [ ] `post_batch_analysis.sh` 支援 CSV metadata join
- [ ] 新增 tier transition table
- [ ] 新增 VGuide vs svcomp26 overlap table
- [ ] 新增 expected TRUE/FALSE accuracy table

### Runs

- [ ] Phase 1 smoke：30 題 × 3 modes
- [ ] Phase 2 clean：517 題 × 3 modes
- [x] Phase 3 broad：764 題 × 3 modes
- [ ] Phase 4 side sets（視結果）

### Docs

- [x] 更新 `RUN_EXPERIMENTS.md`
- [ ] 更新 `STANDARD_BENCHMARK_SUITE.md`
- [ ] 新增 experiment spec：`experiments/2026-06-xx_v1.5_loops_exploratory.md`
- [x] 新增 report：`reports/2026-06-13_v1.5_loops_reachsafety_unreach.md`
- [x] tag `vguide-v1.5.0`

---

## 12. Out of Scope：FALSE 導向移出 v1.5

v1.5 不實作 FALSE / bug-finding context 工程；只在 exploratory evaluation 中保留 expected-false 分層統計。

不納入 v1.5 的內容：

- doomed-region / error-invariant prompt
- suffix-WP elicitation
- plan-before-predicates BUG schema
- frontier digest / anti-divergence
- verdict-conditional BUG throttling
- sentinel-triggered BMC / value-analysis escalation

---

## 13. 產物索引

| 產物 | 路徑 |
|------|------|
| 本計劃 | `docs/vguided-cegar/analysis/V1_5_LOOPS_EXPLORATORY_PLAN.md` |
| Dataset summary | `docs/vguided-cegar/benchmark_sets/loops_reachsafety_summary.md` |
| Experiment spec | `docs/vguided-cegar/experiments/2026-06-xx_v1.5_loops_exploratory.md` |
| Report | `docs/vguided-cegar/reports/2026-06-xx_v1.5_loops_exploratory.md` |
| Generator | `scripts/vguided-cegar/generate_svcomp_loop_sets.py` |
| Strong baseline mode | `scripts/vguided-cegar/run.sh cpa --mode svcomp26` |
