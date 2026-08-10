# Bounded Counterexample History — Implementation Plan (Issue #5)

> Status: implementing. 對應 [Issue #5](https://github.com/swear01/cpachecker/issues/5)
> （epic #11 Phase 1）。依賴 #1（dataset）、#3（structured CE）已完成；
> #4（per-loop-head candidates）已 merged。本文件先寫計劃。

## Goal 與 Scope

跨 CEGAR rounds 累積 **CE evidence/history**（structured CE artifact），讓 LLM 看到
counterexample 如何隨 refinement 演化（repeated failure pattern、loop peeling、
missing relational invariant），且 context 有硬上限、deterministic、不跨 task 洩漏。

**In scope（checklist）**
1. CE history entry + analysis-level history store（`CeHistoryStore`，per-bridge instance）
2. 每輪以 structured CE（`structured-ce-v1` JSON）保存
3. CE identity/dedup：whole-CE SHA-256 fingerprint；連續相同 CE 合併為 repeat count
4. current-vs-previous delta：loop-head visits 變化、新增/消失 heads、relations 變化
5. Bounded policy：recent-N（N=4，record-time evict，oldest first）+ build-time char cap（4000）
6. Token budget 與 deterministic eviction（char cap，固定順序）
7. History metadata 寫入 dump（`ce_history` + `ce_history_omitted`）
8. Ablation mode：`vguide.ceHistoryMode` = `OFF | LATEST | BOUNDED | BOUNDED_WITH_DELTA`
   （對應 issue 的四個 ablation conditions；default OFF 保持現行行為）
9. 驗證不跨 analysis/task 共享（store 是 bridge instance field）

**Out of scope**：舊 LLM predicates 是否進下一輪 context（#8）；無上限 raw logs；
跨 task/run 共享。

## 設計

- `CeHistoryStore`：`record(refinementIndex, structuredCeJson)`（dedup by fingerprint，
  bounded evict）+ `buildContext(mode, currentCe)` → prompt block（entries + optional delta）。
- Entry compact 形式：`loop visits: N12 x5, N15 x3; relations: <…>`（label sorted，
  relations 截斷）。
- Delta：兩個 entry 的 loop-head visits 比較（`N12 visits 5 -> 8`、`new loop head N23 x2`、
  `head gone N12`、`relations changed`）；無差異 → `(no change vs previous round)`。
- Prompt 插入點：`ProposalPromptBuilder` 的 `PRIOR CE HISTORY (read-only):` block，
  在 current CE 之後、budget 之前。
- Dump：schema-5 → **6**（additive）：refinement row 加 `ce_history`
  `[{refinement_index, fingerprint, repeat_count}]` + `ce_history_omitted`。

## 驗收對照

- Round t 看到 current CE + bounded prior summaries/deltas ✅（buildContext 在 record 前呼叫）
- Context 硬上限（4000 chars + 4 entries）✅
- 相同 CE sequence → 相同 history pack（sorted + fixed cap）✅
- Reset/restart 不洩漏（store 隨 bridge 實例消滅）✅
- Ablation 四 mode 可選 ✅；held-out 0-wrong 屬 #2 評估

## 執行

單一 PR（branch `issue5-ce-history`）：store + option → prompt 接線 → dump → docs。
驗證：`ant build-project` + checkstyle + spotbugs + vguide unit tests 全綠；
full JUnit crash list 與 unmodified main 相同（10 個 pre-existing native crashes）。
