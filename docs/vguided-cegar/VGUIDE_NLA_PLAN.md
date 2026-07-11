# VGuide-NLA：兩批完成計畫

**狀態：STOP after final PDR/KI-PDR consumer-capacity gate（2026-07-11）**

> Result：12-task exact-BV/MathSAT stock 0/12、oracle 0/12 @60s；`ps2-ll` oracle
> @300s仍 UNKNOWN。相容 Z3 4.15.4 runtime安裝後，exact NIA/Z3亦為 stock 0/12、
> oracle 0/12 @60s。這已停止 ordinary incremental k-induction generator；尚未排除
> mutually-inductive per-location conjunction與 direct PDR CTI abstraction/frame learning。最後一次
> consumer matrix也為all oracle delta 0；詳見
> [`reports/2026-07-11_nla_oracle_capacity_smoke.md`](reports/2026-07-11_nla_oracle_capacity_smoke.md)。

## 1. 研究決定

下一條主線是 **CTI-conditioned polynomial search-space synthesis for k-induction**：LLM
只選變數、monomial basis、degree 與 recurrence/template 結構；係數由 deterministic
backend 求解；候選 invariant 必須通過 CPAchecker 既有 bounded base check 與
`KInductionProver` 才能影響證明。LLM、sample fitting 或外部 algebra tool 都不能直接決定
verdict。

Ordinary k-induction、per-loop conjunctive candidate、KI-PDR與direct PDR root／abstraction
vocabulary皆已停止。Final matrix不呼叫LLM且all oracle delta 0，因此不實作CTI helper；現轉
convergence-aware predicate usefulness gating。

## 2. 為什麼是這條線

- 既有 ReachSafety cheap levers 已用盡；剩餘 UNKNOWN 的最大可辨識群是 nonlinear
  arithmetic。
- CPAchecker 已有 `CandidateGenerator`、`SingleLocationFormulaInvariant`、predicate-precision
  candidate import、bounded base check 與 `KInductionProver`；第一批可先走既有路徑，不改
  BMC core。
- 真正可檢驗的新命題不是「LLM 會寫 invariant」，而是「verification-state-conditioned
  LLM 能否比 deterministic enumeration 更有效地縮小 polynomial search space」。
- 若正確 polynomial invariant 仍無法被現有 engine 證明，應立刻停止；這代表缺的是新的
  nonlinear backend，不是更多 LLM prompting。

## 3. 唯一斷點：修改 BMC core 之前

整個工作只分兩個 execution batch。唯一人工停下來重新判斷的斷點位於 **Batch 1 完成、
Batch 2 修改 `AbstractBMCAlgorithm` / `KInductionProver` 之前**。

這個斷點同時回答兩個問題：

1. **Engine capacity**：給正確 polynomial invariant，CPAchecker 能否證明？
2. **LLM necessity**：相同 coefficient/proof backend 下，LLM basis 是否勝過 deterministic
   basis？

斷點判定：

| 結果 | 決策 |
|------|------|
| Oracle/reference candidate 在 12-task smoke 至少新增 4 solve，且 60-task frozen set 上 CTI-LLM 至少新增 8 solve、比最佳 deterministic arm 多至少 4 | **GO：直接進 Batch 2** |
| Oracle 有效但 LLM 不勝 deterministic | **STOP LLM claim**；保留 deterministic NLA 結果，不改 BMC core |
| Oracle 在 12-task smoke 新增少於 4 solve | **STOP VGuide-NLA**；瓶頸是 proof backend/semantics，轉 predicate usefulness gating |

所有 GO 結果還必須滿足：0 wrong、stock-solved controls 最多 2 lost、沒有以 benchmark
family/name 或 expected verdict 作 runtime signal。

## 4. Execution Batch 1：一次完成 capacity、baseline、LLM necessity

### B1.1 凍結資料與 provenance

從既有 Loops 764 manifest 與 stock results 產生：

- `nla_oracle_smoke.list`：12 個不同 recurrence/polynomial pattern 的 expected-TRUE 代表題；
- `nla_capacity_dev.list`：family-separated development set；
- `nla_capacity_holdout.list`：60 個 expected-TRUE、stock-UNKNOWN、family-held-out tasks；
- `nla_regression_controls.list`：expected-FALSE nonlinear + stock-solved controls。

每個 manifest 記錄 source/YAML content hash。每個 run 記錄 commit、JAR/build hash、expanded
config、solver、machine model、CPU/wall/memory、API response hash 與 task order。experiment groups
必須 sequential 執行，不能讓不同 arms 同時競爭主機資源。

### B1.2 不改 core 的 oracle-capacity harness

**完成（2026-07-11）。** TDD harness、12-task frozen catalog、atomic/supporting-first/
conjunction、runner/provenance與 current-commit實跑已完成。BV backend 0/12；修復相容
Z3 runtime後 exact NIA/Z3仍為 0/12。科學判定為 RED。

使用既有：

```text
bmc.kinduction.predicatePrecisionFile
PredicateToKInductionInvariantConverter
StaticCandidateProvider.suggestCandidates(...)
SingleLocationFormulaInvariant
KInductionProver.check(...)
```

先在 12-task smoke 餵 reference/oracle polynomial candidates；同時測 atomic、supporting-first
與 conjunction 形式，避免把 candidate dependency 誤判成 engine 無能力。記錄 parse、base、step、
solver UNKNOWN/timeout、C/bit-vector semantics mismatch 與 target insufficiency。

### B1.3 共用 deterministic coefficient backend（取消）

建立一條離線 prototype：canonical exponent vector → monomial matrix → exact rational/integer
nullspace → gcd/sign normalization → sparsity rank → predicate-precision candidate → k-induction。

所有 arms 共用同一 backend、candidate budget、timelimit 與 proof path。第一版 degree ≤ 3、
最多 4 variables、16 monomials、3 conjuncts；不處理 pointer/array/string/float/recursion。

### B1.4 必須比較的 arms（取消）

1. stock standalone k-induction；
2. deterministic all-monomials degree ≤ 2；
3. deterministic all-monomials degree ≤ 3；
4. property-directed basis；
5. recurrence/update-derived basis；
6. source-only LLM basis；
7. CTI/verification-state-conditioned LLM basis；
8. oracle/reference candidates（capacity upper bound，不計方法成績）。

LLM 只能輸出 loop head、variables、monomials、relation kind 與 budget；不能輸出 verdict，
也不能讓未證明公式成為 assumption。

### B1.5 Batch 1 產物（未繼續）

- frozen manifests；
- oracle candidate corpus；
- deterministic coefficient prototype 與 tests；
- LLM basis schema/parser 與 cached responses；
- per-task funnel：proposed → synthesized → base-pass → step-pass → proof-used；
- 一份斷點報告，明確 GO 或 STOP。

## 5. Execution Batch 2：取消

只有斷點 GO 才做；oracle gate為 0/12，因此以下項目不執行。

### B2.1 Dynamic integration

新增 `core/algorithm/bmc/vguide/`，核心是 dynamic `CandidateGenerator`。最小修改：

- `BMCAlgorithm.getCandidateInvariants()`：組合 target candidate 與 VGuide-NLA generator；
- `AbstractBMCAlgorithm.checkStepCase()`：induction 失敗後傳 immutable feedback；
- 優先重用 `InductionResult.getBadStateBlockingClauses()`；只有不足時才擴充 CTI representation；
- stock-first：stock step case 先失敗，NLA feature gate 才允許一次 LLM round；
- 每 loop 最多 1 call、1–3 candidates；parse/fit/base/step/solver/API failure 全部 fail closed。

最終 formula 以 `SingleLocationFormulaInvariant` 交給既有 base + k-induction path；只有
confirmed candidate 可支援 target proof。

### B2.2 驗證

- unit tests：schema、degree/scope/type、canonicalization、coefficient normalization、dedup、
  timeout/UNKNOWN、cache、shutdown、malformed/hallucinated output；
- end-to-end：cubic/quadratic/finite-difference、nested loop、signed overflow、unsafe control、
  mathematical-integer-correct but bit-vector-invalid；
- soundness gate：0 wrong；false/unproved candidates 不得被 confirm；API/CAS failure 不得改 verdict。

### B2.3 決定性評估

先跑 frozen 180-task suite（120 TRUE nonlinear stock-UNKNOWN + 30 FALSE controls + 30
stock-solved controls），再跑完整 Loops 764 portfolio。主要報 solved、new/lost/wrong、PAR-2、
family-held-out、proof-dependent wins、solver failure、API cost 與 end-to-end overhead。

成功門檻至少滿足一項：

- 完整 764：+15 至 +20 net、0 wrong、lost ≤ 1%、PAR-2 不惡化；或
- family-held-out TRUE-NLA：UNKNOWN 減少至少 20%，勝過最佳 deterministic baseline，且完整
  portfolio 無顯著 regression。

### B2.4 Batch 2 產物

- production dynamic hook、configs、tests；
- frozen 180 + full-764 raw per-task outputs；
- exact expanded configs、build hashes、cached responses；
- offline reproduction 從 per-task data 重算，不再只比 hard-coded summary；
- report/paper 更新與 conservative claims。

## 6. 第一個要執行的步驟

**先建立 12-task oracle-capacity harness，走
`bmc.kinduction.predicatePrecisionFile` → `PredicateToKInductionInvariantConverter` →
`KInductionProver` 的現成路徑。**

理由：這是整個方向唯一不可由更多 coding 補救的前提。若正確 polynomial invariant 都無法在
現有 C/bit-vector semantics 與 solver budget 下被證明，dynamic LLM hook、CTI API、prompt 與
coefficient backend 都沒有研究價值。反之，只要這條現成路徑能穩定產生 direct wins，就能在同一
個 Batch 1 立即接 deterministic 與 LLM basis arms，無需再停。

## 7. Fallback

斷點 STOP 時轉向 **convergence-aware predicate usefulness gating**：用 refinement slope、
loop-head visits、predicate overlap/consistency、formula size 與 SMT-time growth 預測 injection
pollution；目標是保留 `peel=0` portfolio gains 並消除 isolated regressions。不要再做純 prompt
或 fixed-threshold tuning。
