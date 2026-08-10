# VGuide（Unified）

**單一路徑、全 Java。** 設計見 [architecture/UNIFIED_VGUIDE_ARCHITECTURE.md](architecture/UNIFIED_VGUIDE_ARCHITECTURE.md)。

**Predicate 驗證**：L1 contract + L2 parse 必跑；**L3 不用**（消融整體較差，`enableL3Entailment=false`）。

**Per-loop-head candidate contract（Issue #4，已完成）**：LLM 輸出必須為
`loop-head-candidate-v1`（每個候選帶 `loop_head`/`loop_heads`）；無 location 一律 reject
且原因可觀察（`missing_loop_head` 等）。Scope 驗證（free variables 必須在 trace vocabulary
且 function 相符）、`over_specific`/`group_conflict` advisory diagnostics、dump schema-5
（`candidate_rejections`）。實作：PR #21/#22/#23；契約見
[LOOP_HEAD_INVARIANT_PLAN.md](LOOP_HEAD_INVARIANT_PLAN.md)。

**Predicate usefulness gate**：validation後、injection前，若目前trace的loop-head visits ≤8且
至少2個unique formulas含`bvmul`，整批precision predicates不注入並停止後續LLM rounds；standard
refinement照常。General default為off，只由`vguide-experiment-usefulness-gate-on.properties`
顯式開啟。Fresh targeted結果為7/7 losses recovered、2/2 direct wins preserved、0 wrong。

## 快速入口

### 現行入口與計劃（active）

| 文件 | 狀態 | 用途 |
|------|------|------|
| [VGUIDE_NLA_PLAN.md](VGUIDE_NLA_PLAN.md) | **STOP after final consumer gate** | Ordinary KI、conjunctive KI-PDR與direct PDR oracle arms皆0/12；不做CTI helper，轉predicate usefulness gating |
| [RUN_EXPERIMENTS.md](RUN_EXPERIMENTS.md) | 現行入口 | **`run.sh` 怎麼跑**；批次後 PAR-2 / cactus |
| [reports/README.md](reports/README.md) | 報告索引 | 進度報告總入口 |
| [SVCOMP26_OVERFLOW_VGUIDE_IMPROVEMENT_PLAN.md](SVCOMP26_OVERFLOW_VGUIDE_IMPROVEMENT_PLAN.md) | deferred | 91 fired/37 fired-but-UNKNOWN；config/prompt cheap levers 已用盡；predicate usefulness gating完成前不再投入 |
| [SVCOMP26_PORTFOLIO_LLM_PLAN.md](SVCOMP26_PORTFOLIO_LLM_PLAN.md) | background | 把 LLM 從 PredicateCPA 擴展到 svcomp26 portfolio strategy；guards 層已完成，後續 layers 非現行主線 |
| [REACHSAFETY_IMPROVEMENT_PLAN.md](REACHSAFETY_IMPROVEMENT_PLAN.md) | **A1 = v1.7.0+v1.7.1 ✅** | ReachSafety stock-first + peel完成：764 `svcomp27-vguide` **482→493→504（累積 +22 / 0 wrong）**。NLA k-induction新注入點因 oracle gate 0/12取消；現轉 usefulness gating。A2 CPU隔離已評估後砍。**不考慮競賽** |
| [SVCOMP_INTEGRATION_PLAN.md](SVCOMP_INTEGRATION_PLAN.md) | deferred | **svcomp27** × VGuide v1.5 整合背景；predicate usefulness gating完成前不投入 |
| [LLM_RESEARCH_ROADMAP.md](LLM_RESEARCH_ROADMAP.md) | 現行 roadmap | Predicate usefulness gating優先；其餘跨 property/domain/FALSE/witness/offline方向作後續地圖；含 S/R/X soundness守則 |

### 已完成計劃與結果記錄（✓ done / 歷史）

| 文件 | 狀態 | 用途 |
|------|------|------|
| [reports/2026-06-20_reachsafety_exploration_summary.md](reports/2026-06-20_reachsafety_exploration_summary.md) | **階段總結** | **ReachSafety LLM 改進探索收尾**:v1.7.0+v1.7.1 = +22/0 wrong(504/764);nla-digbench 非線性 out-of-scope、A2/peel-prompt/FALSE-fuzzing 已評估後砍/降優先;**PAUSED at v1.7.1** |
| [reports/2026-06-20_reachsafety_stockfirst_guard.md](reports/2026-06-20_reachsafety_stockfirst_guard.md) | 結果記錄 | **A1 止血 schedule ablation (v1.7.0)**：`every_n_or_interval` stock-first guard。targeted 15 loss → +4/0/0;**完整 764 both-arm → 482→493 淨 +11（+17 new −6 lost）、0 wrong** |
| [reports/2026-06-20_reachsafety_peel_trigger.md](reports/2026-06-20_reachsafety_peel_trigger.md) | 結果記錄 | **A1.2 peel 觸發器 (v1.7.1)**:早開火(loop-head visits ≥ 4),救回 v1.7.0 的 #1-need 回歸。**完整 764 → 493→504 淨 +11（+18 new −7 lost）、0 wrong;累積 +22** |
| [SVCOMP26_OVERFLOW_VGUIDE_PLAN.md](SVCOMP26_OVERFLOW_VGUIDE_PLAN.md) | ✓ v1.6 | 把 reachability 的 predicate-CEGAR hook 泛化到 NoOverflow branch（Class-A、config-only、零 Java）——+6/0 lost/0 wrong |
| [SVCOMP26_VGUIDE_FULLSET_PLAN.md](SVCOMP26_VGUIDE_FULLSET_PLAN.md) | ✓ v1.5.1 | **svcomp26-vguide** full-set 計劃與完成狀態 |
| [SVCOMP26_TERMINATION_VGUIDE_PROBE.md](SVCOMP26_TERMINATION_VGUIDE_PROBE.md) | ✓ 結案(RED) | probe RED → Class-B：引擎是 `TerminationToReachCPA` 非 predicate-CEGAR，VGuide 無從 fire；termination 留 v2.0 ranking-function Java hook |
| [reports/2026-06-16_combined_300s_classA.md](reports/2026-06-16_combined_300s_classA.md) | 結果記錄 | **v1.6.1 combined @300s**：unified config，reach **+15** / overflow **+4**（競賽級、0 wrong）；含 free-LLM-time / 非競賽情境 caveat |
| [reports/2026-06-15_svcomp26_overflow_vguide.md](reports/2026-06-15_svcomp26_overflow_vguide.md) | 結果記錄 | **v1.6 Class-A**：NoOverflow 452 題，363 solved vs stock 357（**+6 / 0 lost / 0 wrong**） |
| [reports/2026-06-14_svcomp26_vguide_loops.md](reports/2026-06-14_svcomp26_vguide_loops.md) | 結果記錄 | **v1.5.1**：Loops 764 題，493 solved vs svcomp26 486（+7），0 wrong，16 direct LLM wins |
| [reports/2026-06-13_v1.5_loops_reachsafety_unreach.md](reports/2026-06-13_v1.5_loops_reachsafety_unreach.md) | 結果記錄 | **v1.5**：Loops broad set 764 題，VGuide +37 vs stock，33 VGuide-only TRUE solves |
| [reports/2026-06-10_freq10_n24_adaptive_noL3.md](reports/2026-06-10_freq10_n24_adaptive_noL3.md) | 結果記錄 | **v1.3 noL3**：150 solved、PAR-2 192s |

## 現行目錄

```
docs/vguided-cegar/
├── VGUIDE_NLA_PLAN.md                 # ordinary KI + final PDR/KI-PDR RED；STOP record
├── RUN_EXPERIMENTS.md
├── LOCAL_DEVELOPMENT_ENV.md
├── SVCOMP_INTEGRATION_PLAN.md
├── SVCOMP26_VGUIDE_FULLSET_PLAN.md
├── SVCOMP26_PORTFOLIO_LLM_PLAN.md
├── REACHSAFETY_IMPROVEMENT_PLAN.md   # 止血優先,不考慮競賽
├── LLM_RESEARCH_ROADMAP.md
├── SVCOMP26_OVERFLOW_VGUIDE_PLAN.md   # v1.6 ✓ 完成
├── SVCOMP26_OVERFLOW_VGUIDE_IMPROVEMENT_PLAN.md   # v1.6.1 提升計劃
├── SVCOMP26_TERMINATION_VGUIDE_PROBE.md   # v1.6 probe RED
├── architecture/UNIFIED_VGUIDE_ARCHITECTURE.md
├── llm/                    # 排程、ensemble、predicate budget、API
├── analysis/               # 已完成/歷史計劃與方法記錄
├── experiments/            # 已完成的單次實驗規格
├── evaluation/             # benchmark 定義、frozen replay
├── reports/                # 進度報告
├── benchmark_sets/         # manifest（run.sh 讀取）
└── predicate_sets/         # Exception 用凍結謂詞
```

### llm/

| 文件 | 用途 |
|------|------|
| [llm/LLM_API.md](llm/LLM_API.md) | **DeepSeek V4** 模型、thinking / non-thinking、環境變數 |
| [llm/LLM_CALL_SCHEDULING.md](llm/LLM_CALL_SCHEDULING.md) | `min_interval` / `every_n` 排程 |
| [llm/LLM_ENSEMBLE.md](llm/LLM_ENSEMBLE.md) | 雙 prompt（SAFE+BUG）與每軌 ensemble（v1.4） |
| [llm/PREDICATE_BUDGET.md](llm/PREDICATE_BUDGET.md) | **單輪多條** predicate 數量與品質 |
| [llm/OFFLINE_SAMPLING.md](llm/OFFLINE_SAMPLING.md) | `test_llm_proposal_quality.py` vs CPA 內 LLM |

### evaluation/

| 文件 | 用途 |
|------|------|
| [evaluation/STANDARD_BENCHMARK_SUITE.md](evaluation/STANDARD_BENCHMARK_SUITE.md) | sample(8) + full_scalar(217) |
| [benchmark_sets/README.md](benchmark_sets/README.md) | manifest 與排除說明 |
| [evaluation/FROZEN_PREDICATES.md](evaluation/FROZEN_PREDICATES.md) | NO_SPURIOUS Exception、replay |

## 已完成/歷史計劃

`analysis/`、`experiments/` 與部分 `llm/*PLAN.md` 保留已完成的設計與實驗規格，
現行 claim 與重跑入口以上方報告、`RUN_EXPERIMENTS.md`、`SVCOMP26_VGUIDE_FULLSET_PLAN.md` 為準。
搜尋目前架構時優先看 `architecture/`、`llm/` 的現行說明與 `reports/2026-06-14_svcomp26_vguide_loops.md`。
