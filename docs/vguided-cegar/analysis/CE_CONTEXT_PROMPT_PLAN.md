# CE 摘要進 Prompt（併入 v1.4）

**狀態**：計劃（未實作）  
**壓縮設計**：[CE_SUMMARY_COMPRESSION.md](CE_SUMMARY_COMPRESSION.md)（**語意壓縮，非字元 cap**）  
**總覽**：[DUAL_PROMPT_V1_PLAN.md](DUAL_PROMPT_V1_PLAN.md)

---

## 1. 動機

| 現況 | 問題 |
|------|------|
| first 輪無 CE | 只靠 source |
| later `trace_summary` | 完整 SMT，median **2772** chars |
| 名字 | SSA / `.def_N` 與 predicate 用的 source 名不一致 |

---

## 2. `ce_summary`（`CeSummaryBuilder`）

見 [CE_SUMMARY_COMPRESSION.md](CE_SUMMARY_COMPRESSION.md) 管線 **(A–E)**。

要點：

- loop-head blocks + 非重複 interpolants  
- **不**送 raw `dumpFormula` 整段  
- **不**再附 `trace_summary`

---

## 3. Prompt 位置

`user dynamic`（source + profile 之後，budget 之前）：

```text
SPURIOUS CE SUMMARY (source variable names only):
{ce_summary}
```

SAFE / BUG **共用同一字串**。

---

## 4. Dumper

`prompt_components.ce_summary`；later 輪 `trace` = **0**。

---

## 5. 驗收

- `const_1-2`：含 `x` 相關 rel；BUG 軌出 violation 謂詞  
- `ce_summary` median chars **&lt; 600**；無 `declare-fun`  
- 相較 v1.3 trace_full：**更小且更可讀**
