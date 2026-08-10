# Loop-Head Invariant Candidates — Implementation Plan (Issue #4)

> Status: planning. 對應 [Issue #4](https://github.com/swear01/cpachecker/issues/4)
> （epic #11 Phase 1）。依賴 #3（structured CE）已 merged（PR #20）。
> 本文件先寫計劃，實作前需 user 確認。

## 0. Goal 與 Scope

**目標**：把「LLM 產生任意 predicates → Java 自動綁到所有 loop heads」收斂為
**per-loop-head invariant candidate contract**：每個候選帶明確 location、formula、
role、變數清單；只對自指的 loop head 驗證與注入；scope/type/location 不明的候選
一律不注入且失敗原因可觀察。Verdict soundness 不變（LLM 只產 Tier-S 候選，
L1/L2/L3 solver validation 維持）。

**In scope（本 issue checklist 1–9）**
1. 盤點現有 contract（完成，見 §1）
2. Versioned per-loop-head candidate schema（§2）
3. Prompt / parser 改為 location 與 formula 一起產出與解析（§3）
4. 變數 scope / type / bit-width / loop-head 可見性驗證（§4）
5. 多 loop-head 映射政策；禁止默認 broadcast（§5）
6. Supporting invariants 有序/分組驗證（§6）
7. 去重、衝突、過度具體檢查（metadata only，非 correctness proof）（§7）
8. 驗證與注入 outcome 寫入研究 dump（§8）
9. Tests：single / nested / multiple independent loops、shadowed variables、
   不同 bit-width、supporting conjunction（§9）

**Out of scope（後續 issue，不在此實作）**
- #5 bounded CE history、#6 native CEGAR predicates、#7 refinement outcomes、
  #8 LLM-predicate lifecycle、#9 multi-agent、#10 model comparison
- #2 core-only 448-run 評估：Phase 1（#3–#8）完成並過 freeze gate 後才執行
- Frozen seeds（`FrozenPredicateLoader` + `injectFrozen`）的顯式 broadcast：
  這是 user 提供的 config seed 機制，不是 LLM 輸出，保留現行為、文件標明

## 1. 現有 contract 盤點（checklist ①，已完成）

| 元件 | 現況 | 對 #4 的意義 |
|------|------|--------------|
| `ProposalPromptBuilder.buildJsonContract` | 明寫 `Do NOT use N* location keys; Java binds predicates to all loop heads` | **要改的源頭**：prompt 主動要求不帶 location |
| `LoopHeadCandidateParser` | 只抽 predicate 字串、無 location（`predicates` array）；rejected 清單可觀察 | parser 需升級為 typed candidates（已由本 PR 取代） |
| `PredicateValidationPipeline.validate` | L1 contract → L2 parse → 對 **trace 上每個** loop head 各做 L3 entailment；同一候選 broadcast 到所有 trace heads | 正是要禁的默認 broadcast；L3 保留為 soundness gate |
| `ValidatedPredicate(formula, loopHeadNode, Classification{ENTAILED,PRECISION_ONLY})` | 已帶 location，但無 role/變數/失敗原因/注入狀態 | 擴充為完整 candidate record |
| `LoopHeadBlockFormulaIndex.fromTrace` | trace node → block formula；不在 trace 的 head 無公式 | 未上 trace 的命名 head 需明確定義（不驗證＝不注入，原因可觀察） |
| `LoopHeadPrecisionInjector.inject` | 逐 (node, formula) 注入 local predicates，dedup key `node:formulaHash` | dedup 移到 validation stage 讓 dump 可見；注入邏輯本身保留 |
| `LoopHeadPrecisionInjector.injectFrozen` | broadcast 到全部 heads（frozen seed 專用） | 保留、文件標明（explicit opt-in，非 LLM 路徑） |
| `ContextPack` | loopHeads / varContract / encodedVars / blockFormulas / ceSummary（已含 #3 structured CE） | scope 檢查的資料來源 |
| `VGuideAnalysisDumper`（schema-4） | `validated_predicates` 每條含 loop_head/classification；`injected_predicates` 另列 | 升 schema-5，加 failure reason / role / stage 結果 |

## 2. Candidate contract v1（checklist ②）

新 JSON 輸出契約（prompt 內宣告 `candidate-contract-v1`）：

```json
{
  "loop_head_invariants": [
    {
      "loop_head": "N19",
      "formula": "(bvsge i (_ bv0 32))",
      "role": "bound",
      "variables": ["i"]
    },
    {
      "loop_heads": ["N19", "N23"],
      "formula": "(bvslt i k)",
      "role": "relational",
      "variables": ["i", "k"]
    }
  ]
}
```

- `loop_head`（單一，必填）或 `loop_heads`（顯式多 head array）：label 必須是
  prompt 的 `LOOP HEADS` 清單中的 `N*`；解析後對應 `LoopHeadInfo.node`。
- `role`（optional metadata）：`initiation | supporting | relational | bound`。
- `variables`（optional 交叉檢查清單）：與實際 free variables 比對，不符僅記錄。
- **向後相容政策**：舊 `{"predicates": [...]}` 格式仍可解析，但語意改變——
  無 location → 一律 **reject `missing_loop_head`，不注入、不 broadcast**。
  這是顯式行為變更（prompt 已同步改），不是 silent fallback。
- **Failed-candidate 清單**（仿 `parseWithRejects`）：所有 reject 原因可觀察，
  供 repair prompt 與 dump 使用。

## 3. Prompt 與 Parser（checklist ③）

**Prompt（`buildJsonContract` 重寫）**
- 刪除 `Do NOT use N* location keys...`；改為：
  - 每個候選必須附 `loop_head`（從 LOOP HEADS 清單選）；
  - 跨多 head 用 `loop_heads` array（僅在公式對多個 head 都有意義時）；
  - 未附 location 的候選會被丟棄且計入 rejected；
  - role 建議（initiation/supporting/relational/bound），維持 min/max 條數。
- 範例同步改（含 `loop_head` 欄位）；repair tail 沿用，加入 rejected reasons 提示。
- Prompt 內註記 `candidate-contract-v1`，錄下來的 prompt 自描述版本。

**Parser（`LoopHeadCandidateParser`，取代 `LlmResponseParser`）**
- 新 `parseCandidates`：產出 `CandidateInvariant` records
  （`loopHeadLabels` / `formula` / `role` / `declaredVariables` / 原始 JSON）。
- Label → `LoopHeadInfo` 解析：`N<nodeNumber>` 唯一對應；
  未知 label → `unknown_loop_head`（reject，原因可觀察）。
- 舊 `parsePredicates` 保留給 repair / frozen 路徑相容；LLM 主路徑走新方法。
- `PredicateContractValidator.isValid`（L1）維持在 parser 層先做（現行位置）。

## 4. Scope / type / bit-width / loop-head 可見性驗證（checklist ④）

在 L2 parse 之後新增 `scope check` stage（`PredicateValidationPipeline` 內）：

- 對 parsed formula 取 free variables（JavaSMT `extractFreeVariableMap` 或等價 API，
  實作時確認）。
- **可見性**：每個 free var 必須屬於該 loop head 所在 function 的可見變數
  （來源：`pack.varContract()` 對應 function 的變數 ∪ `pack.encodedVars()`）；
  否則 reject `variable_not_in_scope`（含變數名，方便 repair）。
- **type / bit-width**：由 L2 parse 的 sort 檢查涵蓋（`parsePredicate` 在
  sort 不符時回 null）→ 記為 `parse_error`；不另做 heuristic 判定。
- **Loop-head 可見性**：候選的 head 必須在 `pack.loopHeads()`；否則
  `unknown_loop_head`。
- 所有 reject 原因進入 failed-candidate 清單（§2），與 L1/L2/L3 結果一起寫 dump。
- Shadowed variables（不同 function 同名）：以「每個候選只綁一個 head」+
  該 head 的 function scope 解析，天然區分。

## 5. 多 loop-head 映射政策（checklist ⑤）

- **默認：候選只綁它自指的 head**（`loop_head`）。無任何隱式 broadcast。
- 顯式 `loop_heads` array：對每個命名 head 各別做完整驗證（含 §4 scope check
  與 L3 entailment），任一 head 失敗不影響其他 head 的注入。
- 命名 head 不在 spurious trace 上 → 無 block formula，無法 L3 → **不注入**，
  記錄 `head_not_on_trace`（現行行為已是跳過，現加可觀察原因）。
- `ValidatedPredicate` 維持一 record = (formula, 單一 loopHeadNode, classification)，
  multi-head 候選展開成多條，各自獨立驗證與注入。

## 6. Supporting invariants 有序/分組驗證（checklist ⑥）

- `role=initiation`：先驗證（L3：head block formula → 候選）。
- `role=supporting`：在 initiation 之後驗證，並做 **group consistency check**：
  `block ∧ 同 head 其他候選 ∧ 本候選` 必須 SAT；UNSAT → 記 `group_conflict`。
- Group check 是 **advisory metadata，不是 correctness proof**：不阻擋個別
  L3 通過的候選注入（注入多餘 predicate 不影響 soundness，只影響效率）；
  結果一律寫 dump。
- 排序資訊（initiation 先於 supporting）只影響 group check 的組合方式，
  不影響注入順序語義。

## 7. 去重 / 衝突 / 過度具體（checklist ⑦）

- **去重**：canonical 化（`fmgr.dumpFormula` 正規化）+ head node 作 key，
  從 injector 移到 validation stage，dump 顯示 `dedup` 狀態（不再無聲丟棄）。
- **衝突**：同 head 同輪候選間 `block ∧ c1 → ¬c2`（L3 可判定）→ 記 `conflict`；
  metadata only。
- **過度具體**：候選含未出現在該 head scope 的常數/變數（§4 已擋 scope 違規）；
  另記 heuristic flag `over_specific`（如公式僅含非常量且與 trace 無關）——
  **僅記錄，不作 correctness 判定**（issue 明示不得把 heuristic 當 proof）。
- 所有 flags 進 dump，不影響 soundness gate（L1/L2/L3 + scope）。

## 8. Dump（checklist ⑧）

`VGuideAnalysisDumper` 升 **schema-5**（additive，向後相容；既有 consumer
`scripts/vguided-cegar/analyze_predicate_study.py` 不受影響）：

- `validated_predicates` 每條新增：`role`、`declared_variables`、
  `scope_check`（pass/reject reason）、`dedup`（bool）、`conflict`（bool/詳情）、
  `over_specific`（bool）。
- 新增 `candidate_rejections` 陣列：每條 reject 的候選含 raw text、head label、
  failure reason（`missing_loop_head | unknown_loop_head | contract_violation |
  parse_error | variable_not_in_scope | head_not_on_trace`）、stage 與 round。
- `injected_predicates` 維持現行 per-node 記錄（加 `dedup` 標記）。
- Manifest `schema_version` → `"5"`；`PREDICATE_ANALYSIS_PLAN.md` 的 schema 表同步。

## 9. Tests（checklist ⑨）

Unit-level（沿用現有 vguide tests 的 synthetic pack / CFA 方式）：

| 測試 | 場景 |
|------|------|
| `LoopHeadCandidateParserTest` | 新契約解析；legacy `predicates` → `missing_loop_head`；未知 label；multi-head array；malformed JSON |
| `LoopHeadCandidateValidatorTest`（新） | single-loop 正常注入；**nested-loop**（內外兩個 heads 各自綁定）；**multiple independent loops**；shadowed variables（同名不同 function，各綁各的 head）；不同 bit-width（int vs long → parse_error）；supporting group conflict flag；dedup |
| Mapping | 候選指名 N19 不得注入 N23（no-broadcast 的負向測試）；`loop_heads` 顯式多 head |
| `VGuideAnalysisDumper` 測試 | schema-5 欄位存在、rejections 陣列格式 |
| 既有測試回歸 | `ProposalPromptBuilderTest`（prompt 新契約）、`PredicateValidationPipeline` 相關 |

## 10. Docs 更新

- 新文件：本計劃（`LOOP_HEAD_INVARIANT_PLAN.md`）
- `architecture/UNIFIED_VGUIDE_ARCHITECTURE.md`：candidate contract v1、映射政策
- `analysis/PREDICATE_ANALYSIS_PLAN.md`：dump schema-5、failure reasons
- `README.md`：Phase 1 進度連結
- `STRUCTURED_COUNTEREXAMPLE_CONTEXT.md`：cross-ref（CE 的 loop_head 欄位 ↔ 候選綁定）
- `docs/roadmap.md` / `docs/plan.md`：狀態更新

## 11. 執行順序與 PR 計劃

單一 PR（branch `issue4-loop-head-invariants`，從更新後 main 開），commit 順序：

1. Candidate contract + parser（§2–3）+ parser tests
2. Scope/visibility validation + multi-head mapping + supporting group（§4–6）+ tests
3. Dedup/conflict flags + dump schema-5（§7–8）+ tests
4. Docs（§10）

驗證：`ant build-project` + `ant tests -Dtest.only=...`（新增與受影響 tests）；
跑既有 vguide unit tests 全綠才動。後續 dev-split smoke 依
`CORE_ONLY_EVALUATION_PLAN.md` 的 gate（Phase 1 完成後，非本 PR）。

## 12. 風險與緩解

| 風險 | 緩解 |
|------|------|
| LLM 新格式初期 accepted rate 下降 | rejected reasons 可觀察 → repair path；dev split 量測，不 tune prompt 到 overfit |
| 行為變更（legacy predicates 不再 broadcast）造成既有 dev tasks 回歸 | 顯式 reject + dump 可歸因；dev split 對比；0-wrong gate 優先 |
| 未知 label / label 解析失敗 | `unknown_loop_head` 可觀察；prompt 明確給 LOOP HEADS 清單 |
| scope check 誤殺（encoded 名稱 vs source 名稱） | 可見性判定以 varContract + encodedVars 為準，實作時用既有 frozen/dev 案例驗證 |
| dump schema 變更破壞分析 script | additive fields；schema-5 相容測試 |

## 13. 驗收對照（Issue #4 acceptance criteria）

- 每個 injected predicate 都有唯一 loop-head provenance ✅（§5 mapping + §8 dump）
- 無 scope/type/location 對應的候選不注入，失敗原因可觀察 ✅（§4 + §8 rejections）
- 不把候選無條件注入所有 loop heads ✅（§5，prompt 同步移除 broadcast 指令）
- L1/L2/L3 + scope 保持 verdict soundness；LLM 不決定 verdict ✅（§4，Tier S）
- Tests 覆蓋多 loop head / shadowed variables / bit-width / supporting conjunction ✅（§9）
- Hard-case ablation 報告 per-location candidate validity、injection、progress 與
  solved delta —— 屬 #2 評估（Phase 1 完成後），非本 PR 產出。
