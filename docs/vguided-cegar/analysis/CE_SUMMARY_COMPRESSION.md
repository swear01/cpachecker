# CE 摘要：語意壓縮（非字元 cap）

**狀態**：設計（v1.4 `CeSummaryBuilder`）  
**原則**：**先少送、送對、送短格式**；字元 cap 僅作極端 fallback，不作主要手段。

**問題根源**：現行 `summarizeTrace` = `dumpFormula` 整段 SMT（`declare-fun`、`let`、`.def_N`、SSA `@3`）→ median **2772** chars，對 LLM **資訊冗餘、名字錯誤**（應用 source 名寫 predicate）。

---

## 1. 目標：LLM 需要什麼？

| 需要 | 不需要 |
|------|--------|
| 在 **loop head** 上、沿 spurious trace 的 **關係式**（用 **source 變數名**） | 每個中間 block 的完整 VC |
| assertion 相關變量在 CE 上的 **取值/範圍** | `declare-fun`、內部 `.def_*` |
| 相鄰狀態 **變化**（loop 推進） | 與上一 head 重複的 conjunct |
| 與 interpolant **不重複** 的額外約束 | 整段 `precision_local` |

---

## 2. 壓縮管線（建議實作順序）

```
BlockFormulas + trace + loop heads
    → (A) 只選 loop-head blocks
    → (B) 公式 → source 名關係式
    → (C) 去重 / delta
    → (D) assertion 相關優先
    → (E) 格式化輸出
    → ce_summary 字串
```

### (A) 選點：loop-head only（最大瘦身）

- 用 `LoopHeadBlockFormulaIndex.fromTrace` + `pack.loopHeads()`，**只摘要 trace 上的 loop head block**。
- 預設 **最多 4 個 head**（沿 trace 時間序），不是「前 5 個 block index」。
- 可選第 5 點：**assert 前最後一個 block**（若 CFA 可標 `__VERIFIER_assert` 鄰近且不在 loop head）。

**預估**：多數題 1–2 head → 輸出從 5×長 SMT 變 1–2 段。

### (B) 結構化提取：SMT → 關係式（核心）

對每個選中 block 的 `BooleanFormula`：

1. **展開 top-level AND**（`visitAnd` / split conjuncts）。
2. **丟棄** trivial / 內部：`isTrue/isFalse`、純 `.def_N` 定義式（僅為命名）。
3. **變數名**：encoded `|main::i@3|` → contract 左側 **`i`**（`VarContractBuilder.sourceNameFromEncoded`）。
4. **常數**：`(_ bv0 32)` → `0`；大常數保留或 hex 簡寫。
5. **輸出**：與 predicate 同風格的 **prefix 片段**（已是 LLM 輸出格式）：
   ```text
   L@N30: (bvslt i n)  (bvsge i 0)  (= x 0)
   ```
   或更短一行：`L@N30: i<n, i>=0, x=0`（僅當單變數等式/不等式可安全線性化時）。

**實作**：`BooleanFormulaVisitor` 抽 atom；或 `fmgr.dumpFormula` 後 **regex 替換** SSA→source（v1 可先 regex，v2 visitor）。

**不** 送整段 `let`；關係式已是語意內容。

### (C) 去重與 delta

| 技巧 | 範例 |
|------|------|
| **跨 head 去重** | head2 的 `(bvslt i n)` 若已在 head1 → 標 `i<n` 為 **carried**，head2 只列 **新** 關係 |
| **delta 一行** | `i: 0→1→2` 若僅 `i` 的等式在變 |
| **interpolant 合併** | 同 node 的 interpolant 與 block **conjunct 集合比對**；完全子集則 interpolant **不另列** |

### (D) assertion 優先（非 cap）

從 `pack.assertion()` 抽變量名集合 `A`（如 `x`）。

- 每 head **先列** 含 `A` 中變量的關係，再列其它。
- BUG 軌依賴同一 `ce_summary`；profile 文字引導即可，**不必**在摘要裡複製兩份。

### (E) 輸出格式（二選一，實作時定）

**文字（預設，cache 友好）**

```text
SPURIOUS CE (source names only):
  L@N30: (bvslt i n) (= x (_ bv0 32))
  L@N30: i: 0→1        # delta line when only i changes
```

**JSON（與 json_object 一致，略長但結構清晰）**

```json
{"ce_hints":[{"at":"N30","rels":["(bvslt i n)","(= x (_ bv0 32))"],"delta":"i:0→1"}]}
```

Prompt 固定一句：`ce_hints in JSON below` 或嵌入 user 段。Dumper 仍計 char。

---

## 3. 與 `trace_summary` 的重複性（實測）

### 3.1 現行 `trace_summary` 是什麼

`summarizeTrace` = **block index 0..4** 的 `dumpFormula` 全文 + 行首 `block i:`（與 refinements 裡前 5 個 block SMT **幾乎同一回事**）。

v1.3 adaptive dump（113 次 later LLM）：

| 量 | median | max |
|----|--------|-----|
| `prompt_components.trace` | **2772** | **8914** |
| refinements 前 5 block SMT 字元合計 | **2696** | **8838** |
| 兩者比例 block5/trace | **0.973** | 0.944–0.991 |

→ **trace_summary ≈ 前 5 block 完整 SMT**（重複性在「自身定義」上就很高：同一批公式換個標頭）。

### 3.2 `ce_summary` 與 `trace_summary` 會不會重複？

取決於 **ce 送什麼**：

| ce_summary 設計 | 與 trace 重複？ |
|-----------------|----------------|
| 又用 `dumpFormula` 送 **同一批 block 0..4** | **極高（~97%+ 字元）** — 兩段並送無意義 |
| **loop-head only** + 語意 rel（計劃） | **部分重疊**：若 head 落在前 5 block 內，**語意相同但字元少很多**；若 head 在 block 30+，trace **根本沒有** → **互補** |
| **+ interpolants** | **大多不重複**：565 條 itp（前 5），僅 **21** 條與前 5 block SMT 有 substring 重疊 → itp 是 trace **幾乎沒帶** 的資訊 |

**結論**

- **並送** `ce_summary`（完整 dump）+ `trace_summary`：**重複性很高**，應避免。  
- **僅** 語意 `ce_summary`（head + 非重複 itp）、**廢止 trace**：不是「兩份廢話」，而是 **換格式 + 不同選點 + 補 itp**。  
- later 輪若只加 itp 而不改 block 選點，相對 trace 的 **新增資訊主要在 interpolants**，不是 block 公式。

### 3.3 v1.4

| 項 | 決策 |
|----|------|
| `trace_summary` | **廢止** |
| `ce_summary` | 唯一 CE 通道（head rel + 非重複 itp） |

---

## 4. 邊界：語意上限 vs 字元 fallback

| 類型 | 建議 | 理由 |
|------|------|------|
| **語意上限** | max **4** loop heads；每 head max **8** rels；max **3** interpolant 行 | 主控規模；刪的是低優先 **條目**，不砍斷字串 |
| **字元 fallback** | 僅當整段 `ce_summary` &gt; **12000** chars 時觸發；從 **已排序** rel 尾部刪（先非 assertion） | 必須 **設得很高**：現行 trace alone max **8914**；語意壓縮後正常應遠小於此。**fallback 幾乎不應在 217 題上觸發** |
| **單條 SMT 硬切** | **禁止** | 產生不可 parse 碎片 |

fallback 12000 的依據：v1.3 最大 trace 組件 ~8914；預留 head+itp+格式化後仍低於語意上限的題；僅防實作 bug 或未預期公式爆炸。

---

## 5. 預估大小（壓縮後）

| 題型 | 現行 trace chars | 語意壓縮後（估） |
|------|------------------|------------------|
| 簡單 loop（`up`） | ~2772 | **~150–400** |
| 重題（`theatreSquare`） | ~5258 | **~400–900** |
| 極重（`half`） | ~8914 | **~800–1500**（fallback 可能觸發） |

median 預期 **&lt; 600 chars**（遠低於現行 2772）。

---

## 6. 進階（v2，非 v1.4 必做）

| 想法 | 說明 |
|------|------|
| **CE delta since last LLM** | bridge 記上次 CE hash，只送新 head / 新 rel |
| **Model 取值** | 若 block 上可 SAT 取 model，送 `i=3` 而非 `(= i (_ bv3 32))` |
| **Z3 simplify** | `bfmgr.simplify(block)` 再 extract（需測穩定性） |
| **Template 分類** | `i<n` 標 `[guard]`，`x=0` 標 `[assert-var]` 給 BUG 軌 |

---

## 7. 驗收

- `const_1-2`：`ce_summary` 含 `x`/`y` 相關 rel，**無** `declare-fun`  
- `up`：chars **&lt; 500**；cache 前綴（source 段）不變  
- 對照：語意壓縮 vs 舊 trace_full → predicate 品質 / FALSE 指標  

---

## 8. 參考程式

- `LoopHeadBlockFormulaIndex.fromTrace`
- `VarContractBuilder.sourceNameFromEncoded`
- `ContextPackBuilder.summarizeTrace`（將被取代）
