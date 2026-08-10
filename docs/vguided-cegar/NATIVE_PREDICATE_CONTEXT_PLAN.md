# Native CEGAR Predicate Context — Implementation Plan (Issue #6)

> Status: implementing. 對應 [Issue #6](https://github.com/swear01/cpachecker/issues/6)
> （epic #11 Phase 1）。依賴 #1/#3/#4/#5 已完成。

## Goal 與 Scope

把 **current native CEGAR predicate precision** 作為 read-only context 提供給 LLM，
避免重複提案、被支配候選、或無法理解抽象缺少什麼。LLM-owned predicates 分開追蹤，
不偽裝為 native。

**In scope（checklist）**
1. 盤點 PredicatePrecision API：`getGlobalPredicates()` / `getFunctionPredicates()` /
   `getLocalPredicates()`；atom = `AbstractionPredicate.getSymbolicAtom()` ✅
2. Ownership model：bridge 記錄每次 LLM injection 的 `local N<num>|<canonical smt>` keys；
   extractor 以此 split origin = `native` | `llm`（frozen seeds 在 analysis end 才注入，
   不影響後續 rounds，不需追蹤）
3. Canonical deterministic serializer：`fmgr.dumpFormula(atom)` + scope-tagged entries，
   (scope, smt) dedup + sort
4. Relevance：global + loop-head-owning functions + loop-head locals；selection rule 記錄
5. Token cap：40 predicates / 3000 chars，omitted 計數可觀察（不靜默丟棄）
6. ContextPack/prompt 接入：`NATIVE CEGAR PRECISION (read-only):` block（CE 與 history 之後）
7. Dump：schema-6 → **7**（additive）`native_predicate_context`
   {selection_rule, omitted, predicates:[{scope, origin, smt}]}
8. Ablation：`vguide.nativePredicateContext`（default false）= no-predicate-context vs
   native-predicate-context
9. 隔離：llmOwnedKeys 與 extractor 都是 bridge instance field；每輪讀 current precision

**Out of scope**：移除 active precision 中的舊 LLM predicates（#8）；完整 SMT internal dump。

## 驗收對照

- Context 每個 predicate 可追溯到當前 PredicatePrecision + origin ✅
- Native vs LLM 不混淆 ✅（origin tag + llmOwnedKeys）
- 相同 precision/state → deterministic context ✅
- Token cap 不靜默丟棄；omitted/selection_rule 可觀察 ✅
- 不修改 predicate 語意、context exposure 不作 validation ✅
- Ablation 報告屬 #2 core-only 評估

## 執行

單一 PR（branch `issue6-native-predicate-context`）：builder → option → bridge 接線 →
prompt → dump → docs。驗證：`ant build-project` + checkstyle + spotbugs + vguide tests 全綠；
full JUnit crash list 與 unmodified main 相同。
