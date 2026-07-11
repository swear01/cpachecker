# Unified VGuide Architecture（單一路徑）

> 取代 B2 / B4 / B5 / Python sidecar。Legacy 見本機 `archive/vguided-legacy/`（gitignore）。

## 決策摘要

| 項目 | 決定 |
|------|------|
| LLM | **全 Java `HttpClient`**（與 CPAchecker 同 JVM） |
| 觸發 | runtime config決定；pinned stock-first為refinement #10、15秒或peel trigger |
| 注入 | **僅 loop head**，`addLocalPredicates`（LBE 對齊） |
| ENTAILED | L3-on 時：`block ⊨ pred` → strengthen interpolant（**主線不用 L3**） |
| L3 (SMT entailment) | **不用**（2026-06-07 消融：L3-on 整體較差 → `enableL3Entailment=false`） |
| NO_SPURIOUS | **Exception**：可選 [FROZEN_PREDICATES](../evaluation/FROZEN_PREDICATES.md) |
| Semantic seed replay | **Frozen predicate 檔**（NO_SPURIOUS exception） |
| Paired API replay | evaluation-only exact request-hash/ordinal response cache；fail closed |
| Legacy B2/B4/B5 | **已歸檔** |

## 模組（Java package）

```
org.sosy_lab.cpachecker.cpa.predicate.vguide
  VGuideRefinementBridge      // 唯一入口，掛在 PredicateCPARefiner
  ContextPackBuilder          // source + CE + loop_heads + var_contract
  PredicateProposalClient     // DeepSeek HttpClient，可 parallel variants
  LlmResponseCache            // paired record/replay；per-task namespace，無live fallback
  PredicateValidationPipeline // L1 contract, L2 parse (L3 implemented, not used)
  LoopHeadPrecisionInjector   // local inject only
  FrozenPredicateLoader       // NO_SPURIOUS exception
  VGuideOutcome               // FIRST_SPURIOUS | FROZEN_SEED | NO_SPURIOUS_GIVE_UP
```

## 控制流

```mermaid
sequenceDiagram
  participant CPA as PredicateCPA
  participant Br as VGuideRefinementBridge
  participant LLM as PredicateProposalClient
  participant Inj as LoopHeadPrecisionInjector

  CPA->>CPA: explore until spurious or timeout
  alt refinements == 0 at budget end
    Br->>Br: NO_SPURIOUS → optional FrozenPredicateLoader
  else first or later spurious
    Br->>Br: ContextPackBuilder
    Br->>LLM: propose (HttpClient, wall budget)
    Br->>Br: PredicateValidationPipeline
    opt frozen usefulness gate rejects batch
      Br->>Br: suppress injection and later LLM calls
    end
    CPA->>CPA: standard interpolation refinement
    Br->>Inj: accepted precision-only predicates, loop heads only
    Inj->>CPA: update PredicatePrecision
  end
```

## 主要設定（`config/vguide.properties`）

```properties
vguide.enable=true
vguide.llmCallSchedule=every_n_or_interval
vguide.llmEveryNSpuriousRefinements=10
vguide.llmMinIntervalSec=15
vguide.maxLlmRoundsPerAnalysis=5
vguide.peelLoopHeadThreshold=4
vguide.dualPromptMode=true
vguide.llmSamplesPerCall=1
vguide.enablePredicateUsefulnessGate=false
vguide.enableL3Entailment=false   # not used (ablation worse)
vguide.frozenDir=docs/vguided-cegar/predicate_sets
```

`cpa.predicate.refinement.useVocabularyGuide=true` 改為只啟用 **Bridge**，**不**啟動舊 `LLMConnector.initializeVocabBlocking()`。

## 廢除項

- Python `bootstrap_*` / `b5_*` / `b4_*` 腳本（已歸檔）  
- `VGUIDE_INJECT_REPAIR_*` env 樹  
- 舊版 `VGUIDE_LLM_RECORD` / `REPLAY` protocol（現行evaluation cache使用明確的
  `VGUIDE_LLM_{RECORD,REPLAY}_DIR`，不恢復legacy sidecar）
- Java `LLMConnector` 背景 thread（實作移除前以 `vguide.legacyConnector=false` 關閉）

## 已完成的實施順序

1. **文檔 + 歸檔**
2. `PredicateProposalClient` + prompt 模板（合併原 bootstrap/B5 語意）  
3. `VGuideRefinementBridge` 接 Refiner；關舊 Connector 啟動  
4. `LoopHeadPrecisionInjector` + validation pipeline  
5. `FrozenPredicateLoader` + NO_SPURIOUS 統計日誌  
6. 刪除 archive 依賴的 demo 腳本，改 CPA 單命令 demo  

## 相關

- [FROZEN_PREDICATES.md](../evaluation/FROZEN_PREDICATES.md)  
- [LOCAL_DEVELOPMENT_ENV.md](../LOCAL_DEVELOPMENT_ENV.md)
