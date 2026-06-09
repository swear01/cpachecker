# DeepSeek V4 API（VGuide LLM 客戶端）

VGuide 透過 `PredicateProposalClient` 呼叫 `https://api.deepseek.com/chat/completions`（OpenAI 相容格式）。

## 環境變數

| 變數 | 預設 | 說明 |
|------|------|------|
| `DEEPSEEK_API_KEY` | — | **必填** |
| `DEEPSEEK_MODEL` | `deepseek-v4-pro` | 亦可用 `deepseek-v4-flash` |
| `VGUIDE_LLM_THINKING` | **`disabled`** | `disabled` = non-thinking；`enabled` = thinking mode |
| `VGUIDE_LLM_REASONING_EFFORT` | `high`（僅 thinking 時） | `high` 或 `max`（`low`/`medium` 會對應到 `high`） |
| `VGUIDE_LLM_TIMEOUT_SEC` | `120` | 單次 HTTP 逾時 |

## Thinking vs non-thinking（重要）

DeepSeek **V4 預設是 thinking enabled**。若不關閉，API `usage` 會出現大量 **`reasoning_tokens`**（內部 chain-of-thought），latency 常達數十秒～數分鐘，且與最終 JSON 品質無直接對應。

| 模式 | Request body | `reasoning_tokens` | 適用 |
|------|----------------|-------------------|------|
| **Non-thinking（預設）** | `"thinking": {"type": "disabled"}` | 應為 0 或極小 | **VGuide 主路徑**（結構化 JSON predicate） |
| Thinking | `"thinking": {"type": "enabled"}` + `reasoning_effort` | 高 | 實驗／難題探索 |

**不要**依賴舊版 `reasoning: { exclude: true }` 參數——那是舊 API 語意（隱藏思考文字，**不等於**關閉 thinking），且 V4 已改用 `thinking.type`。

開啟 thinking 範例：

```bash
export VGUIDE_LLM_THINKING=enabled
export VGUIDE_LLM_REASONING_EFFORT=high   # 或 max
```

## 日誌與 dump

- CPA log：`VGuide LLM model:`、`VGuide LLM thinking:`、`VGuide LLM round # … latencyMs=`
- Analysis dump：`llm_rounds.jsonl` 每行有 `latency_ms`、`usage`（含 `reasoning_tokens`）
- `run_manifest.json`：`model`、`llm_thinking`

## 離線腳本對齊

`scripts/vguided-cegar/test_llm_proposal_quality.py` 預設亦送 `thinking: disabled`，與 Java 客戶端一致。

## 參考

- [DeepSeek Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode)
- [Create Chat Completion](https://api-docs.deepseek.com/api/create-chat-completion)
