# LLM Predicate Lifecycle — Implementation Plan (Issue #8)

> Status: implementing. 對應 [Issue #8](https://github.com/swear01/cpachecker/issues/8)
> （epic #11 Phase 1）。依賴 #1/#3/#4/#5/#6/#7 已完成。

## Goal 與 Scope

每次新 LLM round 生效時，從 active precision 移除上一輪 LLM-owned predicates，再注入
本輪 validated candidates：

```
P_active(t) = P_native_CEGAR(t) ∪ P_LLM(t)      （而非累積 ⋃ P_LLM(i)）
```

**In scope（checklist）**
1. Ownership 追蹤：bridge 的 `llmOwnedKeys`（canonical `local N<num>|<smt>`，由
   `llmOwnedKey()` helper 統一）— 與 #6 的 origin split 共用
2. Precision removal 語意：`PredicatePrecision` immutable + **public ctor** → 過濾
   local multimap 重建 filtered precision，`updatePrecisionGlobally` 一次原子套用；
   既有 ARG states 保留舊 abstraction（standard precision-update 語意），後續
   refinement 使用 filtered precision
3. Round transaction：remove old → preserve native → inject new（一個 immutable rebuild
   + 一次 global update；無 partial state）
4. 空新批次：LLM round fired 但無 validated predicates → 仍移除上一輪（transaction
   語意明確）；LLM 未 fired 的 round 不動 precision
5. Dump：schema-8 → **9**（additive）`llm_precision_replaced` + `llm_precision_removed`
6. Ablation：`vguide.replaceLlmPredicates`（default false = cumulative 現行行為）
7. C0/C1 context policy：C0 = `nativePredicateContext` off；C1 = on（#6 的 origin=llm
   標記即 historical metadata）— 兩者獨立於 active-precision 語意
8. source-prior：pre-CEGAR 注入的 predicates 在 analysis 開始前就進 initial
   precision；若後續 LLM rounds replace，source-prior 的 keys 也在 `llmOwnedKeys`？
   —— source-prior 路徑目前不記錄 keys（preCegarValidated 走 mergePreCegarInto）。
   決定：**source-prior predicates 不算 replaceable LLM-owned set**（documented，
   避免誤刪 initial precision）
9. **frozen / test-only ownership 標記（issue #37）**：frozen seeds 在 analysis end 才
   注入（不影響後續 rounds），test-only predicates 不進 active precision — 兩者都不在
   `llmOwnedKeys`，且 dump 的 `llm_precision_removed/retained` 只反映
   replaceable set；此標記為顯式設計決定，非疏漏。removal 的 regression test 卡在
   `AbstractionPredicate` 無法在 unit test 中建構（package-private ctor + Region
   依賴）——待測試 seam（如 predicate 字串層的 filter 函式）後補。

**Out of scope**：frozen seeds（analysis end 注入，不影響後續 rounds）；replay
predicates（同 injection 路徑，自動納入 keys）。

## 驗收對照

- 每個移除/注入可追溯到 ownership key + round ✅
- Native 保留、LLM 替換 ✅
- 失敗不留 partial state（immutable rebuild + 單次 update）✅
- 空批次語意明確 ✅
- Dump 記錄 added/removed ✅（`llm_precision_removed` + validated/injected counts）
- Cumulative-vs-replacement ablation（option）✅
- C0/C1 不混淆 ✅

## 執行

單一 PR（branch `issue8-llm-predicate-lifecycle`）。驗證：`ant build-project` + checkstyle
+ spotbugs + vguide tests 全綠；full JUnit crash list 與 unmodified main 相同。
