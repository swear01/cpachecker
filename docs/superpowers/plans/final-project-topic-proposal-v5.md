# Final Project Topic Proposal (v5)

**Date:** 2026-05-18

**Topic:** 基於 LLM 動態謂詞詞彙庫之 CEGAR 插值策略導引  
**Vocabulary-Guided CEGAR: Dynamic LLM Predicate Vocabulary for Interpolation Strategy Selection in Software Model Checking**

**Team Mate:** r14k41044 黃思維

---

## 1. Motivation

CEGAR 是 software model checking 的主流框架。以 CPAchecker 為例，predicate abstraction + CEGAR 在遇到 spurious counterexample 時，透過 Craig interpolation 產生 predicates 並加入 precision。

問題在於：同一條 spurious trace 可由不同 interpolation strategy / direction 產生多組合法 interpolants。這些 interpolants 都能排除當前 trace，但其語意品質可能差很多。固定使用預設策略容易導致：

1. predicates 過度 minimal，只排除當前 trace；
2. CEGAR refinement iteration 增加；
3. loop-heavy、array、linear arithmetic cases 收斂較慢。

LLM 具備從程式碼與 trace 中抽取高階語意 predicate 的能力，但直接把 LLM predicate 加入 precision 會牽涉 soundness 風險。本研究採用較保守的設計：

> LLM 不直接替代 interpolation；LLM 只維護一個動態 Predicate Vocabulary `V`，用來在多個合法 interpolation 結果中選擇語意上較好的結果。

---

## 2. Problem Formulation

給定某輪 CEGAR 產生的 spurious trace `π`，系統對同一條 `π` 計算多個合法 interpolation candidates：

```text
P1 = SEQ_CPACHECKER / FORWARDS
P2 = SEQ_CPACHECKER / BACKWARDS
P3 = SEQ_CPACHECKER / ZIGZAG
P4 = TREE_WELLSCOPED / ZIGZAG
P5 = TREE_NESTED / ZIGZAG
P6 = TREE_WELLSCOPED / LOOP_FREE_FIRST
```

每組 `Pi` 都是 solver 產生的合法 interpolants，因此 soundness 不依賴 LLM。

系統用 LLM-maintained vocabulary `V` 評分每組 `Pi`：

```text
score(Pi, V) = α * subsumption(Pi, V) + (1 - α) * variableOverlap(Pi, V)
```

其中：

- **Subsumption score**：對 `p ∈ Pi`，若存在 `v ∈ V` 使得 `v => p`，則計分。
- **Variable overlap**：`p` 與 `V` 中 predicates 的變數集合 Jaccard similarity。
- 預設 `α = 0.6`、`τ = 0.2`。

選出 score 最高的 interpolant set 加入 precision。

---

## 3. True Sidecar LLM Architecture

本研究要求 LLM 與 CEGAR **完全非同步**：

> CPAchecker 主流程不得直接等待 LLM HTTP call。

因此 `V` 是一個 eventually-improving sidecar state。CEGAR 每次 refinement 只讀取當下可用的 `V` snapshot；若 `V` 尚未初始化或品質不足，系統仍可 fallback 到預設 interpolation candidate。

### Sidecar Workflow

```text
PredicateCPARefinerFactory.create()
  -> create VocabularyGuide with empty V
  -> create LLMConnector sidecar
  -> llm.start()
  -> llm.requestInitialVocab()       // enqueue only, non-blocking
  -> return PredicateCPARefiner

PredicateCPARefiner.performInterpolatingRefinement()
  -> compute all interpolation candidates
  -> score candidates using current V snapshot
  -> select best candidate, or fallback if V is empty/weak
  -> if score < τ:
       llm.addTrace(current trace)
       llm.onShortfall()            // enqueue CE-guided update only
  -> return immediately

LLMConnector daemon thread
  -> process queued INITIAL / CE_GUIDED requests
  -> call OpenRouter reasoning model
  -> parse predicates
  -> update V
```

### Timeout Role

LLM timeout is **not** used to protect CEGAR latency; CEGAR never waits for LLM. Timeout only prevents the sidecar from being stuck forever.

Default sidecar settings:

```text
OPENROUTER_MODEL = deepseek/deepseek-v4-pro
OPENROUTER_MAX_COMPLETION_TOKENS = 8192
OPENROUTER_REASONING_TOKENS = 2048
OPENROUTER_TIMEOUT_SECONDS = 600
```

Reasoning tokens are bounded because reasoning models can otherwise spend the entire completion budget on internal reasoning and return `content = null`.

---

## 4. Implementation Plan

Implementation is based on a CPAchecker fork.

Modified / added files:

```text
src/org/sosy_lab/cpachecker/cpa/predicate/VocabularyGuide.java
src/org/sosy_lab/cpachecker/cpa/predicate/LLMConnector.java
src/org/sosy_lab/cpachecker/cpa/predicate/PredicateCPARefiner.java
src/org/sosy_lab/cpachecker/cpa/predicate/PredicateCPARefinerFactory.java
```

Key implementation points:

1. `PredicateCPARefinerFactory` creates multiple `InterpolationManager`s with different strategy / direction configs.
2. `VocabularyGuide` stores `V`, scores candidates, and records usage statistics.
3. `LLMConnector` is a daemon sidecar with an internal request queue.
4. `PredicateCPARefiner` never calls blocking LLM APIs; it only reads `V` and enqueues update requests.

---

## 5. Research Questions

**RQ1:** Does V-guided strategy selection produce more semantic predicates than the fixed default strategy?

**RQ2:** Does V-guided strategy selection reduce total CEGAR refinement iterations?

**RQ3:** Does dynamic sidecar update improve vocabulary quality over time?

**RQ4:** Is the improvement due to LLM semantic guidance rather than merely switching strategies?

---

## 6. Baselines

1. **Stock CPAchecker**: default `SEQ_CPACHECKER / ZIGZAG`.
2. **Random Strategy Selection**: randomly select from the same strategy pool.
3. **Static V Only**: LLM generates only initial `V0`, no dynamic update.
4. **Dynamic V-Guided Sidecar**: proposed method.

---

## 7. Evaluation

Benchmarks:

- SV-COMP `loops/`
- SV-COMP `loop-invariants/`
- SV-COMP `array-examples/`
- 20-30 instances that CPAchecker can finish within timeout.

Metrics:

1. Verification success rate under 300s timeout.
2. CEGAR refinement iteration count.
3. Predicate semantic quality.
4. Vocabulary usage quality: `selected / considered`.
5. Strategy deviation rate from stock default.
6. End-to-end runtime with and without sidecar LLM overhead.
7. Ablation: static V vs dynamic V; 3 strategies vs 6 strategies; cleanup on/off.

---

## 8. Expected Contribution

This project contributes a soundness-preserving LLM-assisted CEGAR heuristic:

> LLM semantic knowledge influences which legal interpolation result is selected, but never replaces solver-generated interpolants.

The central contribution is a true sidecar architecture where LLM updates improve `V` asynchronously while CPAchecker continues verification without waiting for LLM calls.
