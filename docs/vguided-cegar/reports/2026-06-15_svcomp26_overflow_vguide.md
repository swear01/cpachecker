# svcomp26-overflow-vguide：v1.6 Class-A 泛化結果（2026-06-15）

第一次測試 reachability 的 predicate-CEGAR VGuide hook 能否泛化到第二個 SV-COMP property branch（NoOverflow）。
計劃見 [`../SVCOMP26_OVERFLOW_VGUIDE_PLAN.md`](../SVCOMP26_OVERFLOW_VGUIDE_PLAN.md)；
為何 Overflow 是唯一 Class-A（config-only）見 [`../LLM_RESEARCH_ROADMAP.md`](../LLM_RESEARCH_ROADMAP.md) §4.2。

**結論：泛化成立，且乾淨——零 Java、零 prompt 改動，+6 sound net-new、0 regression。**

## Summary

```text
set:        no_overflow_scalar（452 題 = NoOverflows-{BitVectors,Other} ∩ no-overflow.prp）
config:     只在 overflow predicate 元件 flip cpa.predicate.refinement.useVocabularyGuide=true
timelimit:  120s，parallel 6，heap 4000M，兩 arm 完全相同
```

| Arm | TRUE | FALSE | UNKNOWN | Solved | Wrong |
|-----|-----:|------:|--------:|-------:|------:|
| `svcomp26-overflow`（stock） | 155 | 159 | 95 | 314 | **0** |
| **`svcomp26-overflow-vguide`** | **161** | 159 | 89 | **320** | **0** |

Delta：**+6 solved / 6 new / 0 lost / 0 wrong**。
是 stock 的 **strict superset**（無任何 regression）——比 reachability v1.5.1 更乾淨（那次有 10 lost）。
6 個 new solves 全部 TRUE 且 direct LLM-decided。

## 為什麼這是「便宜的泛化」（Class-A）

overflow 的 predicate 元件 `config/components/predicateAnalysis--overflow.properties` `#include` 的是
**與 reachability vguide 同一顆** `predicateAnalysis-PredAbsRefiner-ABEl.properties` refiner，正是 VGuide hook
（`PredicateCPARefinerFactory` 讀 `cpa.predicate.refinement.useVocabularyGuide`）落點。所以 flip 一個 option 就生效，零 Java。

## Soundness（gate）

- **0 wrong 兩 arm**：逐題對 `.yml` 的 `expected_verdict` 掃，無 TRUE/FALSE 誤判。
- FALSE 數不變（159→159）：vguide 注入的 predicate 從未翻掉任何 FALSE 題。
- recursion → BAM fallback（vguide off）、無 crash（見 plan §11 smoke D）。
- Tier S 成立：spurious predicate 只浪費 work，不會產生錯 verdict。

## 6 個 direct LLM wins

每題：stock UNKNOWN（120s timeout）→ vguide **1 refinement、~4–6s** 解 TRUE，deciding = vguide predicate child，`llm_rounds=1`。

| Task | stock | vguide | refs | wall | preds |
|------|-------|--------|-----:|-----:|------:|
| `Cairo_step2-1` | UNKNOWN | TRUE | 1 | 4.7s | 6 |
| `PodelskiRybalchenko-LICS2004-Fig1` | UNKNOWN | TRUE | 1 | 5.7s | 14 |
| `benchmark17_conjunctive` | UNKNOWN | TRUE | 1 | 3.8s | 7 |
| `benchmark18_conjunctive` | UNKNOWN | TRUE | 1 | 4.0s | 9 |
| `benchmark23_conjunctive` | UNKNOWN | TRUE | 1 | 4.9s | – |
| `benchmark34_conjunctive` | UNKNOWN | TRUE | 1 | 6.3s | – |

## Predicate evidence：LLM 給的是 overflow-相關 facts

即使 prompt 沒為 overflow 改過，注入的 predicate 正是 overflow-avoidance 需要的 **bound + 非負**：

`PodelskiRybalchenko-LICS2004-Fig1`（14 條）：
```text
sign-bit(x) ≠ 1            →  x ≥ 0           （非負）
x ≤ 1073741823 (= 2^30−1)                      （壓在 INT_MAX 之下避免 overflow）
y < x                                          （loop relation）
```
`Cairo_step2-1`：`x ≥ 0`、`x < 2`、`x == 0`。
`benchmark17/18`：`i < n`、`k == i`、非負 sign-bit。

這直接解掉 plan §9 的「prompt 適配」風險：**config-only 就夠**，spurious-CE 驅動的 predicate 對 no-overflow 夠 property-agnostic。

## Attribution

6 個 win 全部 `deciding_component = svcomp26-overflow-vguide--predicateAnalysis--overflow.properties`
（`… finished successfully.`）**且** `llm_rounds = 1`。portfolio 確實路由到 vguide predicate child 且由它決定，贏過 value-analysis。
（`attribute_svcomp_verdicts.py` 的 `verdict`/`deciding_component`/`llm_rounds` 對 overflow 直接可用；
`selection_branch`/`restart_stage` 是 reachability 專用，對 overflow 回 `unknown`，如預期。）

## Smoke 梯（full-set 前的驗證，見 plan §5/§11）

L0 隔離 fire ✓；L1 portfolio routing：fire 且 predicate child 決定（4/4）✓；C FALSE 0-wrong ✓；D recursion BAM fallback 無 crash ✓。

## Caveats

- **timelimit 120s**（非競賽 300s）；兩 arm 相同，所以 +6 的 delta 仍是有效泛化信號。300s 會讓兩 arm 絕對 solved 都上升。
- pilot（signedintegeroverflow-regression，straight-line）fire 0——vguide 只在需要非平凡 predicate refinement 的題（loop）才介入；對 straight-line overflow 檢查不 fire 也不需要。
- 單一 Class-A branch、單一 timelimit；非 SV-COMP submission。

## 結論 → roadmap

Class-A 泛化（roadmap §4.2）**實證確認**：reachability 的 predicate-CEGAR LLM hook 零 Java/零 prompt 改動轉移到 NoOverflow，
得 **+6 sound net-new、0 regression**。roadmap §1 的 verified-candidate 角色與 §4 的 hook-inheritance feasibility 模型獲驗證。

下一步：termination 的 **safety-reduction 路**（terminationToSafety 走 PredicateCPA）是下一個 Class-A 候選；
**lasso/ranking-function 路是 Class-B**（要新 injection hook），留給 v2.0。
