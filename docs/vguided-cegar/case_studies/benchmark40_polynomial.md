# Case study：`benchmark40_polynomial`（vs stock 唯一變差）

**路徑**：`loop-zilu/benchmark40_polynomial.i`  
**對照**：`full_scalar_vguide_interval15` vs `full_scalar_stock_interval15`（2026-06-05）

## 摘要

| | Stock | VGuide |
|--|-------|--------|
| Verdict | **FALSE** @ **0.87s** | **UNKNOWN** @ **300s**（強制終止） |
| PAR-2 | **0.87 s** | **600 s** |
| Ref | 2 | ≥2（#1、#2 後卡死） |
| LLM | — | 1 次，inject **6** 謂詞 |

唯一 **verdict 變差** 題；單題 PAR-2 代價 ≈ **599 s**（約整批 Δ 的 11%）。

## 程式

維護 `x*y>=0` 的迴圈；`assert(x*y>=0)`。Stock **<1s** 可找反例。

## VGuide 失敗機制

1. 首輪 spurious → LLM：`x`/`y` 符號、乘積、邊界等 **bv** 謂詞（多 PRECISION_ONLY）。
2. strengthen + **6** 條 loop-head 注入 → 抽象變厚。
3. `refinement #2` 後卡在 **MathSAT allSat** → CPU 300s 強殺。

**非** soundness bug；屬 **precision 過厚 / 求解卡死**。

## 對照

- **tier40** 同題 VGuide 曾 **FALSE**（3 ref）→ 非必然失敗。
- 見報告 [§4.4.3](../2026-06-04-vguided-cegar-report.md#443-唯一變差題benchmark40_polynomialcase-study)。

## Log

- Stock：`output/vguide/experiments/full_scalar_stock_interval15/logs/benchmark40_polynomial.log`
- VGuide：`output/vguide/experiments/full_scalar_vguide_interval15/logs/benchmark40_polynomial.log`
