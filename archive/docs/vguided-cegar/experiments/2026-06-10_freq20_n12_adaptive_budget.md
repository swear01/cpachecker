# 實驗計劃：every_n=12 + maxLlmRounds=20（adaptive budget）

**狀態**：待跑（config 就緒）  
**前置 tag**：`v1.3.0`（freq10/n24：150 solved，PAR-2 avg 192.03s）  
**基線**：`config/vguide-experiment-freq10-n24.properties`

---

## 1. 變更（相對 v1.3.0）

| 參數 | v1.3.0 | **本實驗** |
|------|--------|------------|
| `vguide.llmEveryNSpuriousRefinements` | 24 | **12** |
| `vguide.llmMinIntervalSec` | 15 | **15**（不變） |
| `vguide.maxLlmRoundsPerAnalysis` | 10 | **20** |
| adaptive budget / completion tokens | 同左 | 不變 |

**排程語意（`every_n_and_interval`）**

- Spurious **#1, #13, #25, #37, …**（`(refinementIndex - 1) % 12 == 0`）且距上次 LLM ≥15s。
- 最多 **20 輪** LLM（`const_1-2` 類高 refinement 題可觸發至 spurious **#229**）。

**粗估 API 量**

- stock-unsolved 池：refs&lt;25 仍可觸發 **2 次**（#1、#13），較 n=24 多 1 slot。
- 高 refinement 題：20 輪 × ~3s LLM ≈ 60s LLM + 20×15s interval ≈ **380s** 排程上限 → 300s timelimit 下實際受牆鐘限制。

---

## 2. Config

`config/vguide-experiment-freq20-n12.properties`

---

## 3. 驗收（相對 v1.3.0）

| 指標 | 目標 |
|------|------|
| solved | **≥150**（不退化） |
| PAR-2 avg | ≤195s（允許略升） |
| vs stock degraded | ≤2 |
| `const_1-2` | 見 case study 假設：更多 LLM 輪或 verdict 改善 |

---

## 4. Full 217 執行

```bash
export VGUIDE_LLM_THINKING=disabled
export VGUIDE_CONFIG=config/vguide-experiment-freq20-n12.properties
export VGUIDE_ANALYSIS_DUMP_DIR=output/vguide/analysis_dumps/full_scalar_noL3_freq20_n12_adaptive_20260610
export VGUIDE_ANALYSIS_DUMP_PROMPTS=1
export VGUIDE_ANALYSIS_BENCHMARK_SET=full_scalar
export VGUIDE_ANALYSIS_TIMELIMIT_SEC=300

OUT=output/vguide/experiments/full_scalar_vguide_noL3_freq20_n12_adaptive_20260610

./scripts/vguided-cegar/run.sh cpa \
  --set full_scalar \
  --ablation no-l3 \
  --parallel 8 \
  --timelimit 300 \
  --out "$OUT"
```

**單題 case study 重跑**

```bash
./scripts/vguided-cegar/run.sh cpa --set sample --ablation no-l3 --timelimit 300 \
  --out output/vguide/experiments/case_const_1-2_freq20_n12 \
  --option vguide.llmEveryNSpuriousRefinements=12 \
  --option vguide.maxLlmRoundsPerAnalysis=20
# 或 verify-pack --task const_1-2（需 manifest 含該題）
```

---

## 5. 相關

- [case_studies/const_1-2.md](../analysis/case_studies/const_1-2.md)
- [reports/2026-06-10_freq10_n24_adaptive_noL3.md](../reports/2026-06-10_freq10_n24_adaptive_noL3.md)
