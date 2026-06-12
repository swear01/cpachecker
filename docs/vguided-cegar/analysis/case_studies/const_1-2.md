# Case study：`const_1-2`（loop-acceleration）

**程式**：`loop-acceleration/const_1-2.c`（舊名 `const_false-unreach-call1.c` / `.i`）  
**SV-COMP harness**：`loop-acceleration/const_1-2.yml`  
**Property**：`unreach-call.prp` → `CHECK( init(main()), LTL(G ! call(reach_error())) )`  
**Expected verdict**：**`false`**（assert 失敗 → `reach_error` **可達**；非 safe 題）  
**難點**：loop 內 `x = 0`，出口 `assert(x==1)` 必敗；工具應給 **FALSE**，predicate CEGAR 易在抽象上磨很久。

---

## 1. 程式摘要

```c
unsigned int x = 1, y = 0;
while (y < 1024) {
  x = 0;
  y++;
}
__VERIFIER_assert(x == 1);  // 執行後 x=0 → 錯誤可達（expected FALSE）
```

單 loop head（`N18`），變數 `x`, `y`；assertion 為單變數相等。

---

## 2. v1.3.0 run（freq10/n24，adaptive）

| 來源 | 路徑 |
|------|------|
| 實驗 log | `output/vguide/experiments/full_scalar_vguide_noL3_freq10_n24_adaptive_20260610/logs/const_1-2.log` |
| Dump | `output/vguide/analysis_dumps/full_scalar_noL3_freq10_n24_adaptive_20260610/tasks/const_1-2/` |

| 指標 | adaptive (n=24, max 10) | stock | old_analysis |
|------|-------------------------|-------|--------------|
| Verdict | **UNKNOWN**（應 **FALSE**） | UNKNOWN | UNKNOWN |
| Predicate refinements | **481** | 138 | 73 |
| Wall | 312.2s | — | — |
| LLM rounds / API | **10 / 10**（打滿上限） | 0 | — |

### 2.1 為何是「高 refinement + 打滿 LLM」？

- **481** 次 predicate refinement：絕大多數時間在 **SMT 插值 / 精度更新**，不是 LLM。
- **10 次 LLM** 全部用盡（`maxLlmRounds=10`）。
- 排程為 `every_n=24` + `min_interval=15`：**實際觸發 spurious #1, #49, #97, … #433**（間隔 **48** 次 spurious，#25 等常被 **15s interval** 跳過）。
- 最後一輪 LLM 在 spurious **#433**；之後仍有 spurious 至 **#481** 但已無 LLM 配額。

### 2.2 Predicate 提案品質（10 calls）

| 指標 | 值 |
|------|-----|
| budget tier | **low**（全程 S 低；max 8） |
| preds/call | **6**（每 call 固定 6，貼 low tier 中段） |
| parse_ok | 10/10 |
| validated / injected | 60 / 60 |
| total tokens | 15,032（prompt 14,199） |

**觀察**：模型穩定輸出 6 條，但未產生能終結 CEGAR 的關鍵謂詞（例如 `y` 與 1024 的關係、`x` 在 loop 出口語意）。first prompt **無 CE 摘要**（僅 source + loop head）。

### 2.3 LLM 觸發時間軸（spurious index）

| Round | Spurious # | preds |
|-------|------------|-------|
| 1 | 1 | 6 |
| 2 | 49 | 6 |
| 3 | 97 | 6 |
| … | … | 6 |
| 10 | 433 | 6 |

---

## 3. SV-COMP：誰解出來？

**ReachSafety-Loops / loop-acceleration** 標準題；配對安全題 `const_1-1.c`（assert `x==0`，expected **true**）。

| 來源 | 結果 |
|------|------|
| **SV-COMP 2024**（59 工具，[官方表](https://sv-comp.sosy-lab.org/2024/results/results-verified/unreach-call.ReachSafety-Loops.table.html)） | **~40+ 工具 `false(unreach-call)`**；少數 TIMEOUT/unknown |
| **CPAchecker SV-COMP'24** | **`false(unreach-call)`**（correct） |
| **CBMC / ESBMC / UAutomizer / UTaipan / Symbiotic / VeriAbs** 等 | 多數 **false** |
| **SV-COMP 2019**（舊名 `.i`） | **11 false**，**6 timeout**，2 unknown（約 20 工具參賽） |
| **CPAchecker seq 2016 Loops** | **timeout** |

**結論**：這題 **不是**「沒人解出」— 多數競賽工具能在時限內 **找出 bug（FALSE）**；我們 predicate+VGuide 跑成 **UNKNOWN** 代表 **沒找到反例也沒證 safe**，比賽意義上是 **未解出**。

配對題 `const_1-1`（assert `x==0`）為 expected **true**（safe）。

---

## 4. Harness 怎麼跑

**SV-Benchmarks 2.0 task**（無獨立 Java harness，靠 YAML + property）：

```yaml
# ~/sv-benchmarks/c/loop-acceleration/const_1-2.yml
input_files: 'const_1-2.c'
properties:
  - property_file: ../properties/unreach-call.prp
    expected_verdict: false
```

**BenchExec / SV-COMP**（與競賽一致）：

```bash
# 需安裝 BenchExec；tool 定義見 CPAchecker 的 svcomp.xml
benchexec --tool=cpachecker ~/sv-benchmarks/c/loop-acceleration/const_1-2.yml
```

**CPAchecker 本機**（我們 batch 等價：`default.spc` = assertion + ERROR label）：

```bash
export JAVA=$HOME/.local/bin/java
scripts/cpa.sh -config config/predicateAnalysis-vguide.properties \
  -spec config/specification/default.spc \
  -timelimit 300 \
  ~/sv-benchmarks/c/loop-acceleration/const_1-2.c
```

期望輸出：`Verification result: FALSE`（若 predicate 分析找到 assert 失敗路徑）。

---

## 5. v1.4 假設（every_n=12，max rounds 20）

| 變更 | 對 `const_1-2` 的預期 |
|------|------------------------|
| `every_n=12` | 觸發點 **#1, #13, #25, …**；減少「等 48 步才第二次 LLM」 |
| `maxLlmRounds=20` | 在 300s 內至多觸發至 spurious **#229**（若 interval 允許） |
| 仍無 CE context | 可能仍 UNKNOWN，但 **更早** 拿到更多提案 → 適合對照 |

**建議重跑**

```bash
export VGUIDE_CONFIG=config/vguide-experiment-freq20-n12.properties
export VGUIDE_LLM_THINKING=disabled
export VGUIDE_ANALYSIS_DUMP_DIR=output/vguide/analysis_dumps/const_1-2_freq20_n12
# 使用 run_benchmark_set 單題或 full_scalar 子集
```

---

## 6. 改進方向

見 [FALSE_ORIENTED_VGUIDE_PLAN.md](../FALSE_ORIENTED_VGUIDE_PLAN.md)：BUG_HUNT prompt、CE 摘要、`regression_false_unknown` 驗收。

## 7. 待查問題（下一版分析）

1. 10 輪 60 條 predicate 的 **Z3 overlap / Novel%**（`pcs_per_predicate.csv`）。
2. 是否有 **injected 但仍大量 spurious** → 謂詞方向錯，非數量問題。
3. **CE_CONTEXT_PROMPT** 是否比單純加頻率更有效（first prompt 目前看不到 `x=0` 的 CE）。

---

## 8. 產物索引

| 檔案 | 說明 |
|------|------|
| `prompts/r001_first_primary.prompt.txt` | 首次 prompt（無 trace） |
| `prompts/r433_later_primary.prompt.txt` | 第 10 輪（含 trace） |
| `llm_rounds.jsonl` | 每輪 API / preds / budget |
| `refinements.jsonl` | 481 輪 refinement 詳情 |
