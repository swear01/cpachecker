# VGuide Predicate 分析報告（noL3 全量 dump）

**日期**: 2026-06-08  
**Model**: `deepseek-v4-pro`  
**Config**: `full_scalar` / noL3（`vguide.enableL3Entailment=false`）  
**Timelimit**: 300s（runner 330s）  
**Dump run**: `output/vguide/analysis_dumps/full_scalar_noL3_20260608`  
**CPA logs**: `output/vguide/experiments/full_scalar_vguide_noL3_analysis/`  
**離線 CSV**: `output/vguide/analysis_dumps/full_scalar_noL3_20260608/analysis/`  
**計劃**: [PREDICATE_ANALYSIS_PLAN.md](../analysis/PREDICATE_ANALYSIS_PLAN.md)

---

## 1. 執行摘要

本輪在 **217 題**上完成 instrumentation + 重跑，蒐集 API `usage`、全量 `interpolants_pre` / `block_formulas`、每 spurious refinement 的 dump，並跑 **Phase D 離線分析**（**Z3 overlap / PCS**）。

| 軸 | 主要結論 |
|----|----------|
| **A. Context budget** | API `usage` 為 ground truth；median **677** prompt tokens/call（max 2365），遠小於 1M context；**非瓶頸** |
| **B. Overlap（Z3）** | **55% Novel** / **45% Redundant**（992/807）；R_I 474 / R_T 703 / R_P 60 yes |
| **C. 驗證效果** | vs stock：**33** 題 UNKNOWN→解出；**2** 題解出→UNKNOWN；rescued 題 **100%** 有 LLM |
| **排程** | 3639 spurious refinements 中僅 **199** 次呼叫 LLM（**5.5%**）；**180** 題只有 1 輪 LLM（`everyN=72`）；該批 **`llmSamplesPerCall=1`**、prompt 建議 **4–8** 條 |

**與 2026-06-07 headline noL3 batch 的 verdict 漂移**（同 config，不同 git / 計時）：約 **15** 題 verdict 變化（9 UNKNOWN→TRUE，5 TRUE→UNKNOWN 等），分析以 **本輪 dump** 為準。

---

## 2. 實驗與資料完整性

### 2.1 跑批結果

| 指標 | 值 |
|------|-----|
| 題數 | 217 / 217 完成 |
| TRUE / FALSE / UNKNOWN | **112 / 39 / 66**（7 題 hang 補跑後；`benchmark40_polynomial` 現為 **FALSE**） |
| 有 LLM API 的題 | 190（200 次 HTTP call） |
| 無 LLM（0 refinement 或從未排程到） | 27 |

### 2.2 已知資料限制（不阻擋本報告結論）

| 問題 | 影響 | 處理 |
|------|------|------|
| **7 題 hang 補跑（2026-06-08）** | 原批缺 `task_summary`；已用 `hang_summary_rerun.list` 重跑並寫入同一 dump | 現 **7/7 有 `task_summary.json`**；validate V2 通過 |
| **V3 off-by-one（56 題）** | `task_summary.refinements` = CPA 總 refinement 次數；`refinements.jsonl` = **僅 spurious** 行數（少 1 為最後 feasible CE 或非 spurious 輪） | 分析用 **jsonl 行數** 作 spurious 計數 |
| **`validated_predicates.injected`（舊 dump）** | 2026-06-08 批次的 jsonl 中該欄位常為 `false`（dumper 已於事後修正） | 本輪離線分析以 `precision_injected` / `precision_local_after` 推斷；**不必為此重跑 217 題** |
| **V7 SMT 字串比對** | `validated_predicates.smt_dump` 用 CE 脈絡 SSA（`l@2`）；`precision_local_after` 用 precision 內建 canonical 名（`l`） | **非注入失敗**；validate 已改 canonical assert 比對 + `precision_injected` 為準 |

### 2.3 重現分析

```bash
python3 scripts/vguided-cegar/analyze_predicate_study.py \
  --skip-validate \
  --dump-dir output/vguide/analysis_dumps/full_scalar_noL3_20260608 \
  --logs-dir output/vguide/experiments/full_scalar_vguide_noL3_analysis/logs \
  --stock-logs output/vguide/experiments/full_scalar_stock/logs \
  --out output/vguide/analysis_dumps/full_scalar_noL3_20260608/analysis
```

---

## 3. 軸 A — Context budget（API `usage`）

### 3.1 Token 統計（200 次 API call）

| 指標 | 值 |
|------|-----|
| `prompt_tokens` | min 479，**median 677**，max 2365 |
| 總 `prompt_tokens` | 137,544 |
| 總 `completion_tokens` | 620,458（含 reasoning） |
| `reasoning_tokens`（合計） | 599,651 |
| `prompt_cache_hit_tokens`（合計） | 115,584 |
| Latency | median **54s**，max **321s** |

### 3.2 Prompt 組件（dump 內 `prompt_components` 字元數）

典型 first-spurious prompt 以 **C source + contract + loop heads + rules** 為主；later 輪另加 `trace_summary`（≤5 blocks）。與 §3.1 一致：**遠未觸及 context 上限**。

### 3.3 解讀

- **瓶頸在 API latency + completion（含 reasoning）**，不是 prompt 長度。
- 擴 prompt（例如加 precision history）在 token 上仍有余量；是否值得做取決於 overlap 結論，而非 context 恐懼。

---

## 4. 軸 B — Overlap（Z3 entailment）

### 4.1 怎麼驗證的（每條 predicate `q`）

對 `refinements.jsonl` 中每條 `validated_predicates`，用 **Z3**（`z3_overlap.py`）做三個蘊含檢查：

| 分量 | SMT 問題 | 資料來源 |
|------|----------|----------|
| **R_I** | `I ⊨ q`？（UNSAT `I ∧ ¬q`） | 同 `loop_head` 的 `interpolants_pre` |
| **R_T** | `B ⊨ q`？（UNSAT `B ∧ ¬q`） | `block_formula_smt`（該 head 的 CE block） |
| **R_P** | `P_loc ⊨ q`？ | `precision_local_before[loop_head]` **僅當** 與 `q` **同一 SSA 符號名** |

分類：`max(R_I, R_P, R_T) ≥ 0.9` → **Redundant**；`≤ 0.1` → **Novel**；否則 Orthogonal。  
實作：`analyze_predicate_study.py` → `pcs_per_predicate.csv`（`pcs_mode=z3`）。

### 4.2 全量結果（1799 predicates）

| Overlap | 數量 | % |
|---------|------|---|
| **Novel** | **992** | **55.1%** |
| **Redundant** | **807** | **44.9%** |

| 分量 yes 次數 | 數量 | 含義 |
|---------------|------|------|
| R_I | 474 | 插值已邏輯蘊含 q |
| R_T | 703 | CE block 已邏輯蘊含 q |
| R_P | 60 | precision 已蘊含 q（1739 條因 SSA 不一致跳過 R_P） |

### 4.3 如何解讀 45% Redundant

- 約一半在 Z3 語意下仍為 **Novel**（相對插值 / block / precision 有獨立資訊）。  
- Redundant 主要來自 **R_I（474）** 與 **R_T（273 條單獨驅動分類）**；R_P 因 SSA 限制僅貢獻 60 條。  
- 「與已有資訊重疊」在實務上 ≈ **插值或 block 已涵蓋**；precision 層面多數因 SSA 不一致未檢（1739 條 skip）。

### 4.4 重現

```bash
pip install z3-solver
python3 scripts/vguided-cegar/analyze_predicate_study.py --skip-validate \
  --dump-dir output/vguide/analysis_dumps/full_scalar_noL3_20260608 \
  --logs-dir output/vguide/experiments/full_scalar_vguide_noL3_analysis/logs \
  --stock-logs output/vguide/experiments/full_scalar_stock/logs
```

全量 1799 列本機約 **6s**（`--z3-timeout-ms 8000`）。

---

## 5. 軸 C — PCS（Z3 分數）

CSV 欄位：`R_I`, `R_T`, `R_P`, `N = 1 - max(R_I, R_P)`（0/1；`unknown`→0.5）。  
`in_final_precision` 仍為終局 precision 字串比對（輔助欄位，非 overlap 主判據）。

---

## 6. LLM 排程與驗證效果

### 6.1 排程（3639 spurious refinements）

| `llm_skip_reason` | 次數 |
|-------------------|------|
| `schedule` | 3433 |
| `no_interpolants` | 7 |
| 實際 `llm_called` | **199**（**5.5%**） |

`everyN=72` + `maxLlmRoundsPerAnalysis=5` → 多數題 **僅第 1 次 spurious** 呼叫 LLM（180 題 exactly 1 round）。

### 6.2 vs Stock（本輪 analysis run）

| | 數量 |
|--|------|
| Stock UNKNOWN → 本輪解出（T/F） | **33** |
| 本輪解出 → Stock UNKNOWN（degraded） | **2** |
| Verdict 相同 | 173 |
| Rescued 且曾有 LLM | **33 / 33** |

代表題（rescued）：`up`, `down`, `benchmark19_conjunctive`, `count_by_nondet`, `string_concat-noarr`, `odd`, `even`, …

### 6.3 LLM 但仍 UNKNOWN

**64** 題曾有 LLM API 但 verdict 仍 UNKNOWN：LLM 有介入但 300s 內未證完或 hang。

### 6.4 LLM 生成品質（本批 `llmSamplesPerCall=1`）

| 指標 | 數值 |
|------|------|
| API calls（`llm_rounds.jsonl`） | **200** |
| `response_parse_ok` | **200 / 200**（JSON 可解析） |
| `predicates_raw` / call | median **7**（prompt 建議 4–8，見 `ProposalPromptBuilder` RULES） |
| 同一次 response 內重複字串 | **0 / 200** calls |
| Spurious 輪有叫 LLM | **199** |
| 該輪 `validated_predicates` ≥ 1 | **197 / 199**（**99%**） |
| 通過驗證的 predicate 總列數 | **1798**（noL3 下多 head 注入，列數 > raw 字串數） |

**解讀**：格式與 L1/L2 合約在本批幾乎不是瓶頸；失敗主要來自 **排程稀疏**（僅 5.5% spurious 輪叫 LLM）與 **證明時間**，而非 JSON 解析。

---

## 7. 與 headline 報告（2026-06-07）的關係

| 項目 | 2026-06-07 noL3 batch | 本輪 analysis rerun |
|------|----------------------|---------------------|
| 解出 (T+F) | 145/217 | **151/217**（112+39；7 題 hang 補跑後） |
| PAR-2 | 235.65s | 未重算（可從 `full_scalar_summary.csv` 補） |
| 資料 | 僅 CPA log | **+ analysis dump + usage** |

Verdict 漂移約 15 題屬 **非確定性 / 計時 / hang** 邊界；predicate 機制分析 **以本 dump 為準**。

---

## 8. 產物索引

| 路徑 | 內容 |
|------|------|
| `analysis/context_budget.csv` | 每次 API call 的 `usage` + prompt 組件 |
| `analysis/context_budget_per_task.csv` | 每題 rollup + stock_verdict |
| `analysis/pcs_per_predicate.csv` | 每 predicate Z3 overlap/PCS |
| `analysis/overlap_summary.csv` | 每題 overlap 計數 |
| `analysis/analysis_report.md` | 自動摘要（本文件為詳細版） |
| `tasks/<task>/refinements.jsonl` | 每 spurious refinement |
| `tasks/<task>/llm_rounds.jsonl` | 每次 API call + 完整 `usage` |

---

## 9. 後續建議

1. ~~**Z3 overlap / PCS**~~ ✅ `analyze_predicate_study.py` + `z3_overlap.py`；Novel **992** / Redundant **807**。  
2. ~~Dumper / 7 hang 補跑~~ ✅ 已完成。  
3. **下一輪消融（§10）**：見 [PREDICATE_ANALYSIS_PLAN.md](../analysis/PREDICATE_ANALYSIS_PLAN.md) §10 — 含 **Pre-CEGAR LLM（0-refinement bootstrap）**、`everyN`、prompt 加 interpolant。
