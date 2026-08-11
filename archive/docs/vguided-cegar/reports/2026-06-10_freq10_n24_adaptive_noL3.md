# noL3 + adaptive budget + freq10/n24 — full_scalar 217 題分析

**Run ID:** `full_scalar_noL3_freq10_n24_adaptive_20260610`  
**Commit:** `fd69f395fa`（adaptive predicate budget + experiment config）  
**Config:** noL3，thinking disabled，`enableAdaptivePredicateBudget=true`，tiers (4–8)/(6–12)/(8–16)，`every_n=24`，`min_interval=15`，`maxLlmRounds=10`，`llmMaxCompletionTokens=2048`，timelimit 300s  

| 目錄 | 路徑 |
|------|------|
| 實驗 | `output/vguide/experiments/full_scalar_vguide_noL3_freq10_n24_adaptive_20260610/` |
| Analysis dump | `output/vguide/analysis_dumps/full_scalar_noL3_freq10_n24_adaptive_20260610/` |
| vs stock 報告 | `.../analysis_vs_stock.txt`，`cactus_vs_stock.png` |
| Phase D | `.../analysis/analysis_report.md` |

---

## 1. 解題與 PAR-2（217 tasks，timelimit 300s）

| Run | TRUE | FALSE | UNKNOWN | 解題 (T+F) | PAR-2 sum | PAR-2 avg |
|-----|------|-------|---------|------------|-----------|-----------|
| **stock** | 76 | 40 | 101 | 116 | 61,489 | 283.36 |
| **notthinking**（20260609） | 97 | 40 | 80 | 137 | 49,581 | 228.48 |
| **old_analysis**（v1.0.0 dump） | 112 | 39 | 66 | 151 | 48,793 | 224.85 |
| budget306（thinking on，文檔） | 107 | 39 | 71 | 146 | 55,916 | 257.68 |
| **adaptive**（本 run） | **110** | **40** | **67** | **150** | **41,671** | **192.03** |

### vs stock（本 run）

| 指標 | 結果 |
|------|------|
| Δ 解題 | **+34**（116 → 150） |
| rescued（stock UNKNOWN → solved） | 35 |
| degraded | **1**（`benchmark10_conjunctive` TRUE → UNKNOWN） |
| Δ PAR-2 sum | **−19,819s** |
| PAR-2 單題 | adaptive 46 / stock 105 / tie 66 |
| 同 verdict 解題 wall | adaptive median **3.59×** stock（median 3.95s vs 0.98s） |

### vs notthinking（20260609）

| 指標 | 結果 |
|------|------|
| Δ 解題 | **+13**（137 → 150） |
| improved / degraded | **16 / 3** |
| Δ PAR-2 sum（notthinking − adaptive） | **+7,910s**（adaptive 更好） |
| PAR-2 單題 | adaptive 42 / notthinking 111 / tie 64 |

**notthinking 贏（adaptive UNKNOWN → notthinking solved）— 3 題：** `benchmark10_conjunctive`, `benchmark15_conjunctive`, `benchmark20_conjunctive`

**adaptive 贏（notthinking UNKNOWN → adaptive solved）— 16 題（節選）：** `bhmr2007`, `bin-suffix-5`, `functions_1-1`, `in-de42`, `linear-inequality-inv-a`, `loopv2`, `mono-crafted_1`, `nested3-1`, `nested9`, …

### vs old_analysis（thinking on，v1.0.0 instrumentation run）

| 指標 | 結果 |
|------|------|
| Δ 解題 | **−1**（151 → 150） |
| improved / degraded | 15 / **16** |
| Δ PAR-2 sum（old − adaptive） | **+7,122s**（adaptive PAR-2 明顯更好） |
| 同 verdict wall | adaptive median **0.11×** old（LLM 延遲主因） |

**old 贏、adaptive 逾時 UNKNOWN（16 題，節選）：** `down`, `ddlm2013`, `gr2006`, `gauss_sum`, `string_concat-noarr`, `mono-crafted_13`, `MADWiFi-encode_ie_ok`, …

**adaptive 贏（old UNKNOWN → adaptive solved）：** `benchmark53_polynomial`(F), `cggmp2005_variant`, `count_by_2`, `in-de41/42`, `loopv3`, `nested_delay_nd`, …

**重點：** `odd` 本 run **TRUE**（refs=1，3.7s）；notthinking / adaptive 多數 loop 題仍 UNKNOWN。

**結論：** adaptive + 更高 LLM 頻率 **在 non-thinking 主線上追回 ~13 題解題**，PAR-2 **優於所有對照 run**；相對 old_analysis 僅少 1 題解題，但總時間與 PAR-2 大幅改善。

---

## 2. LLM 延遲與 token（llm_rounds.jsonl）

| Run | API calls | latency median | preds/call median | reasoning_tokens |
|-----|-----------|----------------|-------------------|------------------|
| old_analysis（thinking on） | 226 | **47.9s** | 8 | median 2576（全 call） |
| notthinking | 234 | **2.4s** | **4** | 0 |
| **adaptive**（本 run） | **307** | **3.0s** | **6** | **0** |

| 指標 | adaptive |
|------|----------|
| `response_parse_ok` | **304/307（99.0%）** |
| prompt_tokens / call median | 865 |
| completion_tokens / call | 低（無 reasoning） |
| budget_tier 分布 | **low 210**，**medium 97**，**high 0** |

**檔位內 preds/call median：** low **6.0**；medium **9.0**（符合 tier min 上調）。

**觀察：** 實跑中 **未觸發 high tier（8–16）**；複雜度分數 S 多落在 low/medium。`odd` 僅 1 次 LLM、tier=low（5 preds）；`down` / `string_concat-noarr` 為 medium、median 8–10 preds 但仍 UNKNOWN。

---

## 3. Predicate / Z3 overlap（Phase D）

| 指標 | old_analysis | notthinking | **adaptive** |
|------|--------------|-------------|--------------|
| Tasks with LLM predicates | ~189 | 190 | **191** |
| Validated predicates | ~1799 | 1340 | **3636** |
| Novel / Redundant（Z3） | 992 / 807 | 776 / 564 | **2714 / 921** |
| Novel%（predicate 級） | ~55% | ~58% | **~75%** |
| pct_novel median（per task） | 50% | 50% | **50%** |
| preds / task median | 8 | 5 | **6** |
| Stock UNKNOWN → solved（dump） | 33 | 18 | **31** |

Overlap **per-task median Novel% 仍 ~50%**（與 v1.0.0 / notthinking 一致）；總 Novel 數上升主要來自 **更多 API call + 更高 preds/call**，非單題 overlap 品質突變。

詳見：`output/vguide/analysis_dumps/full_scalar_noL3_freq10_n24_adaptive_20260610/analysis/`

---

## 4. 機制解讀

1. **數量槓桿有效：** preds/call 4→6、call 234→307，解題 +13 vs notthinking，接近 old_analysis（−1 題）且 PAR-2 更好。
2. **high tier 未用上：** 若需逼近 151+ 且拉長 `down`/`string_concat-noarr` 類，可調 S 門檻或對多 loop / parity assertion 加權。
3. **代價可控：** latency 仍 ~3s/call（無 thinking）；PAR-2 avg **192s** 為目前最佳。
4. **風險：** 3 題 conjunctive benchmark 相對 notthinking degraded；整體仍僅 1 題 vs stock degraded。

---

## 5. 建議後續

1. **主線候選：** `vguide-experiment-freq10-n24.properties` + thinking disabled — 對 stock +34、對 notthinking +13、PAR-2 最佳。
2. **微調：** 讓 high tier 在 `odd`/`down` 類實際觸發；或 CE context prompt（見 `CE_CONTEXT_PROMPT_PLAN.md`）。
3. **勿回退 thinking：** old_analysis 解題略高但 PAR-2 與 wall 代價大；adaptive non-thinking 更均衡。

---

## 重跑分析命令

```bash
./scripts/vguided-cegar/post_batch_analysis.sh \
  --vguide-out output/vguide/experiments/full_scalar_vguide_noL3_freq10_n24_adaptive_20260610 \
  --stock-out output/vguide/experiments/full_scalar_stock \
  --set full_scalar --timelimit 300

python3 scripts/vguided-cegar/analyze_predicate_study.py \
  --dump-dir output/vguide/analysis_dumps/full_scalar_noL3_freq10_n24_adaptive_20260610 \
  --logs-dir output/vguide/experiments/full_scalar_vguide_noL3_freq10_n24_adaptive_20260610/logs \
  --stock-logs output/vguide/experiments/full_scalar_stock/logs \
  --out output/vguide/analysis_dumps/full_scalar_noL3_freq10_n24_adaptive_20260610/analysis
```
