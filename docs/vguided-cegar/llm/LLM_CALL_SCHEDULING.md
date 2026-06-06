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

## 預設（`config/vguide.properties`）

| 名稱 | schedule | everyN | minInterval | max | 說明 |
|------|----------|--------|-------------|-----|------|
| **default**（現行） | `every_n_and_interval` | **72** | **15** | **5** | full_scalar 主實驗用 |
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
