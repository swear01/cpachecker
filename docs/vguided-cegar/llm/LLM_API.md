# DeepSeek V4 API（VGuide LLM 客戶端）

VGuide 透過 `PredicateProposalClient` 呼叫 `https://api.deepseek.com/chat/completions`（OpenAI 相容格式）。

## 環境變數

| 變數 | 預設 | 說明 |
|------|------|------|
| `DEEPSEEK_API_KEY` | — | live／record mode必填；純replay可省略 |
| `DEEPSEEK_MODEL` | `deepseek-v4-pro` | 亦可用 `deepseek-v4-flash` |
| `VGUIDE_LLM_THINKING` | **`disabled`** | `disabled` = non-thinking；`enabled` = thinking mode |
| `VGUIDE_LLM_REASONING_EFFORT` | `high`（僅 thinking 時） | `high` 或 `max`（`low`/`medium` 會對應到 `high`） |
| `VGUIDE_LLM_TIMEOUT_SEC` | `120` | 單次 HTTP 逾時 |
| `VGUIDE_LLM_RECORD_DIR` | — | 將live response按task/request hash/ordinal原子寫入；不可與replay同時設定 |
| `VGUIDE_LLM_REPLAY_DIR` | — | fail-closed重播已錄response；cache miss不呼叫live API |
| `VGUIDE_LLM_REPLAY_PRESERVE_LATENCY` | `true` | replay時等待原始call latency，維持paired wall-clock accounting |
| `VGUIDE_LLM_CACHE_NAMESPACE` | `default` | cache task namespace；batch runner自動設成task名 |
| JSON mode | **永久開啟** | 固定 `response_format: json_object` |

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
- Analysis dump：`llm_rounds.jsonl` 每行有 `latency_ms`、`usage`、`prompt_hash`、`request_hash`、`response_hash`與`response_source`
- `run_manifest.json`：`model`、`llm_thinking`

## Paired record/replay

Gate的causal experiment先以gate-off live arm錄製，再讓gate-on重播相同response prefix：

```bash
export CACHE="$PWD/output/vguide/llm-cache/usefulness-full764"
VGUIDE_LLM_RECORD_DIR="$CACHE" ./scripts/vguided-cegar/run.sh cpa \
  --set loops_reachsafety_unreach --mode usefulness-gate-off --parallel 8 --timelimit 300

env -u DEEPSEEK_API_KEY VGUIDE_LLM_REPLAY_DIR="$CACHE" \
  ./scripts/vguided-cegar/run.sh cpa \
  --set loops_reachsafety_unreach --mode usefulness-gate-on --parallel 8 --timelimit 300
```

同一task內相同request以ordinal區分。Replay會驗證schema、request hash與ordinal；missing/corrupt
entry直接終止該CPA run，沒有live或stock fallback。預設等待recorded latency，因此不能把replay
runtime誤當成「免費LLM」。

## JSON Output

`response_format: {"type": "json_object"}` 每次必送；prompt含JSON contract與範例物件。見 [DeepSeek JSON Output](https://api-docs.deepseek.com/guides/json_mode)。

## 離線腳本對齊

`scripts/vguided-cegar/test_llm_proposal_quality.py`：`thinking: disabled`；v1.4 實作後加 `json_object`。

## 參考

- [DeepSeek Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode)
- [Create Chat Completion](https://api-docs.deepseek.com/api/create-chat-completion)
- [JSON Output](https://api-docs.deepseek.com/guides/json_mode)
