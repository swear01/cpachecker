# 離線 LLM 抽樣 vs CPA 內 LLM（為何會「不一致」）

## 兩條路徑

| 維度 | 離線 `test_llm_proposal_quality.py` | CPA `VGuideRefinementBridge` |
|------|-----------------------------------|------------------------------|
| **何時呼叫** | 手動、靜態讀 `.i` 檔 | **第一條（或排程允許的）spurious path** 當下 |
| **Prompt** | 簡化：源碼 + `__VERIFIER_assert` + 通用規則；**無** loop-head block、**無** SSA `encodedVars`、**無** 當輪 interpolants | `ContextPackBuilder` + `ProposalPromptBuilder.buildFirstSpurious`：含 **var contract**、trace、loop heads、block formulas 摘要 |
| **驗證** | Python `FORBIDDEN`（應與 Java `PredicateContractValidator` 對齊） | Java validator → `PredicateValidationPipeline` → loop-head 注入 |
| **成本** | 便宜、可 5× 重複看穩定性 | 完整 CEGAR + SMT；真實品質驗收 |
| **目的** | 快速篩 JSON／字串／合約違規 | **主路徑**是否 rescue |

因此 **不是兩套 API 或兩個模型**，而是 **上下文不同**：離線像「只看原始 C 的出題」；CPA 內像「CEGAR 已走到 spurious、帶 SSA 合約的出題」。

**v1.4 計劃**（[DUAL_PROMPT_V1_PLAN.md](../analysis/DUAL_PROMPT_V1_PLAN.md)）：CPA 內將有 **SAFE+BUG 雙 profile** 與 **ce_summary**；離線腳本 **尚未** 模擬這兩項，對齊後再當 regression。

API 參數（model、**thinking disabled** 等）應與 Java `PredicateProposalClient` 一致，見 [LLM_API.md](LLM_API.md)。

## 典型現象：`array_3-1`

- **離線 5×**：常得到 `(>= i 0)`、`(<= i 1024)`、`(= A[i] 0)` — 字面上像「找零元素」的直覺，但 **`A[i]` 違反合約**（無 select/store、應只用 index 關係）。
- **CPA 內（first_spurious）**：曾見 **極短回應（~57 bytes）**，artifact 解析後像內部 `.def_*` 公式 — 多因 **prompt 壓力 + 合約欄位** 與離線不同，模型走捷徑。

**結論：**

1. 離線 **不能** 代替 CPA 路徑的 pass/fail 判定。  
2. 離線 **可以** 做 cheap regression（JSON 可解析、禁止 `A[i]`、禁止 `|main::|`）。  
3. 要以 CPA 為準時：跑 `verify-pack` 或 batch，看 `logs/<task>.log` 裡的 `VGuide LLM round` / `VGuide predicate`。

## 建議工作流

```text
1) 改 prompt / validator 後 → python3 scripts/vguided-cegar/test_llm_proposal_quality.py
   （預設 16 路平行 HTTP；DeepSeek ~500/min）
2) 通過合約的題 → `./scripts/vguided-cegar/run.sh verify-pack --task array_3-1`
3) Tier S sample 批次 → scripts/vguided-cegar/run_benchmark_set.sh sample
   （預設 PARALLEL=8 個 CPA）
```

## 對齊離線與 Java 合約

離線腳本 `FORBIDDEN` 應與 `PredicateContractValidator` 同步（含 **禁止 C 下標 `A[i]`**）。兩邊 prompt 都應強調：**array 題只用 index 邊界與迴圈守衛，不要寫 `A[i]`**。

執行：`./scripts/vguided-cegar/run.sh llm-quality`。舊抽樣快照見本機 `archive/vguided-docs/llm/LLM_QUALITY_SAMPLE.md`。
