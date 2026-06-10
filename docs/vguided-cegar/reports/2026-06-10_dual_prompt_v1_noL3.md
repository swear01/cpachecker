# v1.4 dual prompt + ce_summary — full_scalar 217 題分析

**Run ID:** `full_scalar_dual_v1_20260610`  
**Commit:** `85706b4bf0`（dual SAFE/BUG、`CeSummaryBuilder`、永久 `json_object`）  
**Config:** `vguide-experiment-dual-prompt-v1.properties`（dual on，freq20/n12，adaptive budget，noL3，thinking disabled，timelimit 300s）

| 目錄 | 路徑 |
|------|------|
| 實驗 | `output/vguide/experiments/full_scalar_dual_v1_20260610/` |
| vs stock | `analysis_vs_stock.txt`，`cactus_vs_stock.png`，`vs_stock_baseline.txt` |
| vs freq10/n24 | `vs_freq10_n24_adaptive.txt` |

---

## 1. 解題與 PAR-2（217 tasks，timelimit 300s）

| Run | TRUE | FALSE | UNKNOWN | 解題 (T+F) | PAR-2 avg |
|-----|------|-------|---------|------------|-----------|
| **stock** | 76 | 40 | 101 | 116 | 283.36 |
| **freq10/n24 adaptive**（v1.3） | 110 | 40 | 67 | 150 | 192.03 |
| **dual v1.4**（本 run） | **117** | **38** | **62** | **155** | **183.05** |

### vs stock

| 指標 | 結果 |
|------|------|
| Δ 解題 | **+39**（116 → 155） |
| Verdict 桶 | improved **42** / same 172 / degraded **3** |
| Δ PAR-2 sum | **−21,767s** |
| PAR-2 單題 | dual 57 / stock 101 / tie 59 |

### vs freq10/n24 adaptive

| 指標 | 結果 |
|------|------|
| Δ 解題 | **+5**（150 → 155） |
| Verdict 桶 | improved 10 / same 202 / degraded 5 |
| Δ PAR-2 sum | **−1,948s** |

---

## 2. v1.4 主目標：FALSE — **未達成**

| 驗收項（DUAL_PROMPT_V1_PLAN §6） | 結果 |
|----------------------------------|------|
| FALSE **+≥2** vs 基線 | **失敗**：40 → **38**（−2） |
| 新解出 FALSE（baseline 非 FALSE → dual FALSE） | **0 題** |
| 丟失 FALSE | **2 題**：`benchmark40_polynomial`、`benchmark53_polynomial`（FALSE → UNKNOWN） |

**結論：** v1.4 在 **TRUE / 總解出 / PAR-2** 上明顯優於 stock 與 v1.3，但 **FALSE 導向目標失敗**——與 v1.3 adaptive 相同，進步幾乎全來自 UNKNOWN→TRUE，未擴展 bug-finding。

---

## 3. 為何 FALSE 沒增加（歸因）

1. **評測集合不對焦**  
   本 run 為 `full_scalar`（217 題）；stock 已解 **40 FALSE**。BUG_HUNT 再跑同一集合，天花板是「維持或替換」既有 FALSE，而非大量新增。計劃中的 `regression_false_unknown`（~25 題，stock UNKNOWN + expected FALSE）**未跑**。

2. **LLM 只在 spurious CE 上觸發**  
   排程仍是 `every_n_and_interval` on **spurious** 反例。Spurious 路徑定義上**到不了**真 assertion failure；`ce_summary` 摘要的是 spurious 上的 loop 關係，與「通向 FALSE 的路徑」語意不一致。BUG 軌 prompt 要求 failure 狀態謂詞，但上下文仍是 **safe-abstraction 分裂** 的證據。

3. **SAFE ∪ BUG 合併仍偏向「證安全」**  
   Merge 順序 SAFE 先、BUG 後；兩軌共用同一 validation / inject。Invariant、bound 類謂詞更容易通過 L1 並推進 TRUE；BUG 軌提議的 negation / violation 狀態謂詞常與 spurious CE **不一致** 或被視為冗餘。

4. **ce_summary 不標示 violation 路徑**  
   語意壓縮（loop-head rel + interpolant）省略了「哪條路徑能觸發 assert」；僅有變量關係，BUG 軌缺少可操作的 failure witness。

5. **未做 FALSE 專用排程**  
   未對 feasible CE、長時間 UNKNOWN、或 yml `expected_verdict: false` 題加權呼叫 LLM（留 v2）。

6. **本 run 無 analysis dump**  
   未設 `VGUIDE_ANALYSIS_DUMP_DIR`，無法統計 `source_profile=BUG_HUNT` 注入占比；log 層亦未印 per-profile API 行。

---

## 4. 後續（v1.5 方向，草案）

| 方向 | 說明 |
|------|------|
| `regression_false_unknown` smoke | 先驗收 FALSE +≥2 的子集 |
| feasible / counterexample 導向 LLM | 非僅 spurious |
| BUG-only merge 或分軌 inject 配額 | 避免 SAFE 吃滿 precision |
| CE 摘要標 violation-relevant rel | 或 model 值一行 |
| 必跑 dump | `source_profile`、overlap 分軌統計 |

---

## 5. 重跑分析

```bash
./scripts/vguided-cegar/post_batch_analysis.sh \
  --vguide-out output/vguide/experiments/full_scalar_dual_v1_20260610 \
  --stock-out  output/vguide/experiments/full_scalar_stock \
  --set full_scalar --timelimit 300
```
