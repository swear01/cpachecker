# Overlap 與 PCS 方法說明

本文件說明 [PREDICATE_ANALYSIS_PLAN.md](PREDICATE_ANALYSIS_PLAN.md) 中 **軸 B（Overlap）** 與 **軸 C（PCS）** 的語意與 **Z3 實作**。實證數字見 [2026-06-08_predicate-analysis_noL3.md](../reports/2026-06-08_predicate-analysis_noL3.md)。

---

## 1. 要回答的問題

對每一條 LLM 提出的 abstraction predicate `q`（在某一 spurious refinement、某一 loop head）：

1. **Overlap**：`q` 與 CEGAR **已經有的資訊** 重疊嗎？（插值、precision、CE block）
2. **PCS（Predicate Contribution Score）**：`q` 對 **切掉這條 spurious 路徑** 有多必要？對 **最終 precision** 是否留下來？

Overlap 是 **分類**（Redundant / Novel / …）；PCS 分量為 **0–1** 連續分數。

---

## 2. 三種 Overlap 對照

```text
                    ┌─────────────────┐
                    │  LLM predicate q │
                    └────────┬────────┘
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
    ┌─────────┐        ┌──────────┐       ┌─────────────┐
    │  O-I    │        │   O-P    │       │    O-T      │
    │ vs 插值 I│        │ vs prec. │       │ vs CE block │
    └─────────┘        └──────────┘       └─────────────┘
```

| 代號 | 語意 | Z3 檢查 |
|------|------|---------|
| **O-I / R_I** | 插值是否已蘊含 `q` | `I ⊨ q` ⇔ UNSAT(`I ∧ ¬q`) |
| **O-P / R_P** | 該 loop head 的 precision 是否已蘊含 `q` | `P_loc ⊨ q`（**僅當** precision 與 `q` **同一 SSA 命名空間**） |
| **O-T / R_T** | CE block 是否已蘊含 `q` | `B ⊨ q` ⇔ UNSAT(`B ∧ ¬q`)，`B` = `block_formula_smt` |

**分類規則**（`z3_overlap.classify_overlap_z3`）：

- `max(R_I, R_P, R_T) ≥ 0.9` → **Redundant**
- `max ≤ 0.1` → **Novel**
- 否則 → **Orthogonal**

`N = 1 - max(R_I, R_P)`（PCS 分量，不含 T）。

---

## 3. 實作

| 項目 | 說明 |
|------|------|
| 模組 | `scripts/vguided-cegar/z3_overlap.py` |
| 整合 | `analyze_predicate_study.py` Phase D → `pcs_per_predicate.csv`（`pcs_mode=z3`） |
| 依賴 | `pip install z3-solver` |
| 邏輯 | `QF_AUFBV`；每 query 預設 timeout 8s |

### 3.1 R_P 與 SSA

`precision_local_before` 常用 canonical 名（`|main::i|`），`q` 的 `smt_dump` 常用 CE 脈絡 SSA（`|main::i@2|`）。**符號名不完全一致時跳過 R_P**（記 `R_P_status=skip`，`R_P=0`），避免把兩套變數誤併在一起。

### 3.2 R_T 與 Java L3 對齊

`R_T = B ⊨ q` 與 `PredicateValidationPipeline.classify()`（push block + push ¬pred → UNSAT ⇒ ENTAILED）一致。`block_formula_smt` 來自 `LoopHeadBlockFormulaIndex`（該 `loop_head` 在 spurious trace 上的 block）。

---

## 4. 實證（full_scalar_noL3_20260608，修正後 Z3）

| Overlap | 數量 | % |
|---------|------|---|
| **Redundant** | 807 | **44.9%** |
| **Novel** | 992 | **55.1%** |

| 分量 | yes | 說明 |
|------|-----|------|
| R_I（I⊨q） | 474 | 插值已蘊含 q |
| R_T（B⊨q） | 703 | block 已蘊含 q |
| R_P（P⊨q） | 60 | 僅 60 條 SSA 與 precision 一致可檢；1739 條 `R_P_status=skip` |

---

## 5. PCS 與驗證效果的關係

- Overlap/PCS 描述 **單條 predicate 的資訊含量**，不直接等於 PAR-2。
- 一條 **Redundant** 的 predicate 仍可能因 **注入時機**（first spurious）幫助分割狀態空間。
- noL3 下通過 L1/L2 的 predicate 皆注入 precision；**injected 數量多 ≠ 每條都有獨立貢獻**。

---

## 6. 重現

```bash
pip install z3-solver
python3 scripts/vguided-cegar/analyze_predicate_study.py \
  --skip-validate \
  --dump-dir output/vguide/analysis_dumps/full_scalar_noL3_20260608 \
  --logs-dir output/vguide/experiments/full_scalar_vguide_noL3_analysis/logs \
  --stock-logs output/vguide/experiments/full_scalar_stock/logs
```

輸出：`dump_dir/analysis/{pcs_per_predicate,overlap_summary,context_budget}.csv`

---

## 7. 已知限制

- R_P 在 SSA 不一致時不檢查 → Redundant 可能 **低估**（若僅 precision 層面重複）。
- Z3 與 CPAchecker Java 求解器可能有邊界差異（罕見）。
- `unknown` timeout 計為 0.5，可能產生 Orthogonal。
