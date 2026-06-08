# LLM 多抽卡（Ensemble）

**作者**: r14k41044 黃思維  
**模組**: `VGuideRefinementBridge` + `PredicateProposalClient`

> **預設**：`vguide.llmSamplesPerCall = 1`（單 draw / 輪）。  
> **單輪多條**由 [PREDICATE_BUDGET.md](PREDICATE_BUDGET.md) 控制（預設 3–6 條），與 ensemble 正交。

## 行為

| Spurious 輪次 | API 次數 | 平行 |
|---------------|----------|------|
| **#1（第一次 spurious）** | **恆 1**（程式寫死，不受 `llmSamplesPerCall` 影響） | **絕不平行**（試水溫 + DeepSeek **prompt cache**） |
| **#2+** 且 `llmSamplesPerCall=K` | **1 同步 + (K−1) 平行** | 僅額外 (K−1) 次平行 |

合併策略：**`union_validate`** — 各次回應 parse 後字串去重，再交 `PredicateValidationPipeline`（與單次相同）。

Repair：合併後仍無 accepted predicate 且存在 rejected → **單次** repair API（不 ensemble）。

## 參數（`vguide.*`）

| 選項 | 預設 | 說明 |
|------|------|------|
| `llmSamplesPerCall` | `1` | 第 2 次起每 **LLM 輪** 目標抽樣數 K（#1 仍為 1） |
| `llmSampleParallelism` | `4` | (K−1) 次額外 draw 的最大併發 |
| `maxLlmRoundsPerAnalysis` | `5` | 上限為 **spurious 輪次**（每輪可含多個 API，仍只計 1 輪） |

### `maxLlmRounds` 語意

- **計 1**：排程允許的一次「spurious → 走 VGuide LLM 流程」。
- **不計**：該輪內的 K 次 HTTP（含平行 extras）與 repair 單發。

例：`maxLlmRounds=5`、`llmSamplesPerCall=3` → 最多 5 個 spurious 輪會叫 LLM；若每輪都打滿，HTTP 約 `5 × (1+2)` = **15**（不含 repair）。

## 使用範例

```bash
./scripts/cpa.sh --config config/predicateAnalysis-vguide.properties \
  --option cpa.predicate.refinement.useVocabularyGuide=true \
  --option vguide.llmSamplesPerCall=3 \
  --option vguide.llmSampleParallelism=3 \
  --option vguide.maxLlmRoundsPerAnalysis=5 \
  ...
```

## Log 範例

```
VGuide LLM round #1 spurious #1 samples=1 api=1 ... latencyMs=1600
VGuide LLM round #2 spurious #45 samples=3 api=3 ... latencyMs=2100
```

- `samples`：本輪設定 K（#1 恆為 1）
- `api`：實際 HTTP 次數（含 ensemble extras，不含 repair 時與 samples 相同；repair 另 +1）

## 多 draw 合併與「謂詞衝突」

多抽卡時，不同 draw 可能提出 **語意不一致** 的候選（例如一個偏 `x=0`、另一個偏 `x≥2`）。

**結論：與 soundness 無關，頂多變慢。**

- 候選只進 **precision**，不是 axiom；**TRUE/FALSE 仍由 CPAchecker 證明**。  
- 若多條同時合法，抽象通常 **更細**；路徑上合不攏時，CEGAR 會再 refinement 或得到 UNKNOWN，**不會**因此錯判 TRUE。  
- 實務影響：可能 **多幾輪 refinement / 較久 UNKNOWN**（探索變慢），不是正確性問題。  
- 目前 **`union_validate`（去重 + Validator）** 已足夠；**不需**額外「互斥過濾」除非日後實測變慢嚴重。

與 **repair** 的差別：repair 是「全部 reject 後改 prompt 再問 **1** 次」，與多 draw 合併無關。

## 與排程的關係

`llmMinIntervalSec` / `every_n` 仍決定 **哪幾個 spurious 輪** 進入 LLM；ensemble 只影響 **該輪內** 打幾次 API。見 [LLM_CALL_SCHEDULING.md](LLM_CALL_SCHEDULING.md)。
