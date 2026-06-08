# VGuide 分析計劃：Context Budget、Predicate 重疊與貢獻度

**狀態**：Phase A–E 已完成（2026-06-08）；overlap/PCS **僅 Z3**（1799 列）  
**結果報告**：[2026-06-08_predicate-analysis_noL3.md](../reports/2026-06-08_predicate-analysis_noL3.md) · [OVERLAP_AND_PCS.md](OVERLAP_AND_PCS.md)  
**主實驗 config**：`full_scalar_vguide_noL3`（L3 off）  
**Benchmark**：`full_scalar` **217 題全跑**（分析專用重跑，見 §6）  
**原 headline 實驗**：[`reports/2026-06-07_vguide-report_deepseek-v4-pro.md`](../reports/2026-06-07_vguide-report_deepseek-v4-pro.md)（145/217；本輪重跑 **verdict 可漂移**，分析以新 dump 為準）

**原則**：**一次 instrumentation + 一次 217 題重跑**，蒐集 §4 全部欄位；PCS / overlap 的 SMT **離線算**，不再為補資料二次跑 CPA。

**暫不納入**：Hybrid L3、改 prompt、調 `everyN`（§10）。

---

## 1. 分析三軸

| 軸 | 問題 | 資料來源 |
|----|------|----------|
| **A. Context budget** | 送進 DeepSeek 多少 token？擴 prompt 後剩多少？ | API `usage`（ground truth）+ prompt 組件 |
| **B. Overlap** | LLM predicate vs interpolant / precision / trace？ | 全量 dump（§4） |
| **C. PCS** | 每一條 LLM predicate 多有用？ | 全量 dump → **離線 Z3**（§5；`z3_overlap.py`） |

---

## 2. Token 計量（Ground truth = API `usage`）

### 2.1 決策

**主數字以 DeepSeek Chat Completions 的 `usage` 為準**（每次 HTTP call 一筆，含 repair call）。

必記欄位：

```json
{
  "prompt_tokens": 0,
  "completion_tokens": 0,
  "total_tokens": 0,
  "prompt_cache_hit_tokens": 0,
  "prompt_cache_miss_tokens": 0,
  "prompt_tokens_details": {},
  "completion_tokens_details": { "reasoning_tokens": 0 }
}
```

文檔：[Token & Token Usage](https://api-docs.deepseek.com/quick_start/token_usage)

**現況（Phase A ✅）**：`PredicateProposalClient.proposeWithUsage()` 解析並回傳 `usage`；`llm_rounds.jsonl` 每 HTTP call 一筆。

### 2.2 離線輔助

HF `deepseek-ai/DeepSeek-V4-Pro` tokenizer 僅用於 **prompt 組件分解**與對照 `usage`；不作主報告。

---

## 3. Context budget（分析項，非重跑條件）

### 3.1 當前 prompt 組成

| 區塊 | first | later | **必 dump** |
|------|-------|-------|-------------|
| Rules + instruction | ✓ | ✓ | `chars_rules` |
| C source | ✓ | ✓ | `chars_source` |
| Loop heads | ✓ | ✓ | `chars_loop_heads` |
| Var contract | ✓ | ✓ | `chars_contract` + JSON |
| Trace summary（≤5 blocks） | ✗ | ✓ | `chars_trace` + 原文 |
| Interpolants | 未進 prompt | 未進 prompt | **仍 dump**（overlap 用） |
| Precision history | 未進 prompt | 未進 prompt | **仍 dump**（overlap 用） |

### 3.2 已知結論（舊 batch 估算）

first-spurious median ~583 tokens（HF），max ~1127；**≪ 1M**。全量重跑後以 **API `usage` 覆寫**。

### 3.3 Sensitivity（離線，dump 齊後亦可重算）

假設把 precision history / interpolant atoms 加進 prompt 的 token 增量——用 dump 內實際 SMT 字串算，不靠猜。

---

## 4. 資料蒐集契約（**一次重跑必齊，缺則視為 run 失敗**）

環境變數（建議）：

```bash
export VGUIDE_ANALYSIS_DUMP_DIR=output/vguide/analysis_dumps/<run_id>
export VGUIDE_ANALYSIS_DUMP_PROMPTS=1   # 寫入完整 .prompt.txt
```

輸出目錄結構：

```
<run_id>/
  run_manifest.json              # config、git hash、model、timelimit
  tasks/<task>/
    cpa.log                      # 標準 CPA log（可 symlink 自 experiments）
    task_summary.json            # 見 §4.3
    refinements.jsonl            # 每一 spurious refinement 一行（§4.4）
    llm_rounds.jsonl             # 每一次 API call 一行（§4.5）
    prompts/                     # 可選完整字串
      r001_first.prompt.txt
      r073_later.prompt.txt
      r001_repair.prompt.txt
```

### 4.1 `run_manifest.json`（整批一次）

| 欄位 | 說明 |
|------|------|
| `run_id`, `started_at` | |
| `benchmark_set` | `full_scalar` |
| `task_count` | 217 |
| `config` | `predicateAnalysis-vguide.properties` + `vguide.*` 有效值 |
| `model` | `DEEPSEEK_MODEL` / default |
| `timelimit_sec`, `timeout_grace_sec` | |
| `git_commit` | 儀器化版本 |
| `schema_version` | dump JSON schema 版本（ bumped 若改欄位） |

### 4.2 每一次 **LLM API call**（`llm_rounds.jsonl` 一行）

含 **primary / ensemble / repair** 每次 `propose()`。

| 欄位 | 必填 | 說明 |
|------|------|------|
| `task` | ✓ | |
| `refinement_index` | ✓ | spurious # |
| `llm_round_index` | ✓ | 1..maxLlmRounds |
| `api_call_index` | ✓ | 該 refinement 內第幾次 HTTP |
| `call_kind` | ✓ | `primary` \| `ensemble_extra` \| `repair` |
| `prompt_kind` | ✓ | `first` \| `later` \| `repair` |
| `usage` | ✓ | §2.1 完整 object |
| `latency_ms` | ✓ | |
| `prompt_chars` | ✓ | 實際送出字串長度 |
| `prompt_components` | ✓ | `{source, contract, trace, rules, loop_heads}` 字元數 |
| `prompt_path` | 若 `DUMP_PROMPTS=1` | 相對路徑 |
| `response_raw` | ✓ | 完整 assistant content |
| `response_parse_ok` | ✓ | JSON 是否可解析 |
| `predicates_raw` | ✓ | 解析出的字串列表（修復前） |
| `predicates_rejected` | ✓ | L1/L2 拒絕列表 + `reason` |
| `schedule` | ✓ | `every_n_and_interval` 等 + `everyN`, `minIntervalSec` |

### 4.3 每一題結束（`task_summary.json`）

| 欄位 | 必填 | 說明 |
|------|------|------|
| `task` | ✓ | |
| `verdict` | ✓ | TRUE/FALSE/UNKNOWN |
| `wall_s` | ✓ | |
| `refinements` | ✓ | |
| `llm_rounds` | ✓ | 實際 API round 數 |
| `llm_api_calls` | ✓ | 含 ensemble + repair |
| `vguide_outcome` | ✓ | `FIRST_SPURIOUS_LLM` / `NO_SPURIOUS_GIVE_UP` / … |
| `stock_verdict` | ✓ | 對照用（讀既有 stock log，不 rerun stock） |
| `precision_final` | ✓ | 終局 local+global predicate SMT 列表（§4.6） |
| `total_usage` | ✓ | 該題所有 call 的 `prompt_tokens` / `completion_tokens` 加總 |

### 4.4 每一次 **spurious refinement**（`refinements.jsonl` 一行）

**不論是否呼叫 LLM** 都寫一行（才能解釋 skip、算 Δrefs）。

| 欄位 | 必填 | 說明 |
|------|------|------|
| `refinement_index` | ✓ | |
| `llm_called` | ✓ | bool |
| `llm_skip_reason` | 若 false | `schedule` \| `max_rounds` \| `wall_budget` \| `no_interpolants` \| … |
| `interpolants_pre` | ✓ | `[{index, node, smt}]` 注入前插值（**overlap O-I**） |
| `block_formulas` | ✓ | CE 上 block SMT（至少與 `summarizeTrace` 同源；建議 **全 blocks**，不只 5 個） |
| `trace_summary_in_prompt` | 若該輪有 LLM | later 時實際進 prompt 的 trace 字串 |
| `var_contract` | ✓ | source → encoded SSA sets |
| `loop_heads` | ✓ | `[{label, node, function}]` |
| `precision_local_before` | ✓ | loop head → [smt]（**overlap O-P**） |
| `precision_global_before` | ✓ | [smt] |
| `abstraction_states` | ✓ | `[{index, node}]` 與 interpolant 對齊 |
| `llm_round_index` | 若 called | 連到 `llm_rounds.jsonl` |
| `validated_predicates` | 若 called | 見 §4.5 |
| `precision_injected` | 若 called | 實際注入的 (loop_head, smt) |
| `precision_local_after` | ✓ | 本輪 refinement 結束後 |

### 4.5 每一條 **validated predicate**（嵌在 refinement 或獨立 `predicates.jsonl`）

分析單位：**(task, refinement_index, predicate_id, loop_head)**。

| 欄位 | 必填 | 說明 |
|------|------|------|
| `predicate_id` | ✓ | 題內遞增 id |
| `raw_string` | ✓ | LLM 原始 |
| `smt_dump` | ✓ | Java parse 後 `fmgr.dumpFormula` |
| `loop_head` | ✓ | `Nxx` |
| `classification` | ✓ | noL3 恆 `PRECISION_ONLY` |
| `l1_ok`, `l2_ok` | ✓ | |
| `injected` | ✓ | 是否進 precision |
| `block_formula_smt` | ✓ | 該 head 上用于 L3 check 的 block（PCS / vacuous） |

### 4.6 終局 precision snapshot

`task_summary.json` 的 `precision_final`：

```json
{
  "global": ["(assert ...)", "..."],
  "local": { "N30": ["..."], "N40": ["..."] }
}
```

### 4.7 NO_SPURIOUS（0 refinement）

仍寫 `task_summary.json` + `refinements.jsonl` **0 行**；`vguide_outcome` = `NO_SPURIOUS_GIVE_UP` 或 `FROZEN_SEED_EXCEPTION`；若有 frozen inject 記 `precision_final`。

### 4.8 標準 CPA log（保留）

`cpa.log` 仍須含既有行（`VGuide LLM round`、`VGuide predicate`、verdict），作 **人工抽查** 與 dump 交叉驗證。

---

## 5. Overlap 與 PCS（**離線 Z3**，不重跑 CPA）

dump 齊全後，由 `scripts/vguided-cegar/analyze_predicate_study.py` + `z3_overlap.py` **全 217 題**跑。語意與欄位定義見 [OVERLAP_AND_PCS.md](OVERLAP_AND_PCS.md)。

### 5.1 Overlap（Z3 entailment）

對每條 `validated_predicates` 中的 `q`：

| 代號 | 對照 | Z3 檢查 |
|------|------|---------|
| **O-I / R_I** | `interpolants_pre` @ 同 `loop_head` | `I ⊨ q`（UNSAT `I ∧ ¬q`） |
| **O-T / R_T** | `block_formula_smt`（該 head 的 CE block） | `B ⊨ q`（UNSAT `B ∧ ¬q`） |
| **O-P / R_P** | `precision_local_before[loop_head]` | `P_loc ⊨ q`（**僅當** precision 與 `q` 同一 SSA 符號名） |

分類：`max(R_I, R_P, R_T) ≥ 0.9` → **Redundant**；`≤ 0.1` → **Novel**；否則 Orthogonal。

**本輪結果**（1799 predicates）：Novel **992**（55%）/ Redundant **807**（45%）。

### 5.2 PCS（每 predicate 一列 → `pcs_per_predicate.csv`）

| 欄位 | 離線計算 |
|------|----------|
| `R_I`, `R_T`, `R_P` | 上表 Z3 結果（0/1；`unknown`→0.5；`skip`→0） |
| `N` | `1 - max(R_I, R_P)`（PCS 分量，**不含** R_T） |
| `overlap_class` | Redundant / Novel / Orthogonal |
| `in_final_precision` | 終局 `precision_final` 字串比對（輔助欄位） |
| `task_solved` | 對 `task_summary.verdict` |
| `pcs_mode` | 固定 `z3` |

**不在 CPA 內重跑**；全量 1799 列本機約數秒（`--z3-timeout-ms 8000`）。

---

## 6. 全量重跑執行計劃

### Phase A — 儀器化（跑 217 前必完成）✅

- [x] `PredicateProposalClient`：解析並回傳 `usage`
- [x] `VGuideAnalysisDumper`：寫 §4 目錄結構
- [x] `refinements.jsonl`：每 spurious 一行（含 **無 LLM**）
- [x] `block_formulas` **全量**（不只 prompt 內 5 個）
- [x] `interpolants_pre` 全量
- [x] repair call 獨立記 `usage` + `prompt`
- [x] smoke：`down` / `up` 等單題驗證

### Phase B — 217 題重跑 ✅

```bash
export VGUIDE_ANALYSIS_DUMP_DIR=output/vguide/analysis_dumps/full_scalar_noL3_<date>
./scripts/vguided-cegar/run.sh cpa \
  --set full_scalar --timelimit 300 --parallel 8 \
  --out output/vguide/experiments/full_scalar_vguide_noL3_analysis
```

- config：**noL3**（與現主線一致）
- **不**改 `everyN`（本輪只蒐集資料）
- 產物：`experiments/.../logs/*.log` + `analysis_dumps/<run_id>/tasks/*`

### Phase C — 跑後驗收（§7）✅

- V3 off-by-one：預期（見結果報告 §2.2）
- 7 hang 題已補跑；217/217 有 `task_summary.json`
- V7：3 條 SSA 字串 warn（非 fail）

### Phase D — 離線分析 + 報告 ✅（Z3 overlap / PCS）

- `output/vguide/analysis_dumps/full_scalar_noL3_20260608/analysis/*.csv`
- `scripts/vguided-cegar/analyze_predicate_study.py` + `z3_overlap.py`
- Overlap：Novel **992**（55%）/ Redundant **807**（45%）

---

## 7. 跑後驗收清單（**缺一項 = 資料不完整，需修 dumper 再重跑**）

對 **217 題每一題** 自動檢查（`analyze_predicate_study.py --validate-only`）：

| # | 檢查 | 條件 |
|---|------|------|
| V1 | 題目覆蓋 | `tasks/` 下 217 個 task 目錄 |
| V2 | `task_summary.json` | 存在且 `verdict` 非空 |
| V3 | `refinements.jsonl` 行數 vs `task_summary.refinements` | **spurious 行數** = CPA 總次數，或 **CPA−1**（最後一輪為 feasible CE / 非 spurious）；差 >1 為 warn（`analyze_predicate_study.py` 已放寬） |
| V4 | LLM 題 | 每個 `llm_round` log 行有對應 `llm_rounds.jsonl` 且 `usage.prompt_tokens > 0` |
| V5 | 無 LLM 的 refinement | `llm_skip_reason` 必填 |
| V6 | 有 LLM 的 refinement | `interpolants_pre` 非空、`validated_predicates` 存在（可空陣列） |
| V7 | 每條 injected predicate | `injected=true` 者須列於 `precision_injected`；與 `precision_local_after` 以 **canonicalized assert** 比對（SSA `@N`、`.def_N` 正規化）。字串仍不合 → **warn**（注入語意上常仍成立） |
| V8 | `precision_final` | 存在（含空） |
| V9 | repair | 若 log 含 `repair LLM call`，`llm_rounds` 必有 `call_kind=repair` |
| V10 | prompt 檔 | 若啟用 `DUMP_PROMPTS`，每個 `usage` 行有 `prompt_path` 且檔案存在 |

**通過標準**：V1–V10 對 217 題 **零失敗**（或明確列為 `INCOMPLETE` 的 hang 題，且仍有 V2 + partial refinements）。

---

## 8. 與舊 batch 的關係

| 項目 | 舊 `full_scalar_vguide_noL3` | 本輪 |
|------|------------------------------|------|
| verdict / PAR-2 | 145/217 已發表 | 可能略漂移；**分析用新 dump** |
| `VGuide predicate` log | 有 | 保留 + dump 交叉驗證 |
| interpolant / usage / precision snapshot | **無** | **本輪補齊** |
| 能否事後從舊 log 補？ | **不能** | 必須重跑 |

---

## 9. 階段產物索引

| 路徑 | 內容 |
|------|------|
| `output/vguide/analysis_dumps/<run_id>/` | 原始 dump（長期保存） |
| `output/vguide/experiments/full_scalar_vguide_noL3_analysis/` | CPA logs + summary CSV |
| `output/vguide/analysis_dumps/<run_id>/analysis/context_budget.csv` | 離線分析輸出 |
| `output/vguide/analysis_dumps/<run_id>/analysis/pcs_per_predicate.csv` | 全 217 |
| `output/vguide/analysis_dumps/<run_id>/analysis/overlap_summary.csv` | 全 217 |
| `output/vguide/analysis_dumps/<run_id>/analysis/analysis_report.md` | 自動摘要 |

---

## 10. 相關 todo（本計劃外 — 消融 / 下一輪實驗）

| 項目 | 說明 | 狀態 |
|------|------|------|
| Z3 overlap / PCS | `analyze_predicate_study.py` + `z3_overlap.py`（`pcs_mode=z3`） | ✅ |
| **Pre-CEGAR LLM（0-refinement bootstrap）** | 在**尚無任何 spurious refinement**（CEGAR loop 前 / 0-refinement 時點）先呼叫 LLM 注入 predicate；對照現行「first spurious 後才呼叫」。比 verdict、PAR-2、refinement 次數、token | **未做**（需新 config + 217 或子集） |
| 調 `vguide.llmEveryNSpuriousRefinements` | 更多 spurious 輪叫 LLM（現行 5.5%） | 未做 |
| ~~predicate budget~~ | `minPredicatesPerCall` / `maxPredicatesPerCall`（預設 3–6） | ✅ |
| prompt 加 interpolant | overlap 已定稿（55% Novel）；評估是否值得擴 prompt | 未做 |
| Hybrid L3 | 不納入 | — |
| NO_SPURIOUS frozen seed | 0 refinement 時讀 `predicate_sets/`（非 LLM API）；見 [FROZEN_PREDICATES.md](../evaluation/FROZEN_PREDICATES.md) | 已實作（Exception 路徑） |

---

## 11. 參考

- [Token & Token Usage](https://api-docs.deepseek.com/quick_start/token_usage)
- [`reports/2026-06-07_vguide-report_deepseek-v4-pro.md`](../reports/2026-06-07_vguide-report_deepseek-v4-pro.md)
- [`llm/LLM_CALL_SCHEDULING.md`](../llm/LLM_CALL_SCHEDULING.md)
- IC3ia redundant predicates（Griggio et al., FMSD 2016）
- Henzinger et al., «Abstractions from proofs»
