# SVCOMP26 portfolio-level LLM 改進計劃（v1.5.2+）

目標：v1.5.1 已證明「只把 LLM 放進 PredicateCPA refinement」能讓
`svcomp26-vguide` 在 Loops ReachSafety 764 題上從 486 solved 提升到 493 solved。
下一步不只是在 pure CPA solver 裡加 predicate，而是把 svcomp26 視為一個
**portfolio strategy**，探索 LLM 能否介入 portfolio 選擇、資源分配、fallback、hint 產生與
離線策略學習。

本計劃承接：

- [`reports/2026-06-14_svcomp26_vguide_loops.md`](reports/2026-06-14_svcomp26_vguide_loops.md)
- [`reports/2026-06-14_svcomp26_vguide_case_studies.md`](reports/2026-06-14_svcomp26_vguide_case_studies.md)

---

## 0. 重要更正：retry-sensitive 不是 runtime 策略

Case study 中 targeted rerun 顯示 10 個 lost solves 有 5 個在小批次 default rerun 中恢復。
這代表 full-set 結果有 **resource/race sensitivity**，但正式單次執行時沒有「失敗後再 retry」的機會。

因此：

- targeted rerun 只作為**診斷工具**，用來分辨 stable regression vs resource-sensitive loss；
- v1.5.2 的 runtime 改進必須是**單次 execution 內的策略**：更好的 portfolio routing、budget、probe、guard、fallback；
- 報告可以標記 retry-sensitive，但不能把「多跑一次」當成競賽或正式工具能力。

---

## 1. 什麼是 adaptive predicate budget？為什麼說有改進信號？

目前 default VGuide 每次 LLM call 使用固定 predicate budget：

```properties
vguide.minPredicatesPerCall = 3
vguide.maxPredicatesPerCall = 6
vguide.llmMaxCompletionTokens = 1024
```

意思是 prompt 會要求約 3–6 條 predicate，parser 也會在去重後最多保留 6 條。

Adaptive predicate budget 開啟後：

```properties
vguide.enableAdaptivePredicateBudget = true
vguide.llmMaxCompletionTokens = 2048
```

`PredicateBudgetResolver` 會用 ContextPack 算 complexity score：

| 訊號 | 加分直覺 |
|------|----------|
| loop head 數量 | 多 loop → 可能需要更多 predicates |
| assertion 含 `bvand` / `bvurem` / `bvmul` | bitvector / arithmetic 結構較複雜 |
| scalar variable 數量 | 變數多 → 可能需要 relational predicates |
| source 有 array declaration | array/index bounds 可能重要 |
| refinementIndex > 1 | 後續 refinement 通常需要更強 context |

然後分 tier：

| Tier | Score | Budget |
|------|------:|--------|
| low | `<= 3` | 4–8 predicates |
| medium | `<= 6` | 6–12 predicates |
| high | `> 6` | 8–16 predicates |

「有明確改進信號」的意思不是已證明 full-set 必勝，而是小型對照顯示它能救回 default 救不回的題：

| Pool | Setting | Result |
|------|---------|--------|
| 18 個 old v1.4 VGuide-only 但 v1.5.1 未回收題 | `freq12 + adaptive` | 5/18 TRUE |
| 上面 5 題再用 default rerun | default | 只 1/5 TRUE |

其中 `count_by_nondet`、`down`、`functions_1-1`、`up` 在 default rerun 仍 UNKNOWN，
但 adaptive run 變 TRUE。這代表「更大的第一輪 predicate budget / token cap」很可能有實際幫助。
不過它還需要 full-set ablation，因為更大 predicate budget 也可能增加 precision pollution 或 CPU 成本。

---

## 2. LLM 可以介入 portfolio 的哪些層？

svcomp26 不是單一 solver，而是：

```text
SelectionAlgorithm
  └─ RestartAlgorithm
      └─ ParallelAlgorithm
          ├─ symbolicExecution
          ├─ valueAnalysis-Cegar
          ├─ predicateAnalysis
          ├─ dataFlow
          └─ IMC / kInduction
```

v1.5.1 的 LLM 只介入 `predicateAnalysis` refinement。v1.5.2+ 可以探索以下更廣的介入點。

### A. Pre-run portfolio advisor（靜態 routing）

LLM 在 CPA 開跑前讀 source slice / metadata / property，輸出 portfolio 建議：

- singleLoop / multipleLoops / complexLoop 是否維持 heuristicSelection 判斷；
- 是否啟用 VGuide predicate component；
- 是否使用 adaptive predicate budget；
- 是否降低或提高 predicate / symbolic / k-induction 的 thread CPU budget；
- 是否使用 SAFE-only injection 或 full SAFE+BUG injection。

Soundness：LLM 只選 config / resource，不直接給 verdict；底層 CPA component 仍決定 TRUE/FALSE。

研究價值：svcomp26 的 heuristic 是人工規則；LLM 可作為 learned strategy selector，尤其針對
`Loops` 中不同 benchmark family（`nested*`, `in-de*`, `*_valuebound*`, `heapsort`, `mono-crafted*`）。

### B. In-run portfolio manager（單次執行內 probe + switch）

因為沒有 retry，真正可用的是「先用少量 budget 探測，再在同一次 run 內切換策略」。

可能流程：

1. 前 1–3 秒跑 stock portfolio probe 或 cheap static classifier；
2. 收集 telemetry：component 是否快速產生 progress、predicate refinement count、CEGAR rate、k-induction status；
3. LLM / rule-based advisor 決定：
   - 繼續 stock predicate；
   - 切到 VGuide predicate；
   - 開 adaptive budget；
   - 降低 predicate branch，保護 symbolicExecution / k-induction；
   - 對 relation-heavy TRUE 題增加 predicate budget。

這比外部 retry 更符合現實，因為所有選擇都發生在一次 CPAchecker execution 裡。

### C. Resource allocation advisor（portfolio CPU budget）

v1.5.1 lost solves 顯示，有些題不是因為 predicate 給錯答案，而是 shared CPU budget 下 portfolio child
互相影響。LLM 可介入：

- 對 baseline-easy symbolicExecution family，避免 VGuide predicate 消耗太多 CPU；
- 對 interpolation-heavy TRUE family，給 predicate branch 更多 budget；
- 對 complexLoop / k-induction family，完全關閉 VGuide 或只作 diagnostics。

第一版可以不用 LLM runtime，先用 case-study 規則做 config variants：

| Family / signal | Candidate action |
|-----------------|------------------|
| stock predicate historically solves in <= 8 refinements | delay LLM or stock-first |
| first CE has many arithmetic relations / array indices | adaptive budget |
| symbolicExecution near-solved in baseline | reduce VGuide interference |
| complexLoop branch | no VGuide; consider k-induction-specific hints later |

### D. Predicate-quality / injection policy advisor

目前 LLM predicates 都被當成 precision candidates。Portfolio 模式需要更保守：

- SAFE-only injection：BUG prompt 保留給 diagnostics，不直接注入；
- reject mutually exclusive same-variable equalities in the same round；
- reject very large constants unless present in source/assertion/CE；
- down-rank nonlinear bitvector formulas (`bvmul`, `bvurem`, shifts) unless task complexity tier is medium/high；
- prefer loop-head variables and variables present in spurious trace.

這仍是 pure predicate layer，但它的目標是 portfolio-level：減少 precision pollution，保住 baseline solves。

### E. Candidate invariant hints for k-induction / IMC（非 predicate CPA）

目前 VGuide 不介入 k-induction / IMC。可以探索 LLM 產生**候選 invariant**，但必須由 solver 驗證：

- LLM 給 invariant candidate；
- k-induction 或 invariant generator 把它當候選 lemma；
- 只有 base/step 都證明後才用於推理。

Soundness 原則：LLM invariant 不能作為 assumption 直接相信，只能作為待證候選。

這可能對 `complexLoop` 和目前 predicate 無法碰到的 branch 有價值。

### F. Offline family-level hint library（不是 runtime retry）

`Loops` 有很多 family variants：`*_unwindbound*`, `*_valuebound*`, `in-de*`, `mono-crafted*`。
可以用 LLM 離線整理 solved cases 的 predicates，形成 family templates：

```text
family: in-de*
hints: y == n, x == n - y, non-negative counters, bounded z
```

Runtime 時不是 retry，而是根據 filename/source feature 載入 family predicate seeds。這接近 frozen predicates，
但來源是 family-level synthesis，而不是單題 hard-coded replay。

Soundness：作為 predicates / invariant candidates 使用仍由 CPA 驗證；不能作為 assumptions。

### G. Log-to-strategy offline advisor

LLM 還可以用在研究 loop 本身：讀 full-set logs / attribution / dumps，自動提出下一組 config ablation。
這不改善單次 runtime，但能加速找到更好的 portfolio strategy。

---

## 3. v1.5.2 建議優先順序

### P0 — 先做無 Java 或少 Java 的 full-set config ablation

目的：確認 adaptive budget 是否能把 493 推到 500 附近，並觀察 lost solves 是否增加。

Arms：

| Arm | Change | Purpose |
|-----|--------|---------|
| default | v1.5.1 | baseline |
| adaptive-budget | `enableAdaptivePredicateBudget=true`, `llmMaxCompletionTokens=2048` | isolate budget effect |
| freq12-adaptive | adaptive + `llmEveryN=12`, `maxRounds=20` | test later-round opportunity |
| SAFE-only-adaptive | adaptive + do not inject BUG predicates | reduce pollution |

Acceptance:

- 0 wrong verdicts;
- solved > 493;
- lost solves vs svcomp26 fewer than 10, or at least fewer stable lost solves;
- direct LLM wins remain explainable from attribution.

### P1 — Stock-first / delayed-first-LLM guard

Purpose：避免 `nested-3` 這類 stock predicate 很快解掉的題被 first-spurious LLM 改壞。

Candidate runtime rule：

```text
if svcomp portfolio mode:
  run stock predicate refinement for K refinements or T seconds before first LLM
  if stock trajectory looks promising, keep stock
  else enable VGuide/adaptive budget
```

Open design question：K/T 要放在 PredicateCPA 內，還是做成一個 portfolio child pair
`stockPredicate` + `vguidePredicate`？後者較乾淨但 config/CPU budget 更複雜。

### P2 — Portfolio advisor / meta-controller prototype

Purpose：讓 LLM 不只產生 predicates，而是選 strategy。

Minimum viable prototype：

- input：source summary + benchmark family + heuristic branch + cheap static features；
- output：one of `{stock, vguide-default, vguide-adaptive, safe-only, no-vguide}`；
- enforcement：只改 config/options，不直接改 verdict；
- evaluation：先在 764 Loops 做 oracle replay / leave-one-family-out，再決定是否 runtime 化。

### P3 — Candidate invariant hints for non-predicate components

Purpose：打到 predicate CPA 以外的 branch，尤其 complexLoop / k-induction / IMC。

This is higher risk and should wait until P0/P1 clarify easy gains.

---

## 4. Why this is broader than pure CPA solver tuning

Pure predicate tuning asks：

> LLM 能不能給 PredicateCPA 更好的 predicates？

Portfolio-level LLM asks：

> 在 svcomp26 這個多 solver portfolio 中，LLM 能不能決定何時用 predicate、用多少 budget、何時保護
> symbolic/k-induction、何時產生 invariant candidates、何時用 family-level hints？

這是更強的研究方向，因為 svcomp26 的優勢本來就來自 portfolio，而不是單一 CPA。
VGuide v1.5.1 已證明 predicate-level LLM 有正增益；v1.5.2 應該把 LLM 升級為 portfolio advisor。

---

## 5. 更長 horizon：跨 category / domain / artifact

本文件（A–G 層、P0–P3）仍鎖在 **reachability 分支的 predicate / portfolio routing**。
再往外還有整片未開發面：其餘五個 property branch（Termination / MemSafety / NoOverflow /
MemCleanup / DataRace）+ SoftwareSystems、predicate 以外的抽象域、FALSE/counterexample task、
witness artifact、以及離線 corpus 學習。這些屬於 v1.6 → v2.0 → exploratory horizon，
連同 S/R/X soundness 守則與可泛化的 scoped-variant 進場方法，整理在：

- [`LLM_RESEARCH_ROADMAP.md`](LLM_RESEARCH_ROADMAP.md)

其中 **Termination 的 ranking-function 候選**被標為最高槓桿的新 category（驗證最便宜、LLM 最擅長），
建議在 v1.5.2 predicate 層收緊後優先探索。
