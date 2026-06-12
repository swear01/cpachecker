# 實驗計劃：提高 LLM 頻率 + 自適應 predicate 數量（non-thinking）

**狀態**：**已完成**（217 題 20260610；報告見 [reports/2026-06-10_freq10_n24_adaptive_noL3.md](../reports/2026-06-10_freq10_n24_adaptive_noL3.md)）  
**基線 tag**：`v1.2.0`（notthinking：`137` solved，`PAR-2 avg 228.48`）  
**本 run 結果**：**150** solved，`PAR-2 avg 192.03s`（+13 vs notthinking，+34 vs stock）  
**假設**：non-thinking 單條品質尚可（Novel ~58%），瓶頸在 **每 call 條數偏少** + **LLM 輪次偏少**。

---

## 1. 變更摘要（兩個一起調）

### 1.1 排程（相對 `v1.2.0` / `vguide.properties` 預設）

| 參數 | 預設 (v1.2.0) | **本實驗** |
|------|---------------|------------|
| `vguide.llmCallSchedule` | `every_n_and_interval` | 不變 |
| `vguide.llmEveryNSpuriousRefinements` | 72 | **24** |
| `vguide.llmMinIntervalSec` | 15 | **15**（不變） |
| `vguide.maxLlmRoundsPerAnalysis` | 5 | **10** |

**語意（`every_n_and_interval`）**

- Refinement **#1** 一定可叫（且不受 interval 擋）。
- 之後：spurious **#25, #49, #73, …**（`(refinementIndex - 1) % 24 == 0`）且距上次 LLM **≥15s**。
- 整場最多 **10 輪** LLM（`maxLlmRounds` 計 **輪次**；K=1 時 1 輪 = 1 API）。

**與 300s timelimit**

- 10 輪 × 15s 間隔 ≈ **135s** 排程等待（若每輪都踩滿）。
- non-thinking LLM ~2.5s/call → 10 API ≈ **25s**；**completion 變長**（見下）可能再加 ~10–20s/輪。

### 1.2 Predicate 數量（自適應 + **激進上調**）

**設計原則**：v1.2.0 品質夠好 → 中/高檔 **明顯多給**；低檔維持適度，避免簡單題 padding。

**複雜度分數 `S`（每輪 LLM 依當次 `ContextPack` 計算）**

| 因子 | 分數 |
|------|------|
| `loop_heads` 數量 | +1 / head（cap +3） |
| assertion 含 `bvand` / `bvurem` / `bvadd` 巢狀（regex） | +2 |
| 允許 scalar 變數數 `|contract|` | +1 若 ≥5；+1 若 ≥8 |
| source 有 array decl（index 題） | +1 |
| `refinement_index > 1`（later spurious） | +1 |

**檔位 → `(min, max)`（已定案）**

| 檔位 | S | min | max | 典型題 |
|------|---|-----|-----|--------|
| **low** | ≤3 | 4 | **8** | 單 loop、簡單 assert |
| **medium** | 4–6 | **6** | **12** | 雙 loop、`down` |
| **high** | ≥7 | **8** | **16** | `odd`、`vnew1`、多變數 / parity |

**Prompt 語氣**

- 刪除「fewer rather than weak fillers」。
- 「至少 `min` 條、至多 `max` 條；陣列順序 = 優先級；覆蓋 assertion + 跨 loop 耦合；每條不同角色。」

**實作（待開發）**

- `PredicateBudgetResolver.resolve(ContextPack, refinementIndex)` → `PredicateBudget` + `tier` + `S`
- 每輪重建 `ProposalPromptBuilder` 或注入動態 budget
- `llm_rounds.jsonl`：`budget_tier`, `budget_min`, `budget_max`, `complexity_score`

**全域護欄**

- 硬 cap **max = 16**（僅 high 檔觸及）。
- **`max_completion_tokens`：預設 1024 → 2048**（max≥12 時必開；16 條 JSON 約 800–1200 chars，留 reasoning 餘量）。
- `PredicateBudget.capOrdered` 仍為 parse 後硬截斷。

---

## 2. 為何不拆成兩個實驗？

一起調（你指定）；dump 記錄 tier / round / refinement 以便事後消融。若 PAR-2 變差 → **only-freq** 或 **only-budget** 子實驗。

---

## 3. 成本估算（更新：激進檔位）

| 項目 | v1.2.0 | 本實驗（粗估） |
|------|--------|----------------|
| API calls / 217 | 234 | **500–800** |
| median preds / call | 4 | **7–10**（高檔可達 12–16） |
| completion tokens / call | 低 | **↑30–80%**（視檔位） |
| LLM wall / 題（upper） | ~25s | **~80–200s**（10 輪 + 長 completion） |

平行 8、~500/min：仍可接受；監控 rate limit 與單題 timeout。

---

## 4. Test 計劃（實作後、217 前必跑）

### 4.1 單元測試（JUnit，`ant test` 或 targeted）

| 測試 | 內容 |
|------|------|
| `PredicateBudgetResolverTest` | 固定 `ContextPack` fixture：`S` 分檔 → low(4,8) / med(6,12) / high(8,16)；later refinement +1 分 |
| `PredicateBudgetTest` | `capOrdered` 在 max=16 時截斷、去重、保序 |
| `ProposalPromptBuilderTest` | 動態 min/max 出現在 prompt + JSON contract；無「fewer fillers」舊句 |
| `LlmEnsembleMergerTest` | union + cap 16 不丟順序 |

```bash
export PATH="$HOME/.local/ant/bin:$PATH"
export JAVA="${JAVA:-$HOME/.local/bin/java}"
ant build-project
ant junit.test -Dtest.class=org.sosy_lab.cpachecker.cpa.predicate.vguide.PredicateBudgetResolverTest
# …其餘 test class 同上
```

### 4.2 編譯與離線 LLM 品質（無 CPA）

```bash
export DEEPSEEK_API_KEY=...
python3 scripts/vguided-cegar/test_llm_proposal_quality.py
# 確認 VGUIDE_LLM_THINKING=disabled、thinking disabled、JSON 可解析
```

可選：對 `down` / `odd` / `string_concat-noarr` 各 3 次，檢查條數落在檔位內、`parse_ok`。

### 4.3 CPA smoke — `sample`（8 題）

```bash
export VGUIDE_LLM_THINKING=disabled
OUT=output/vguide/experiments/smoke_freq10_n24_adaptive_$(date +%Y%m%d)

./scripts/vguided-cegar/run.sh cpa \
  --set sample \
  --ablation no-l3 \
  --parallel 4 \
  --timelimit 300 \
  --out "$OUT" \
  --option vguide.llmEveryNSpuriousRefinements=24 \
  --option vguide.maxLlmRoundsPerAnalysis=10 \
  --option vguide.llmMinIntervalSec=15 \
  --option vguide.enableAdaptivePredicateBudget=true

# 通過條件：
# - 8/8 logs 有結束 verdict
# - log 含 VGuide LLM thinking: disabled
# - 至少一題 log 出現 llm round #2（驗證排程非僅 first）
# - 無大量 API / parse 異常
grep -h "VGuide LLM round" "$OUT/logs"/*.log | head -20
```

### 4.4 Regression 子集（建議 12–21 題，217 前）

Manifest：`docs/vguided-cegar/benchmark_sets/regression_nothink.list`  
含：`down`, `odd`, `ddlm2013`, `gr2006`, `bhmr2007`, `string_concat-noarr`, `vnew1`, `benchmark40_polynomial`, `mono-crafted_13`, `cggmp2005_variant`, …

```bash
# 待 list 就緒後
./scripts/vguided-cegar/run.sh cpa --set regression_nothink ...（同 smoke 參數）
```

**通過條件（regression）**

| 檢查 | 期望 |
|------|------|
| `odd` / `down` | refinements **< 50** 或 verdict 優於 v1.2.0 UNKNOWN |
| `response_parse_ok` | **≥95%** API calls |
| preds/call | high 檔 median **≥8** |
| dump `budget_tier` | 與題型一致（`odd` → high） |

### 4.5 Dump validate（regression 或 sample 帶 dump）

```bash
python3 scripts/vguided-cegar/analyze_predicate_study.py --validate-only \
  --dump-dir output/vguide/analysis_dumps/<smoke_or_regression> \
  --logs-dir "$OUT/logs" \
  --expected-tasks <N>
```

---

## 5. 實作清單

- [x] `PredicateBudgetResolver` + 檔位 (4,8)/(6,12)/(8,16)
- [x] `VGuideOptions.enableAdaptivePredicateBudget` + `llmMaxCompletionTokens`
- [x] Dumper 欄位：`budget_tier`, `complexity_score`, `budget_min/max`
- [x] `config/vguide-experiment-freq10-n24.properties`
- [x] `regression_nothink.list`
- [x] §4.1 unit tests（7 tests OK）
- [x] §4.3 CPA smoke sample 8/8（`smoke_freq10_n24_adaptive_20260610`）
- [ ] §4.2 離線 LLM 品質
- [ ] §4.4 regression_nothink
- [x] §4.5 dump validate + Phase D（217 題，見 reports/2026-06-10_freq10_n24_adaptive_noL3.md）
- [x] §6 Full 217 完成（150 solved，PAR-2 avg 192.03s）

---

## 6. Full 217 執行

```bash
export VGUIDE_LLM_THINKING=disabled
export VGUIDE_ANALYSIS_DUMP_DIR=output/vguide/analysis_dumps/full_scalar_noL3_freq10_n24_adaptive_20260610
export VGUIDE_ANALYSIS_DUMP_PROMPTS=1
export VGUIDE_ANALYSIS_BENCHMARK_SET=full_scalar
export VGUIDE_ANALYSIS_TIMELIMIT_SEC=300

export VGUIDE_CONFIG=config/vguide-experiment-freq10-n24.properties
OUT=output/vguide/experiments/full_scalar_vguide_noL3_freq10_n24_adaptive_20260610

./scripts/vguided-cegar/run.sh cpa \
  --set full_scalar \
  --ablation no-l3 \
  --parallel 8 \
  --timelimit 300 \
  --out "$OUT"
```

背景跑範例：

```bash
nohup env ... ./scripts/vguided-cegar/run.sh cpa ... \
  > output/vguide/experiments/runner_logs/full_scalar_freq10_n24_adaptive.log 2>&1 &
```

---

## 7. 分析（217 跑完）

| 步驟 | 命令 |
|------|------|
| vs stock | `post_batch_analysis.sh` |
| vs v1.2.0 / old_analysis | `analyze_benchmark_comparison.py` |
| 品質 | `analyze_predicate_study.py --skip-validate` |

**成功標準 vs 實測（20260610）**

| 指標 | 目標 | 實測 | 備註 |
|------|------|------|------|
| solved | ≥146 | **150** | ✓ 超 budget306（146） |
| PAR-2 avg | ≤235 | **192.03** | ✓ |
| vs stock rescued | ≥21 | **35** | ✓ |
| vs stock degraded | 0 | **1** | `benchmark10_conjunctive` |
| pct_novel median | ≥50% | **50%** | ✓ |
| high tier preds 8–12 | 期望 | **未觸發 high** | 僅 low/medium；medium median 9 |
| parse_ok | 穩定 | **99.0%** | 304/307 |

---

## 8. 風險與緩解

| 風險 | 嚴重度 | 緩解 |
|------|--------|------|
| JSON 截斷（max=16） | **高** | `max_completion_tokens=2048`；§4.2/4.3 監控 `parse_ok` |
| Redundant% 上升 | 中 | 接受部分 trade-off；看 solved 是否升 |
| completion 變長拖 PAR-2 | 中 | 對照 wall / PAR-2；必要時略降 max |
| 簡單題仍 4–8 | 低 | low 檔不變 |
| 無法归因 | 中 | dump tier + 消融 |

---

## 9. 檔位決策說明

中 **(6,12)**、高 **(8,16)** 對齊舊 thinking batch「常出 7–8 條且品質可」的上界，並讓難題有 **parity / 多 loop** 足夠槽位。低檔 **(4,8)** 避免簡單題浪費。若 regression 顯示 `parse_ok` 穩定且 Redundant 過高，可只收 high max **14** 再跑 217（不必先改計劃除非 smoke 失敗）。

---

## 10. 相關文件

- [ADAPTIVE_PREDICATE_BUDGET_PLAN.md](../llm/ADAPTIVE_PREDICATE_BUDGET_PLAN.md)
- [CE_CONTEXT_PROMPT_PLAN.md](../analysis/CE_CONTEXT_PROMPT_PLAN.md)
- [reports/2026-06-10_freq10_n24_adaptive_noL3.md](../reports/2026-06-10_freq10_n24_adaptive_noL3.md)
- [reports/2026-06-09_notthinking_noL3.md](../reports/2026-06-09_notthinking_noL3.md)
