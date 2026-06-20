# LLM 呼叫排程：依延遲與 refinement 速率設計

## 實測數字（本機）

| 量測 | 來源 | 數值 |
|------|------|------|
| LLM API 延遲 p50 | `test_llm_proposal_quality.py` ×15 次 | **~1.0 s** |
| LLM API 延遲 p99 | 同上 | **~1.5 s** |
| 單次 spurious refinement 耗時 | `array_3-1.i` 60s CPA stats | **~0.21 s/ref**（4 ref / 1.05s） |

因此 fast rescue 題上 **refinement 遠快於 LLM**；排程必以 **牆鐘間隔 `min_interval`** 為主，`every_n` 在快速 CE 下往往達不到下一格（分析在 #11 前已結束）。

## 設計原則

1. **兩次 LLM 之間至少隔開** `min_interval` ≥ `L_p99 + margin`
2. **`every_n`**：快題上應很大，或依 `ceil(min_interval / t_ref)` 推算
3. **`maxLlmRoundsPerAnalysis`** = 會叫 LLM 的 **spurious 輪數** 上限（300s 建議 **5–8**）
4. **`every_n_and_interval`**：兩條件 **都** 要滿足
5. **`every_n_or_interval`（現行預設,v1.7.0 stock-first）**：任一條件滿足即開火,但 **不在 #1**(every_n 從 #N 起算);時間軸首次也等 `min_interval`(從分析起點量,不是立即)。只在 stock 不收斂時介入——次數(many cheap)**OR** 牆鐘(few expensive)。設計見 [`../REACHSAFETY_IMPROVEMENT_PLAN.md`](../REACHSAFETY_IMPROVEMENT_PLAN.md) A1。

## 預設（`config/vguide.properties`）

| 名稱 | schedule | everyN | minInterval | max | 說明 |
|------|----------|--------|-------------|-----|------|
| **default**（現行,v1.7.1） | `every_n_or_interval` + **peel=4** | **10** | **15** | **5** | stock-first + **peel 觸發器**(loop-head visits ≥ 4 早開火,refinement #2+)。764 累積 **+22 / 0 wrong**(482→493→504) |
| `every_n_and_interval`（舊預設 ≤v1.5.1） | `every_n_and_interval` | 72 | 15 | 5 | full_scalar 舊主實驗(會在 #1 開火) |
| `bootstrap_only` | `first_spurious` | — | 0 | 1 | 最便宜、僅首輪 spurious |
| `thorough` | `every_n_and_interval` | **50** | **25** | **8** | 單題深挖 |
| `interval_only` | `min_interval` | — | **40** | **5** | 只信牆鐘 |

覆寫例：

```bash
--option vguide.llmCallSchedule=first_spurious
--option vguide.llmMinIntervalSec=25
```

## 公式（自行校準）

```
min_interval_sec ≥ max(15, 3 × L_lm_p99)
every_n ≥ ceil(min_interval / t_ref_avg)
max_llm ≤ floor(wall_time / min_interval)
```

換機器或模型後請重測 `test_llm_proposal_quality.py` 與一輪 CPA `--stats`。
