# 計劃：First-spurious Prompt 補齊 CE 上下文

**狀態**：計劃（未實作）  
**目標**：在 **non-thinking** 模式下，把 spurious CE 的可觀測資訊送進 **第一次** LLM prompt，減少只靠 source 猜 predicate。  
**不改**：排程、`llmSamplesPerCall`、Z3 overlap 管線。

---

## 1. 背景與動機

| 現況 | 問題 |
|------|------|
| `buildFirstSpurious` 只有 source + loop heads + rules + budget | `ContextPack` 已有 `blockFormulas`、`interpolants`、`traceSummary`，但 **first 輪未用** |
| `buildLaterSpurious` 有 `traceSummary`（5 blocks） | 多數題在 `every_n=72` 下 **等不到第二輪 LLM** |
| Analysis dump 有完整 CE | 例如 `down` prompt 顯示 `Allowed: [n]`，CE 卻含 `i,k,j` |

Thinking run 靠長內部推理補足；non-thinking 需 **外顯 CE**。

**Context 成本（217 題實測，notthinking batch）**

| 方案 | 額外大小（median） | 合計 prompt_tokens（估） |
|------|-------------------|---------------------------|
| 現況 | 0 | ~853 |
| 一行摘要（5 blocks + interpolants） | ~1858 chars ≈ **+464 tokens** | ~1310（**+54%**） |
| 整段 block JSON | ~1670 chars ≈ +400 tokens | ~1270（+49%） |

遠未觸及 context 上限；建議用 **摘要** 而非 raw JSON。

---

## 2. 實作範圍

### 2.1 `ProposalPromptBuilder`

在 `buildFirstSpurious` 的 `commonHeader` 之後、`buildOutputContract` 之前插入：

```text
SPURIOUS COUNTEREXAMPLE (read-only hints; use source variable names in output):
{ce_summary}
```

`ce_summary` 由新 helper 產生（可放在 `ContextPackBuilder` 或 `ProposalPromptBuilder`）：

1. **Block formulas**（最多 5 條）：`block i: {one-line SMT}` — 重用 `summarizeTrace` 邏輯  
2. **Interpolants**（最多 5 條）：`interp@node: {one-line assert}` — 從 `pack.interpolants()` dump 單 assert  
3. **可選**：`Encoded vars in CE: [...]` — canonical 名稱列表（修 `VarContract` 空時的误导）

**禁止**整段 `precision_local_before`（太長、易混淆 SSA）。

### 2.2 `VGuideAnalysisDumper` / `prompt_components`

- `prompt_components` 新增 `ce_summary` char count  
- 方便離線對照 token 與品質

### 2.3 長度護欄

- 單 block SMT 截斷（例如 400 chars）+ `...`  
- 總 `ce_summary` cap（例如 3000 chars）  
- 超過則少列 interpolant 或 block

---

## 3. 驗收

### 3.1 Regression 集（~21 題）

優先：`down`, `odd`, `string_concat-noarr`, `ddlm2013`, `gr2006`, `vnew1`

| 指標 | 期望 |
|------|------|
| 解題數 | ≥ 現 notthinking 137，目標逼近 thinking 151 |
| `odd` | 出現 parity / `bvurem` 相關式 |
| `string_concat-noarr` | 不再出離題 bound（如 `i>=100`） |
| `down` | refinements 不爆炸（<<50） |
| prompt_tokens median | < 2000（摘要後） |

### 3.2 全量

- 217 題 PAR-2 vs stock / notthinking baseline  
- overlap Novel% 不應明顯下降  
- `analyze_predicate_study.py --validate-only` 無新增 hard failure

### 3.3 命令

```bash
# regression 子集（待建 manifest regression_nothink.list）
./scripts/vguided-cegar/run.sh cpa --set regression_nothink --ablation no-l3 \
  --out output/vguide/experiments/regression_ce_context_...

python3 scripts/vguided-cegar/analyze_predicate_study.py --skip-validate \
  --dump-dir output/vguide/analysis_dumps/... \
  --logs-dir output/vguide/experiments/.../logs
```

---

## 4. 實作步驟（建議順序）

1. `formatCeSummary(ContextPack)` + unit-style 固定 pack 快照測試  
2. Wire `buildFirstSpurious`；log `prompt_chars` 變化  
3. 跑 regression 21 題  
4. 全量 217 + 報告更新  
5. 文件：`llm/PREDICATE_BUDGET.md` 交叉引用本計劃

---

## 5. 風險與回退

| 風險 | 緩解 |
|------|------|
| 模型抄 `.def_N` / SSA 名 | 摘要只保留 assert 子式；RULES 重申禁止 `@` / `.def` |
| prompt 變長導致慢 | 摘要已控在 ~500 tokens；non-thinking latency 仍低 |
| CE 误导 | 標註 "hints only"；assertion 仍從 source 讀 |

回退：`--option` 或 env `VGUIDE_PROMPT_CE_SUMMARY=false`（實作時加開關）。

---

## 6. 相關文件

- [OVERLAP_AND_PCS.md](OVERLAP_AND_PCS.md)  
- [llm/PREDICATE_BUDGET.md](../llm/PREDICATE_BUDGET.md)（數量策略，與 CE 正交）  
- [llm/LLM_CALL_SCHEDULING.md](../llm/LLM_CALL_SCHEDULING.md)（頻率，與 CE 正交）  
- 實驗基線：[reports/2026-06-09_notthinking_noL3.md](../reports/2026-06-09_notthinking_noL3.md)
