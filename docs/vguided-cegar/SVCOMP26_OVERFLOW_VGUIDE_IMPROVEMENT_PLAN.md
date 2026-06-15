# v1.6.1：overflow-vguide 還能往上提升嗎？（config / prompt / workflow 評估 + 計劃）

問題：v1.6 的 overflow 結果（[+6 / 0 lost / 0 wrong](reports/2026-06-15_svcomp26_overflow_vguide.md)）是
**刻意零調參**（純繼承 reachability 的 config/prompt）。本文件評估「reachability-tuned 的 config/prompt/workflow
對 overflow 是不是最好的」，並計劃可行的提升。承接 [`SVCOMP26_OVERFLOW_VGUIDE_PLAN.md`](SVCOMP26_OVERFLOW_VGUIDE_PLAN.md)。

---

## 1. Data-grounded headroom（挖 L3 的 452 題 vguide log）

| 類別 | 題數 | 意義 |
|------|-----:|------|
| fired + solved | 54 | vguide fire 且解掉（含 6 個 net-new）|
| **fired + UNKNOWN** | **37** | **fire 了但沒關掉 proof → 可提升的主要目標** |
| never fired + solved | 309 | value child / 平凡，vguide 沒參與 |
| never fired + UNKNOWN | 52 | 沒 fire（NO_SPURIOUS）；vguide 沒機會 |

- **91 題 fire，只有 59% 解掉** → 41%（37 題）fire 後失敗。
- **llm_rounds = {1:90, 2:1}**：幾乎全部只 fire 一次。`maxLlmRoundsPerAnalysis=5` 形同虛設
  （分析很少拿到第二次 spurious 機會）→ **multi-round 是死 lever**。
- **注入 predicate 數：median 8、max 24**（已超過 default `maxPredicatesPerCall=6`）；`nestedLoop-2` 注入 **24** 仍 UNKNOWN
  → **失敗是 predicate 品質問題，不是數量問題**。37 個 fired-but-UNKNOWN 多是 invariant-generation 難題
  （AliasDarteFeautrierGonnord-SAS2010-*、McCarthy91…）。

## 2. 關鍵發現：現在的 prompt 對 overflow 是「反向調校」的

`ProposalPromptBuilder.java`（prompt 寫死在 Java、**property-agnostic**、只有 SAFE / BUG_HUNT 兩 profile）。
SAFE profile 的 budget 指示寫著：

```
- Do NOT pad to N with obvious bounds (e.g. i>=0 in for(i=0;...)) or near-duplicate inequalities.
```

這是 **reachability 思維**（reachability proof 不缺 `i>=0` 這種 trivial bound）。但對 **no-overflow** 而言，
**非負（`x>=0`）與 range bound（`x<=INT_MAX`）正是證明本體**——v1.6 的 wins 注入的就是
`sign-bit(x)≠1`（x≥0）、`x ≤ 2^30−1`。**現在的 prompt 主動勸退 overflow 最需要的 predicate。**

→ 結論：**config/prompt 對 overflow 不是最好的**。prompt 是最大、且方向明確的提升 lever。

---

## 3. 提升 levers（依成本排序）

### P0 — config-only 快測（先做，零 Java）

| Arm | 改動 | 假設 | Tier |
|-----|------|------|------|
| `safe-only` | `vguide.dualPromptMode=false` | overflow wins 全是 TRUE/SAFE；BUG predicate 是 pollution（FALSE 159→159，BUG 沒在幫 FALSE）| R |
| `adaptive` | `vguide.enableAdaptivePredicateBudget=true` + `llmMaxCompletionTokens=2048` | 弱 lever（median 已 8），但免費；bitvector 複雜度高 → tier 升 | R |

成本低，**先在 143 題（91 fired ∪ 52 never-fired）子集**跑兩 arm，看 solved delta + 0 wrong，再決定是否 full。
預期：safe-only 小幅正向或中性；adaptive 大概率中性（數量非瓶頸）。**P0 主要是排除法**：證明「光調 config 救不了那 37 題」。

### P1 — overflow-aware prompt（Java，真正的 lever）

針對第 2 節：讓 prompt property-aware。最小可行改動：

1. 把 property/spec 類型 plumb 進 `ContextPack`（查 `ContextPackBuilder` 是否已帶；沒有就從 spec 傳入一個 enum）。
2. `ProposalPromptBuilder` 對 overflow：
   - 明說目標：「prove **no signed integer overflow**」。
   - **反轉 anti-bound 規則**：鼓勵 range / 非負 / 每個算術運算 operand 的 bound（`INT_MIN ≤ e ≤ INT_MAX`）。
   - 提示哪些算術運算可能 overflow（從 CE summary / source）。
3. 不動 reachability path（只在 property=overflow 時換 SAFE 指示）。

**目標**：把 37 個 fired-but-UNKNOWN 轉一部分成 solved。這是直接打 predicate-品質 失敗模式。
Java 改動範圍小（一個 property enum + 一段 overflow SAFE 文案 + 分支），不碰 refiner / soundness 路徑。

### P2 — workflow：300s 競賽級確認（正交，「鞏固」用）

兩 arm 在 **300s**（非 120s）重跑 full scalar，得可投稿硬數字。不是 vguide 提升，是把 +6 的 claim 補強到 competition timing。

### P3 —（低優先 / 投機）救 never-fired 52 題

這些沒 fire（NO_SPURIOUS）。可試 startup-seed（first refinement 前先注入候選 bound）給 vguide 機會，
但有 precision pollution 風險，且可能傷 0-lost。**先不做**，等 P0/P1 結果。

---

## 4. 建議順序與 acceptance

1. **P0**（半天內）：143-題子集跑 safe-only / adaptive，確認 (a) 0 wrong (b) 是否有 solved 增益。
   - 若某 arm 有穩定增益 → 納入 default，full-set 確認。
   - 若皆中性（預期）→ 正式排除 config-only，進 P1。
2. **P1**（prompt Java）：實作 overflow-aware SAFE 文案 → 143-題子集 A/B（reachability-prompt vs overflow-prompt）→
   **acceptance：0 wrong、fired-but-UNKNOWN 減少、無 regression（0 new lost）** → full scalar 重測 → 更新 report。
3. **P2**：最後做 300s full 兩 arm，產出 competition-grade 數字。

**硬 gate（每階段）**：0 wrong verdict（overflow FALSE 題多，最關鍵）；不得新增 stable lost solves。

---

## 5. 風險

| 風險 | 緩解 |
|------|------|
| overflow-aware prompt 反而 over-produce trivial bounds → precision pollution → lost solves | 143-題子集先驗 0-lost；保留「non-trivial」要求，只是**允許** bounds 而非強制 |
| 改 prompt 影響 reachability path | property 分支：只在 overflow 換文案，reachability 文案逐字不動；跑一次 reachability 子集回歸 |
| adaptive budget 增 CPU → portfolio 內 starve 別的 child | 監看 wall；overflow 是 2-way（predicate vs value），壓力小於 reachability 5-way |
| 樣本小（37 題目標）→ 增益個位數 | 接受：overflow 本來 UNKNOWN 基數就小（89）；目標是把 fire 的轉化率從 59% 拉高，不是大躍進 |

---

## 6. 一句話

現在的 config 對 overflow「堪用但非最佳」，**真正的瓶頸是 reachability-tuned 的 prompt 主動勸退 overflow 需要的 bound predicate**。
最高槓桿是 P1（overflow-aware prompt，小範圍 Java）；P0 先用 config 排除法、P2 補競賽級數字。

## 7. 實作狀態

| 項目 | 狀態 |
|------|------|
| L3 headroom 分析（91 fired / 37 target / quality-not-quantity / multi-round dead）| **DONE**（§1）|
| prompt 反向調校發現 | **DONE**（§2）|
| P0 config 實驗（adaptive budget, full 452）| **DONE → +1**（只 `Avery-FLOPS2006-Table1`，0 regr / 0 wrong）→ **config 確認非 lever**（quality-not-quantity 成立）|
| P1 overflow-aware prompt（Java）| **實作完成、build SUCCESSFUL、1-題 sanity 過**（dump prompt 確含 overflow 文案）；91-fired A/B 進行中 |
| P2 300s 確認 | TODO |

> **基準數字更正**：v1.6 topline 原報 stock 314 / vguide 320 是 basename-keyed 分析少算（跨目錄同檔名碰撞）。
> full-path 重算為 **stock 357 / vguide 363**；**+6 / 0 lost / 0 wrong / 6 new solves 不變**。§1 的 91 fired / 37 target
> 是逐 log 統計（無 dedup），不受影響。
