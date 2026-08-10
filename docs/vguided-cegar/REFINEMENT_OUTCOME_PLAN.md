# Refinement Outcomes Context — Implementation Plan (Issue #7)

> Status: implementing. 對應 [Issue #7](https://github.com/swear01/cpachecker/issues/7)
> （epic #11 Phase 1）。依賴 #1/#3/#4/#5 已完成。

## Goal 與 Scope

把可權威取得的 CEGAR refinement outcomes 跨輪暴露給 LLM，讓模型分辨 successful
generalization、單純 loop peeling、non-progress 與 candidate rejection；不可取得的欄位
標記 unavailable，不推測。

**In scope（checklist，以 bridge hook 可取得的 authoritative artifacts 為限）**
1. 盤點：`CounterexampleTraceInfo` 只有 isSpurious + interpolants；refiner status 不傳給
   bridge；ARG prune metadata 不可得 → 這些標 unavailable
2. `RefinementOutcomeStore`：兩階段記錄（round start: visits/itp/blocks；LLM fired:
   validated/injected/rejected；round complete: native precision delta）
3. Native vs LLM outcome 分離：LLM outcome 是 bridge 自身狀態；native delta 在 LLM
   injection **之前**計算（precision canonical set difference before/after）
4. Progress indicators：loop-head visits 標 `[heuristic]`；native_delta 是 authoritative
5. Bounded：最近 4 rounds，oldest-first eviction，omitted 可觀察
6. ContextPack/prompt：`REFINEMENT PROGRESS (read-only):` block
7. Dump：schema-6 → **8**（additive）`refinement_outcome`（compact line）+
   `refinement_outcome_unavailable`
8. Ablation：`vguide.refinementOutcomeContext`（default false）
9. 隔離：store 是 bridge instance field；每 round 重新計算

**Out of scope**：infeasible prefix/suffix/pivot（API 不可得）；refiner status；
ARG prune/restart metadata；portfolio outcomes。

## 驗收對照

- 每個 exposed outcome 可追溯到 refinement round + CPAchecker artifact ✅
- Native vs LLM outcome 分離 ✅
- Progress indicators：heuristic 標記 ✅
- Bounded + omitted 可觀察 ✅
- 缺失欄位標 unavailable，不推測 ✅
- Ablation 屬 #2 評估

## 執行

單一 PR（branch `issue7-refinement-outcomes`）。驗證：`ant build-project` + checkstyle +
spotbugs + vguide tests 全綠；full JUnit crash list 與 unmodified main 相同。
