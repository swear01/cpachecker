# Frozen Predicates（透明 Replay 替代方案）

取代 `VGUIDE_LLM_RECORD` / `VGUIDE_LLM_REPLAY` hash cache。所有內容 **可讀、可 diff、可 cite**，適合論文與 advisor。

## 術語

| 術語 | 定義 |
|------|------|
| **NO_SPURIOUS** | 時限內 **0 次** predicate refinement → LLM **不觸發** |
| **FIRST_SPURIOUS_OK** | ≥1 次 refinement → 可進入 LLM 主路徑 |
| **FROZEN_SEED** | NO_SPURIOUS 時讀 `predicate_sets/`，不 call API |

Legacy 20 題池統計見本機 `archive/vguided-docs/evaluation/NO_SPURIOUS_STATISTICS.md`。

## 目錄

```
docs/vguided-cegar/predicate_sets/<benchmark>.md
```

每檔建議包含：

1. **benchmark** 名稱與 SV-COMP 路徑  
2. **commit** 驗證時的 git hash（可選）  
3. **loop_heads**（`N19` 等，來自 CFA dump）  
4. **predicates** 列表（source-level SMT 字串）  
5. **run outcome**（TRUE / UNKNOWN，refs）  
6. **notes**（例如 string_concat 需固定 predicate 才 3/3）

範例見 [predicate_sets/up.md](../predicate_sets/up.md)。

## 注入格式（機器可讀，可選）

另可提供同名的 `.json`（由工具從 md 產生）：

```json
{
  "benchmark": "up",
  "loop_heads": ["N19", "N23"],
  "predicates": [
    "(= k i)",
    "(> k (- n j))"
  ],
  "provenance": "bootstrap validated 2026-05, commit 1a3c996380"
}
```

Java `FrozenPredicateLoader` 讀取後 **只** `addLocalPredicates(loopHead, ·)`。

## 何時使用

| 場景 | 用法 |
|------|------|
| NO_SPURIOUS + 論文對照 | Exception `FROZEN_SEED` |
| 穩定性 K=3 | 同一 frozen json 跑 3 次 CPA，不呼叫 API |
| Advisor demo 失敗 | 改播 md 內 predicate + 表格式結果 |

## 不再使用

- `VGUIDE_LLM_CACHE_DIR` / prompt hash replay（已歸檔實驗腳本）  
- 不透明 `response.txt` only cache  

## 與主路徑的界線

- **主路徑：** 第一條 spurious → Java HttpClient → 即時提案  
- **Exception：** 無 spurious → frozen 檔（**不算** LLM 自動成功）
