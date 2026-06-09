# noL3 + thinking disabled — full_scalar 217 題分析

**Run ID:** `full_scalar_noL3_notthinking_20260609`  
**Commit:** `d7021692f9`（`VGUIDE_LLM_THINKING=disabled`）  
**Config:** noL3，predicate budget 3–6，K=1，`every_n=72`，timelimit 300s  

| 目錄 | 路徑 |
|------|------|
| 實驗 | `output/vguide/experiments/full_scalar_vguide_noL3_notthinking_20260609/` |
| Analysis dump | `output/vguide/analysis_dumps/full_scalar_noL3_notthinking_20260609/` |
| vs stock 報告 | `.../analysis_vs_stock.txt`，`cactus_vs_stock.png` |
| Phase D | `.../analysis/analysis_report.md` |

---

## 1. 解題與 PAR-2（217 tasks，timelimit 300s）

| Run | TRUE | FALSE | UNKNOWN | 解題 (T+F) | PAR-2 sum | PAR-2 avg |
|-----|------|-------|---------|------------|-----------|-----------|
| **stock** | 76 | 40 | 101 | 116 | 61,489 | 283.36 |
| **notthinking**（本 run） | **97** | **40** | 80 | **137** | **49,581** | **228.48** |
| budget306（thinking on） | 107 | 39 | 71 | 146 | 55,916 | 257.68 |
| old_analysis（v1.0.0 dump） | 112 | 39 | 66 | 151 | 48,793 | 224.85 |

### vs stock（本 run）

| 指標 | 結果 |
|------|------|
| Δ 解題 | **+21**（116 → 137） |
| rescued | 21（stock UNKNOWN → solved） |
| degraded | **0** |
| Δ PAR-2 sum | **−11,909s**（notthinking 較好） |
| PAR-2 單題 | notthinking 37 / stock 100 / tie 80 |
| 同 verdict 解題 wall | vguide median **2.67×** stock（median 3.27s vs 0.98s） |

### vs thinking-on runs

| 對照 | Δ 解題 | Δ PAR-2 sum (notthinking − other) | 解讀 |
|------|--------|-----------------------------------|------|
| vs budget306 | **−9** | **−6,336s**（notthinking PAR-2 更好） | 少 9 題但總 PAR-2 更低（unsolved 少、無 LLM 拖時間） |
| vs old_analysis | **−14** | **+788s**（略差） | 解題少 14 題，PAR-2 接近（228 vs 225 avg） |

**結論：** 關 thinking 後 **對 stock 仍明顯增益（+21、零 degraded）**，PAR-2 優於 budget306；相對 v1.0.0 thinking run **解題少 ~14 題**，但 **LLM 成本與延遲大幅下降**，PAR-2 幾乎持平。

---

## 2. LLM 延遲與 reasoning tokens

| Run | API calls | latency median | reasoning_tokens |
|-----|-----------|----------------|------------------|
| old_analysis（thinking 預設 on） | 200 | **52.8s** | median 2576，**全 200 call 有** |
| budget306（thinking on） | 200 | **87.9s** | median 5465，全 200 call 有 |
| **notthinking** | **234** | **2.4s** | **0**（全 call） |

- 更多 API call（234 vs 200）：分析較快結束、較少被單次 LLM 佔滿 timelimit，排程下可多觸發幾輪。
- `completion_tokens` 總量遠小於 thinking run；無 `reasoning_tokens` 計費。

---

## 3. Predicate / Z3 overlap（Phase D）

| 指標 | v1.0.0 analysis | notthinking |
|------|-----------------|-------------|
| Tasks with LLM predicates | ~200 | 190 |
| Validated predicates | ~1799 | **1340** |
| Novel / Redundant | 992 / 807 (**55% / 45%**) | 776 / 564 (**58% / 42%**) |
| Stock UNKNOWN → solved（dump 統計） | 33 | 18 |

Overlap 比例與 v1.0.0 相近；predicate 總量較少（更快 call、可能較少輪次或較短回應）。

詳見：`output/vguide/analysis_dumps/full_scalar_noL3_notthinking_20260609/analysis/`

---

## 4. Verdict 翻轉（相對 thinking runs）

### notthinking 贏（old TRUE → notthinking UNKNOWN）— 21 題

多為 thinking run 曾 TRUE、本 run 逾時 UNKNOWN：`down`, `odd`, `ddlm2013`, `gr2006`, `bhmr2007`, `gauss_sum`, `string_concat-noarr`, `vnew1`, `mono-crafted_*` 等。

### notthinking 贏（others UNKNOWN → notthinking solved）— 相對 old +7

`benchmark53_polynomial`(F), `cggmp2005_variant`, `count_by_2`, `in-de41`, `loopv3`, `nested_delay_nd`, …

### vs budget306

- 贏 8 題（含 `benchmark40_polynomial`, `even`, `mod4` 等 thinking run 逾時題）
- 輸 17 題（多為 thinking 曾 TRUE、本 run UNKNOWN）

**解讀：** 關 thinking 降低單題 **隨機性與 latency 方差**，但 **predicate 品質/數量** 可能不如長 reasoning 的單次提案；兩種 run 的 verdict 差異仍大（LLM 非決定性 + 模式不同）。

---

## 5. 建議後續

1. **主線配置：** `VGUIDE_LLM_THINKING=disabled` + predicate budget 3–6 — 成本/延遲合理，對 stock 穩定 +21。
2. **若要逼近 v1.0.0 151 解題：** 可試 ensemble K=2–3（non-thinking）、或略增 `maxPredicatesPerCall`；需再 benchmark。
3. **報告對照：** 本 run PAR-2 **優於** budget306；解題介於 stock+21 與 old_analysis−14 之間。

---

## 重跑分析命令

```bash
./scripts/vguided-cegar/post_batch_analysis.sh \
  --vguide-out output/vguide/experiments/full_scalar_vguide_noL3_notthinking_20260609 \
  --stock-out output/vguide/experiments/full_scalar_stock \
  --set full_scalar --timelimit 300

python3 scripts/vguided-cegar/analyze_predicate_study.py --skip-validate \
  --dump-dir output/vguide/analysis_dumps/full_scalar_noL3_notthinking_20260609 \
  --logs-dir output/vguide/experiments/full_scalar_vguide_noL3_notthinking_20260609/logs \
  --stock-logs output/vguide/experiments/full_scalar_stock/logs
```
