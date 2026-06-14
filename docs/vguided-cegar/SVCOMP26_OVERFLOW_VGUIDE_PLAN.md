# v1.6 generalization 計劃：svcomp26-overflow-vguide（Class-A，config-only）

目標：用**最低成本、零 Java、零 prompt 改動**，驗證 v1.5.1 在 reachability 證明的
predicate-CEGAR LLM hook 能不能**直接泛化到第二個 property branch（NoOverflow）**。
這是 [`LLM_RESEARCH_ROADMAP.md`](LLM_RESEARCH_ROADMAP.md) §4.2 中唯一的 **Class-A** branch，
所以是「簡單、能泛化」的最小一刀。承接 [`SVCOMP26_VGUIDE_FULLSET_PLAN.md`](SVCOMP26_VGUIDE_FULLSET_PLAN.md) 的方法論。

日期：2026-06-15。Branch：`svcomp-integration`。

**研究問題**：同一個 `useVocabularyGuide` hook，**不改 Java、不改 prompt**，套到 overflow 的 predicate 元件上，
會不會 (a) 真的 fire、(b) 0 wrong、(c) 至少救回幾題 stock 沒解的 overflow？
- yes → Class-A 泛化**實證成立**，方法可複製到其他 Class-A。
- fire 但沒贏 → 第一個 finding：「overflow 需要 prompt/context 適配」——仍遠比 Class-B 便宜，且把「config-only 夠不夠」問清楚。

---

## 0. 為什麼 overflow 是「簡單能泛化」的唯一目標（grounded）

1. **Class-A（注入點可繼承）**：overflow 的 predicate 元件
   `config/components/predicateAnalysis--overflow.properties` 內
   `#include ../includes/predicateAnalysis-PredAbsRefiner-ABEl.properties`
   ——與 reachability vguide predicate 元件**同一顆 ABEl refiner**，正是 VGuide hook 落點
   （`PredicateCPARefinerFactory` 讀 `cpa.predicate.refinement.useVocabularyGuide`）。flip 一個 option 就生效，**零 Java**。
2. **predicate child 在 overflow 更顯眼**：`config/components/parallel-overflow.properties` 只並行 **2 個** child
   （`predicateAnalysis--overflow` + `valueAnalysis-overflow--parallel`），不像 reachability 的 5-way。
   predicate 是 1-of-2 → VGuide 影響面比 reachability 更大。
3. **property-agnostic 假設**：VGuide 在 refinement 層看到的是 **spurious counterexample + program**，
   提 predicates 去 refute 那條不可行路徑；這在 refinement 層與「目標是 unreach-call 還是 no-overflow」無關。
   所以理論上同一套 machinery / prompt 不改就能用。§5 smoke test 驗證這點。
4. **chain 已存在**：svcomp26 已有完整 overflow portfolio（§1），不必新建，只做 3 個 scoped 變體。

---

## 1. 已驗證的繼承鏈（grounded）

```text
config/unmaintained/svcomp26.properties            (overflow.config = svcomp26--overflow.properties)
 └─ config/unmaintained/svcomp26--overflow.properties   (specification = ../specification/sv-comp-overflow.spc)
      restartAlgorithm.configFiles:
        ├─ ../components/parallel-overflow.properties               ← 主分析（2-way parallel）
        │     ├─ predicateAnalysis--overflow.properties             ← #include ABEl refiner = VGuide hook 落點 ★
        │     └─ valueAnalysis-overflow--parallel.properties
        ├─ ../predicateAnalysis-bam-rec--overflow.properties::if-recursive   ← recursion → BAM fallback（vguide off）
        └─ components/svcomp26--concurrency-overflow.properties::if-concurrent
```

★ = 唯一要 flip 的點；其餘逐字保留官方檔。recursion 走 BAM（Java guard 與 config 版本無關，沿用 svcomp26-vguide 既有驗證）。

---

## 2. 要建的 3 個 scoped 變體（全在 `config/unmaintained/`）

| 新檔 | 來源官方檔 | 改動 |
|---|---|---|
| `config/unmaintained/svcomp26-overflow-vguide.properties` | `svcomp26--overflow.properties` | 複製；`restartAlgorithm.configFiles` 第一項改指 `components/svcomp26-overflow-vguide--parallel-overflow.properties`；recursion / concurrency fallback 與 spec 不變 |
| `config/unmaintained/components/svcomp26-overflow-vguide--parallel-overflow.properties` | `config/components/parallel-overflow.properties` | 複製；predicate child 改指 `svcomp26-overflow-vguide--predicateAnalysis--overflow.properties`；value child 不變 |
| `config/unmaintained/components/svcomp26-overflow-vguide--predicateAnalysis--overflow.properties` | `config/components/predicateAnalysis--overflow.properties` | **不改原邏輯**，只疊 vguide：見下方 3 行 |

predicate 變體內容（疊在官方 overflow predicate 之上，不重寫其 ABEl include）：
```properties
#include ../../components/predicateAnalysis--overflow.properties
#include ../../vguide.properties
cpa.predicate.refinement.useVocabularyGuide = true
```

⚠️ 路徑 checklist（FULLSET §2 同樣 footgun；overflow 因原檔在 `config/components/` 而非 `unmaintained/components/`，更要小心）：
- 新 predicate 變體在 `unmaintained/components/`；include 官方 overflow predicate 用 `../../components/predicateAnalysis--overflow.properties`。官方檔**自身**的 `../includes/…` 相對它自己的位置 `config/components/` 解析，仍正確（CPAchecker #include 相對「含該 include 的檔」）。
- vguide include = `../../vguide.properties`（unmaintained/components → config/，與 reachability svcomp26-vguide 一致）。
- top 變體第一項用 `components/svcomp26-overflow-vguide--parallel-overflow.properties`（相對 unmaintained/）。
- 每檔複製官方原檔的 SPDX header（REUSE/license CI 會檢查）。
- 只改「指向 vguide 變體」那幾行，其餘逐字保留。
- **smoke test 必須確認 ABEl refiner 真的被 load**（log 出現 predicate refinement + VGuide round），否則路徑錯會讓 hook 靜默不生效。

---

## 3. Runner：加兩個 mode

`scripts/vguided-cegar/run.sh`（平行於現有 svcomp26-vguide，參 `run.sh:99,134-154`）：

```text
svcomp26-overflow)        VGUIDE_SVCOMP=1
                          VGUIDE_CONFIG=config/unmaintained/svcomp26--overflow.properties
                          VGUIDE_SPEC=$REPO/config/specification/sv-comp-overflow.spc
                          # stock baseline；不 require_api
svcomp26-overflow-vguide) require_api; VGUIDE_SVCOMP=1
                          VGUIDE_CONFIG=config/unmaintained/svcomp26-overflow-vguide.properties
                          VGUIDE_SPEC=$REPO/config/specification/sv-comp-overflow.spc
```

- require_api 清單（`run.sh:99`）只加 `svcomp26-overflow-vguide`（baseline overflow 不需 API）。
- `run_benchmark_set.sh` 的 SVCOMP_MODE config-name 偵測擴充涵蓋 `*svcomp26-overflow*`（svcomp 模式**不**傳全域 `useVocabularyGuide`，避免污染非 predicate 元件）。既有 mode 行為不得變。
- `bash -n` 通過。

---

## 4. Benchmark set：建 overflow manifest（目前完全沒有）

現有 manifest 都是 reachability/loops；overflow set 要新建。來源 = 官方 `.set`：

- `NoOverflows-BitVectors.set`：`signedintegeroverflow-regression/*`(15)、`termination-crafted/*`(≤117)、`termination-crafted-lit/*`(≤159)、`termination-numeric/*`(≤22)
- `NoOverflows-Other.set`：`recursive/*`(≤27)、`recursive-simple/*`(≤77)、`bitvector/*`(≤70)、`psyco/*`(≤11)、`loop-zilu/*`(≤53)

建檔（manifest 格式同 loops：`path # yml=… expected=…`，root `$HOME/sv-benchmarks/c`）：

- `docs/vguided-cegar/benchmark_sets/no_overflow_scalar.list`：解析上述 glob，**過濾 .yml 宣告 `properties/no-overflow.prp` 的**，記錄該 property 的 `expected_verdict`。實際題數 build 時定（上界 551；多數 dir 是多 property，filter 後遠少於上界）。
- `docs/vguided-cegar/benchmark_sets/no_overflow_pilot.list`（**先跑**）：`signedintegeroverflow-regression/*`（15 題、100% no-overflow、canonical regression，TRUE/FALSE 都有）。最快證 hook 在 overflow fire + 0 wrong。

註：`recursive*/*` 會 route 到 `predicateAnalysis-bam-rec--overflow::if-recursive`（BAM fallback、vguide off）。保留無妨（soundness 已驗），但不貢獻 vguide signal——分析時要排除在 "vguide-eligible" 子集外。

---

## 5. Smoke test（建 config + manifest 後、跑 full 前；任一不過就停）

1. **hook fire**：1 題會觸發 LLM 的 non-recursive overflow（signedintegeroverflow-regression 內 expected=true 者）`--mode svcomp26-overflow-vguide` → log 出現 `svcomp26-overflow-vguide--predicateAnalysis--overflow.properties` + `VGuide LLM round`，verdict 正確。**← 核心泛化證據**。
2. **FALSE 不誤判**：1 題 expected=false overflow → verdict FALSE 正確（0-wrong 前哨）。
3. **recursion 安全**：1 題 recursive overflow → BAM fallback WARNING、無 vguide log、不 crash。
4. **可歸因**：同 (1) 題 `--mode svcomp26-overflow`（stock）對照，確認 baseline vs vguide 差異能乾淨歸因。

---

## 6. Baseline + full-set 執行

overflow 沒有現成 baseline → **兩個 arm 都要跑**：`svcomp26-overflow`（stock）與 `svcomp26-overflow-vguide`。

- set：先 `no_overflow_pilot`，過了再 `no_overflow_scalar`
- timelimit 300s、parallel 6、heap 4000M（指令格式同 FULLSET §4，換 mode/set/out）
- nohup detached

---

## 7. 分析與報告（soundness FIRST）

報告 `docs/vguided-cegar/reports/<DATE>_svcomp26_overflow_vguide.md`：

1. **0 wrong 第一**：對每題 .yml `expected_verdict` 掃 wrong。**overflow 有大量 FALSE 題，這關比 reachability 更關鍵**；任何 wrong = blocker，高亮 + 保 log。
2. Topline：stock vs vguide（TRUE/FALSE/UNKNOWN/Solved/Wrong/PAR-2）。
3. Overlap/delta：new / lost / disagreements / net。
4. **VGuide fire 證據**：用 `attribute_svcomp_verdicts.py` 統計多少 overflow 題的 predicate 元件 `llm_rounds>0`。**這是泛化的直接證據**。
5. **Direct LLM wins**：vguide solved 但 stock 沒、且 decider = overflow vguide predicate 元件且 `llm_rounds>0`。≥1 即證 hook 在新 branch 有實效。
6. **prompt 適配觀察**：若 LLM 對 overflow 只給 reachability 式 loop invariant 而非 bound/range predicate 且沒用，記為「overflow 需 prompt/context 適配」的第一個 finding。

---

## 8. Acceptance（v1.6 Class-A 泛化判定）

v1.6 的 claim 不是「+N 題」，是「**hook 泛化是否成立**」：

- **0 wrong**（hard gate）。
- VGuide 在 overflow predicate refinement **確實 fire**（≥ 數題 `llm_rounds>0`）。
- **≥1 direct LLM-decided new solve** on overflow（證非 inert）。
- 無大量 stable lost solves（resource 噪音除外，診斷沿用 FULLSET 方法）。

達標 → roadmap §4.2 標「Class-A 泛化已實證，方法可複製」。
fire 但未贏 → 記錄「config-only 不足、需 prompt/context 適配」，**這本身就是 v1.6 的有效結論**。

---

## 9. 風險 / 什麼會推翻假設

| 風險 | 症狀 | 緩解 |
|------|------|------|
| predicate child 在 overflow 很少 decide（value child 先解）| vguide 沒機會 fire | pilot 先看 attribution；必要時看 predicate-only 子集 |
| prompt 非 property-agnostic | LLM predicate 對 no-overflow 沒用 | 降級為「config + 小 prompt 改」，仍遠比 Class-B 便宜 |
| 路徑 footgun | ABEl refiner 沒 load、hook 靜默 | §5 step 1 專門擋；確認 log 有 refinement + VGuide round |
| overflow FALSE 題誤判 | wrong verdict | predicate 是 Tier S（over-approx 只會讓 proof 失敗、不誤判 FALSE）；§7.1 硬驗 |

---

## 10. 工作順序

1. 建 §2 的 3 個 config（注意 `../../` 路徑）。
2. §4 manifest（先 `no_overflow_pilot`）。
3. §3 runner 兩 mode + `bash -n`。
4. §5 smoke（4 步，含 recursive）。
5. pilot full → 看 §8 是否 fire + 0 wrong。
6. 過了再跑 full scalar NoOverflow + §7 報告。
7. 全程不改 Java、不改 `vguide.properties` prompt（除非 §8 finding 要求）、不改官方 svcomp26/27 檔、不 merge main。

---

## 11. 實作狀態

| 項目 | 狀態 |
|------|------|
| 3 個 svcomp26-overflow-vguide config | TODO |
| Runner 兩 mode | TODO |
| overflow manifest（pilot + scalar）| TODO |
| Smoke test（4 步）| TODO |
| Pilot + full-set | TODO |
| 報告 | TODO |
