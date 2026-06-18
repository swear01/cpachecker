# Termination Ranking-Function Hook 計劃（v2.0，Class-B）

把 v1.5 對 predicate 做的事（LLM 提候選 → sound engine 驗證後才用，Tier S）平移到 **termination**：
候選 artifact 從「predicate 原子」換成「**ranking function `f` + 其 supporting invariant `I`**」，
驗證從「會發散的 CEGAR refinement」換成「**四個 SMT UNSAT 查詢**（`I` inductive + `f` 在 `I` 下 ranks）」。
開的是 VGuide 目前 **0 分**的 termination category。

- **承接**：[`LLM_RESEARCH_ROADMAP.md`](LLM_RESEARCH_ROADMAP.md) §3.1 / §4.2（Termination lasso 路標為最高槓桿新 category）、
  [`SVCOMP26_TERMINATION_VGUIDE_PROBE.md`](SVCOMP26_TERMINATION_VGUIDE_PROBE.md)（safety-reduction 路 **RED** → 本計劃走 lasso 路）
- **Class**：B（要寫 Java sound 注入 hook；非 config-only）
- **Soundness tier**：S（LLM 只提候選 `(I, f)`，四個 SMT 檢查全過才採用；猜錯只浪費 CPU，永不產生錯 verdict）

---

## 0. 目標一句話

當 LassoRanker 的 template-based ranking-function 合成對某 loop **失敗（UNKNOWN）**時，讓 LLM 讀 loop 源碼提出
候選 **ranking function `f` 與其 supporting invariant `I`**；用四個 SMT UNSAT 查詢驗證（`I` 是 inductive、
且 `f` 在 `I` 下嚴格遞減且有下界）；通過者轉成 `RankingRelation` 餵回既有 `TerminationAlgorithm`，**下游零改動**。

> **v1 即含 supporting invariant 協同**（決策：2026-06-17）。`I` 是 optional，預設 `true`——`I=true` 時四檢查
> 退化成原本的兩檢查（純 `f`）。這樣 v1 同時涵蓋「需要 supporting invariant」與「不需要」兩類，且 `I` 一律
> 經 inductive 驗證、非假設，soundness 不變。

---

## 1. 背景：CPAchecker 現在怎麼證 termination（lasso 路，逐檔確認）

頂層 `TerminationAlgorithm.proveLoopTermination(loop)`（`core/algorithm/termination/TerminationAlgorithm.java:309`），
對每個 loop 跑「逐 lasso 排除」迴圈（`:327`）：

1. safety analysis 找一條 **lasso**（stem 進 loop + cycle 回 loop head）＝一條可能不終止的執行（`:330`–`:355`）。
2. `lassoAnalysis.checkTermination(loop, counterexample, relevantVariables)`（`:354`）。
3. 結果 `LassoAnalysisResult` 三態：non-termination → `FALSE`（`:357`）；termination（一個 `RankingRelation`）→
   排除此 lasso、加 invariant、reset 找下一條（`:364`–`:374`）；unknown → 最終 `UNKNOWN`（`:387`）。

合成在 `LassoAnalysis.synthesizeTerminationArgument`（`lasso_analysis/LassoAnalysis.java:487`）：
template 迴圈（`:493`）→ `TerminationArgumentSynthesizer.synthesize()` 解 Motzkin/Farkas 填係數（`:500`）→
SAT 則 `rankingRelationBuilder.fromTerminationArgument`（`:514`）→ push 檢查（`:518`）→ 回 result；全失敗回 `unknown()`（`:537`）。

### 1.1 天花板：ranking function 只能來自固定 template

`createTemplates`（`:363`–`:373`）只放 `AffineTemplate`（線性）+ `NestedTemplate(2..maxTemplateFunctions=3)`。
LassoRanker 在此 template 家族內 correct-by-construction，**但 template 表達不出來的 measure 直接 UNKNOWN**——
這就是 headroom（需要 case split / 相位 / 變數間關係較間接的 measure，或需要 supporting invariant 才證得出 decrease）。

---

## 2. 這個 idea：LLM 當 `(ranking function, supporting invariant)` 候選提供者

在 `synthesizeTerminationArgument` 即將回 `unknown()`（`:537`）前，加一個 LLM fallback。

```
                 ┌─ template synthesizer (現有, correct-by-construction)   ── SAT → 採用
 lasso (stem+loop)┤
                 └─ [新增] template 全失敗時 → LlmRankingFunctionProvider
                        │  context: loop 源碼 + relevantVariables + stem/loop transition 摘要
                        │  問:「給 measure f(x) + （需要時）supporting invariant I(x)」
                        ▼
                 對每個候選 (I, f)，I 預設 true:
                   initiation : isUnsat( Stem ∧ ¬I@entry )            // stem 建立 I（I=true 時平凡通過）
                   consecution: isUnsat( I(x) ∧ T(x,x') ∧ ¬I(x') )    // I 被 loop 保持（inductive）
                   bounded    : isUnsat( I(x) ∧ T(x,x') ∧ f(x)  < 0 ) // I 下 f 有下界
                   decrease   : isUnsat( I(x) ∧ T(x,x') ∧ f(x') ≥ f(x))// I 下 f 嚴格遞減
                        ▼
            四個都 UNSAT → (I,f) sound 證此 lasso 終止
                         → 建 RankingRelation(+supportingInvariant) → fromTerminationArgument
                         → 下游 TerminationAlgorithm 照常排除這條 lasso（零改動）
            任一不過 / parse 失敗 → 丟掉候選（猜錯只浪費 CPU）
```

**為什麼結構上避開 overflow/loops 撞的 wall**：predicate 路卡在「atom 組不成收斂的 inductive invariant，CEGAR
refinement 發散」（[`SVCOMP26_OVERFLOW_VGUIDE_IMPROVEMENT_PLAN.md`](SVCOMP26_OVERFLOW_VGUIDE_IMPROVEMENT_PLAN.md) §8）。
ranking 檢查**沒有 refinement、沒有 fixpoint、沒有收斂問題**：一次猜 → 四個 UNSAT → 當場有答案。

**為什麼不會慢（fast model 就夠）**：LLM **只在 template 失敗的 loop 上、每 loop 一次**被呼叫（fallback gating），
輸出是短表達式（`f` + 選用 `I`）；驗證是本地 SMT。比 predicate 路（跨多輪 refinement、每輪等 LLM）更省 latency。不需 thinking mode。

---

## 3. Feasibility probe 結果：**GREEN**（純讀 code 已確認）

| 問題 | 結論 | 證據 |
|------|------|------|
| stem / loop transition 拿得到 JavaSMT `BooleanFormula`？（不碰 Ultimate `Term` 翻譯）| **是** | `LassoBuilder.StemAndLoop.getStem()` / `getLoop()` 回 `BooleanFormula`（`lasso_analysis/construction/LassoBuilder.java:462`/`:474`）；由 `pathFormulaManager` 建（`:217`–`:236`）|
| primed/unprimed (`x` vs `x'`)？ | **有，且 stem-out 與 loop-in index 對齊** | `getLoopInVars()`/`getLoopOutVars()` 回 `SSAMap`（`:478`/`:482`）；loop-in 由 stem 末 SSA 起算（`:222`），故 stem-out=loop-in，initiation 可接 |
| UNSAT 原語？ | **有** | `LassoBuilder.isUnsat(BooleanFormula)`（`:287`–`:291`）；或 `solverContext.newProverEnvironment()`（`LassoAnalysis.java:513`）|
| 怎麼把 `f`/`I` 建成 formula、render RankingRelation？ | **有現成樣板** | `RankingRelationBuilder`（`RankingRelationBuilder.java`）：建 primed/unprimed `NumeralFormula` 加總（`createRankingRelationComponents:257`）、組 decrease+bounded（`createRankingRelationFormula:404`）、`withSupportingInvariants`（`RankingRelation.java:155`）|
| LLM 字串 → formula parser？ | **有，可鏡像** | `VocabularyGuide.parsePredicate` / `parseSexp`（boolean 用；`PredicateValidationPipeline.java:60`）→ 鏡像 numeric-term parser |
| VGuide orchestration 可重用？ | **可整套平移** | `cpa/predicate/vguide/`：`VGuideRefinementBridge`、`ContextPack(Builder)`、`PredicateProposalClient`、`LlmCallScheduler`、`VGuideAnalysisDumper`、`VGuideOptions` |

**結論**：四個檢查可**純在 CPAchecker/JavaSMT 側**建（tap `StemAndLoop`，不碰 Ultimate `Lasso`/`Term`）。原先擔心的 formula translation gap **不存在**。

---

## 4. 架構：hook 插哪、資料怎麼流

### 4.1 注入點（seam）

`synthesizeTerminationArgument`（`:487`）目前只有 Ultimate `Lasso`，**沒有** JavaSMT `StemAndLoop`。要把 stem/loop
`BooleanFormula` + in/out `SSAMap` 帶進來：

1. `LassoBuilder.buildLasso(...)`（`:155`）目前回 `Collection<Lasso>`；內部已建出 `StemAndLoop`（`:160`）→ 改成同時暴露它。
2. `LassoAnalysis.checkTermination0`（`:403`）拿到 `StemAndLoop` + `pRelevantVariables` 後往下傳到 `synthesizeTerminationArgument`。
3. template 全失敗（落到 `:537` 前）→ 呼叫 `LlmRankingFunctionProvider.tryProve(loop, stemAndLoop, relevantVariables)`。

> **Gating（fallback-only）**：只在 template 全失敗時 fire，套 `LlmCallScheduler` 的 min-interval / max-rounds-per-loop，
> 避免同一 loop 多條 lasso × 多輪 iteration 過度呼叫。

### 4.2 新增元件（鏡像 `cpa/predicate/vguide/`；建議放 `lasso_analysis/vguide/`）

| 新元件 | 對應 predicate 路 | 職責 |
|---|---|---|
| `LlmRankingFunctionProvider` | `VGuideRefinementBridge` | orchestration：打包 context → 呼叫 LLM → parse `(I, f)` → 逐候選驗證 → 回 `LassoAnalysisResult` |
| `RankingContextPack(Builder)` | `ContextPack(Builder)` | loop 源碼片段、relevant variables、stem/loop transition 摘要 |
| `RankingProposalClient` | `PredicateProposalClient` | DeepSeek API（**可直接重用** `PredicateProposalClient`，換 prompt/JSON schema）|
| `RankingFunctionVerifier` | `PredicateValidationPipeline` | **核心**：建 `f(x)`/`f(x')`/`I(x)`/`I(x')`、跑 §4.3 四個 UNSAT |
| `RankingTermParser` | `VocabularyGuide.parsePredicate` | LLM 字串 → `IntegerFormula`（`f`）/ `BooleanFormula`（`I`），鏡像 `parseSexp` |
| `RankingAnalysisDumper` | `VGuideAnalysisDumper` | dump 候選 / 驗證結果 / 採用情況，供 attribution |
| options（`@Options(prefix="termination.lassoAnalysis.vguide")`）| `VGuideOptions` | 開關、scheduler 參數、model |

### 4.3 驗證器 `RankingFunctionVerifier`（核心）

輸入：候選 `f`（→`IntegerFormula`）、`I`（→`BooleanFormula`，預設 `true`）、stem `BooleanFormula`、loop `BooleanFormula` `T`、
`stemOutVars`(=`loopInVars`)/`loopInVars`/`loopOutVars`（`SSAMap`）。

```
I_pre  = instantiate(I, loopInVars)    f_pre  = instantiate(f, loopInVars)    // (x)
I_post = instantiate(I, loopOutVars)   f_post = instantiate(f, loopOutVars)   // (x')

initiation : isUnsat( Stem ∧ ¬I_entry )                 // I_entry = I @ stemOut=loopIn
consecution: isUnsat( I_pre ∧ T ∧ ¬I_post )
bounded    : isUnsat( I_pre ∧ T ∧ (f_pre  <  0) )
decrease   : isUnsat( I_pre ∧ T ∧ (f_post ≥ f_pre) )

valid = initiation ∧ consecution ∧ bounded ∧ decrease     // I=true → 前兩者平凡 UNSAT
```

`instantiate` 用 `FormulaManagerView`（把無 index 的 `f`/`I` 綁到指定 SSAMap index）；`isUnsat` 用既有 prover。
通過後鏡像 `RankingRelationBuilder` 產 `RankingRelation`，`.withSupportingInvariants(I)` → `fromTerminationArgument`。

---

## 5. 驗證條件與 soundness（Tier S）

### 5.1 數學（標準、sound）

對 loop transition `T(x,x')`，`(I, f)` 證此 lasso 終止當：
1. **Initiation**：`Stem ⟹ I@entry`（stem 後 `I` 成立）
2. **Consecution**：`I(x) ∧ T(x,x') ⟹ I(x')`（`I` inductive）
3. **Bounded**：`I(x) ∧ T(x,x') ⟹ f(x) ≥ 0`
4. **Decrease**：`I(x) ∧ T(x,x') ⟹ f(x') < f(x)`

1+2 ⇒ `I` 在每次 loop 執行都成立；在 `I` 下 3+4 ⇒ `f` 映到良基域（非負整數）且嚴格遞減 ⇒ 此 lasso 上 loop 不可能無限執行 ⇒ 終止。

### 5.2 為什麼永不產生錯 verdict

- LLM 輸出**從不直接當 verdict**，只擴大候選來源。
- `I` **被驗證為 inductive（非假設）**：LLM 給的 `I` 若非 inductive，consecution 檢查失敗 → 整個候選 reject。
- 任何候選必過 §5.1 四檢查（驗證者是 SMT solver，ground truth）；猜對 → sound proof，猜錯 → 擋下，最壞浪費 CPU。
- 下游把 verified `(I,f)` 當 invariant 加入並排除 lasso：因已驗證為真，sound；即使偏弱最壞只是 non-progress → UNKNOWN，**不會變成錯的 TRUE**。

> **0-wrong gate**：本 hook **只動 termination-argument（TRUE 方向）**，完全不碰 `synthesizeNonTerminationArgument`（`:463`）。
> FALSE（non-terminating）判定路徑零改動。

---

## 6. Config / 選項

vguide 實驗 config 已建：[`config/vguide-experiment-termination.properties`](../../config/vguide-experiment-termination.properties)
（include lasso-only base；vguide 選項先註解，**Java hook 落地（Phase 6）同一個 change 才取消註解**，否則 unknown-option 載入失敗）：

```properties
termination.lassoAnalysis.vguide.enabled = true     # 預設 false；不開＝現狀逐位元不變
termination.lassoAnalysis.vguide.mode = fallback     # 只在 template 失敗才 fire
termination.lassoAnalysis.vguide.maxRoundsPerLoop = 1
```

⚠️ **option 傳播待驗**：`termination.config` 在 lasso config 內是自指（`termination-composition-lassoBasedAnalysis.properties`）。
`termination.lassoAnalysis.vguide.*` 由 `LassoAnalysis`（`TerminationAlgorithm.java:214` 建）讀；需在 Phase 6 確認頂層設的選項
確實傳達到該 `LassoAnalysis` 實例（自指 config 重載的子分析可能讀不到）。

---

## 7. 實驗 harness（**已備好並實證**，2026-06-17）

| 項目 | 內容 | 狀態 |
|------|------|------|
| Benchmark set | [`benchmark_sets/termination_scalar.list`](benchmark_sets/termination_scalar.list)：termination-crafted + crafted-lit + numeric，**146 題（125 terminating / 21 non-term）**。大目錄（product-lines 597、eca 200）是 reactive system、非 ranking-function 目標 → 排除 | ✅ 生成、抽查存在 |
| Smoke set | [`benchmark_sets/termination_smoke_2.list`](benchmark_sets/termination_smoke_2.list)：1 true + 1 false | ✅ |
| Stock config | `config/components/termination-composition-lassoBasedAnalysis.properties`（**lasso-only**，隔離 lasso 路，非 svcomp27 parallel portfolio）| ✅ standalone 跑出 TRUE |
| VGuide config | `config/vguide-experiment-termination.properties` | ✅ skeleton（選項待 Java）|
| run.sh modes | `--mode termination-stock` / `termination-vguide`（output→`${set}_termination_{stock,vguide}`）| ✅ wired |
| **Smoke 實證** | `run.sh cpa --set termination_smoke_2 --mode termination-stock --timelimit 30`：BradleyMannaSipma-CAV2005-Fig1-modified → **FALSE**（expected false ✓）、AliasDarteFeautrierGonnord-SAS2010-Fig1 → **TRUE**（expected true ✓），**0 wrong** | ✅ 端到端通過 |

**harness 三個必要設定（已 wire 進 run.sh termination 模式，逐一驗證生效）**：
- `VGUIDE_SPEC=`（空）：termination config 用內建 automata；若帶 `default.spc` 會 override 並破壞 termination 偵測。
- `VGUIDE_USE_VOCABULARY_GUIDE=false`：termination 內部 safety analysis 是 predicate-based，若 on 會啟動 **reachability** VGuide 混淆 ranking hook。
- `--option analysis.machineModel=Linux64`：這三家族全 LP64；harness 預設 ILP32，int 寬度錯可能翻 termination verdict（**0-wrong 風險**）。

baseline 跑法（stock，可立即跑；Phase 0）：

```bash
SV_BENCHMARKS=~/sv-benchmarks/c ./scripts/vguided-cegar/run.sh cpa \
  --set termination_scalar --mode termination-stock --timelimit 300 --parallel 6
```

---

## 8. 實作 Phase — **全部完成（2026-06-17）**

結果報告：[`reports/2026-06-17_termination_ranking_hook.md`](reports/2026-06-17_termination_ranking_hook.md)
— termination_scalar 146 題 @60s：stock 80 → **vguide 83（+3 / 0 lost / 0 wrong）**，3 個 verified LLM ranking function
（含 1 個需 supporting invariant：`f=y1+y2`, `I=(y1>0 ∧ y2>0)`）。

```
Phase 1  ✅ LassoBuilder.createStemAndLoop 公開 + buildLasso(StemAndLoop,..) overload；checkTermination0 build StemAndLoop 並下傳
Phase 2  ✅ RankingFunctionVerifier（4 UNSAT 檢查）+ RankingFunctionVerifierTest（4 tests，含 I 必要性 case）
Phase 3  ✅ RankingTermParser（LinearTerm 核心，整數 linear，拒非線性/未知變數）+ RankingTermParserTest（10 tests）
Phase 4  ✅ 直接重用 PredicateProposalClient（未另建 RankingProposalClient）；ranking prompt 內建於 provider（system+user, JSON）
Phase 5  ✅ context = 全 source（cfa.getFileNames）+ relevant vars + loop function；built in provider
Phase 6  ✅ LlmRankingFunctionProvider 串起；gating 自製（每 loop ≤1、全程 ≤200，env 控）；**改用 env `VGUIDE_TERMINATION_RANKING=on`**（非 config 選項 → 繞過 §6 的 option 傳播風險，該風險已 moot）
Phase 7  ✅ attribution 用 provider INFO log（`verified LLM ranking function ...`）；未另建 dumper class（log 足夠）
Phase 8  ✅ run.sh `termination-stock`/`termination-vguide` mode；full-set stock+vguide 跑完；0-wrong gate 通過
```

**與計劃的偏離（誠實記錄）**：(1) 啟用改用 env flag 而非 `termination.lassoAnalysis.vguide.*` config 選項——更簡單且避開
termination.config 自指的 option 傳播問題（§6 ⚠️ 因此 moot；`vguide-experiment-termination.properties` 的註解選項保留但未使用）。
(2) 未另建 `RankingProposalClient`/`RankingContextPackBuilder`/`RankingAnalysisDumper` class——直接重用
`PredicateProposalClient`、prompt/context/attribution 內建於 provider，減少表面積。soundness 設計（§4.3/§5）逐字實作。

**verifier 先行原則成立**：Phase 2 的 4-check verifier 先用手寫 `(I,f)` 單元測試鎖定（polarity、整數遞減、I=true 退化、
supporting-invariant 必要性），才接 LLM——full run 的 3 個 win 全部通過該 verifier。

---

## 9. Acceptance gate（每階段硬條件）

| Gate | 條件 |
|------|------|
| **Soundness（硬）** | termination set **0 wrong verdict**（已對 smoke 的 1 true+1 false 驗證方向正確）；FALSE 路徑零 regression |
| 回歸 | hook 關閉時 termination 結果逐位元不變；開啟時 **0 new lost**（template 本來解掉的不可變 UNKNOWN）|
| 增益 | template 失敗的 loop 有 LLM-only 新 solved；**全部可 attribution**（dump 標 llm-decided）|
| 成本 | LLM 只在 fallback fire；per-loop 呼叫受 scheduler 約束；wall 不爆 |

---

## 10. 風險與緩解

| 風險 | 緩解 |
|------|------|
| LLM 給的 `I` 非 inductive / `f` 在 `I` 下仍不遞減 | consecution / decrease 檢查 reject（sound，只浪費 CPU）|
| LLM 給非線性 / 含 array / pointer 的 `f`/`I` → parse 或 verify 不了 | parser reject 不支援形狀；`RankingRelationBuilder.getVariable`（`:352`）已示範哪些 term 不支援（array/binary op）→ 比照 |
| polarity / 整數遞減量慣例搞錯 → verifier 誤判 | Phase 2 手寫已知 case 單元測試鎖定；對照 `createRankingRelationFormula`（`:404`）既有編碼 |
| option 傳播：自指 `termination.config` 子分析讀不到 vguide 選項 | Phase 6 明確驗證（§6 ⚠️）；必要時改傳遞方式 |
| 過度呼叫 LLM 拖慢 | fallback-only + `LlmCallScheduler`；只打 template 失敗的 loop |
| 機器模型：LP64 任務跑成 ILP32 → 翻 verdict | **已處理**：termination 模式自動加 `analysis.machineModel=Linux64`（§7）|

---

## 11. Non-goals / 延後

- **Non-termination（FALSE）候選**：本計劃只做 termination-argument（TRUE）。
- **Recursion / terminationToSafety 路**：只走 lasso 路；safety-reduction 路 probe 已 **RED**（[probe](SVCOMP26_TERMINATION_VGUIDE_PROBE.md)）。
- **取代 LassoRanker**：不取代；LLM 只當 template 失敗後的 fallback provider。
- **多 supporting invariant / 非線性 measure**：v1 先做單一 `I` + 可線性化的 `f`；更複雜形狀視 Phase 2 parser/verifier 能力再擴。

---

## 12. 一句話

lasso 路的 ranking-function 合成有現成「候選 → SMT 驗證」骨架（`synthesizeTerminationArgument`），stem/loop transition 在
JavaSMT 側就拿得到（`StemAndLoop`），verifier 是四個 UNSAT 查詢（§5.1，含 supporting-invariant 協同），VGuide orchestration 整套可平移，
**實驗 harness 已備好並 smoke 通過（§7）**。Class-B 但 GREEN、soundness 乾淨、fast model 夠用、latency 低——
VGuide 從 predicate provider 泛化成 ranking-function provider。

---

## 13. Headroom 診斷（2026-06-18，56-target subset）+ lever 排序

對 56 個 stock-UNKNOWN-terminating 目標跑診斷版（provider 每次 fire log `proposed=/outcomes=`，verifier 回報哪個 check 失敗）。
子集 list：`benchmark_sets/termination_targets.list`。分布：

| 桶 | 數 | 說明 |
|----|---:|------|
| **hook FIRED**（產出 lasso + template 失敗 → hook 真的跑）| **9** | 贏 4 / 沒贏 5 |
| **快速 UNKNOWN（~1s）→ 無 lasso** | **40** | 指標/陣列/字串（`cstr*`/`strchr`/`Arrays*`）；termination 演算法在產出 lasso 前就 give up（`termination arguments: 0`）→ **hook structurally 碰不到**（`checkTermination0` 從未被呼叫）|
| **接近 timeout（≥55s）** | **7** | 分析還在跑，沒走到 fallback |

9-fired 的 5 個沒贏，候選失敗類型統計：**BOUNDED_FAILED×8、INITIATION_FAILED×5、DECREASE_FAILED×2**。
實際候選如 `x | true`、`(- x) | true`、`(+ x y) | true`——**LLM 給了 measure 但沒給「建立下界」的 supporting invariant**
（`x` 要證 `≥0` 需 invariant，卻給 `true`）。

### Lever 排序

- **便宜（已實作 + 實測，2026-06-18）= NEUTRAL**。三方對照（56-target subset，verify→repair + verifier `Outcome` 診斷）：

  | Config | WON | first | repair | 備註 |
  |--------|----:|------:|-------:|------|
  | baseline（原 prompt, plain source, 無 repair）| **4** | 4 | — | 最佳 |
  | 「強化」prompt（強推 invariant）+ repair | 3 | 1 | 2 | INITIATION 5→~20 |
  | 原 prompt + repair | 4 | 4 | 0 | repair +0 |
  | 原 prompt + repair + **stem facts in prompt** | **2** | 2 | 0 | 更差；INITIATION ~25 |

  結論（全部 **≤ baseline 4**）：(a) 「強化」prompt（強推 boundedness/invariant）**變差**（4→3）→ **已還原**；
  (b) **repair +0**——first round 已抓到 9 個 fired loop 裡所有能贏的（4/9）；
  (c) **stem facts（raw SSA SMT 傾印）放進 prompt 反而最差（2）**——SSA 雜訊讓 LLM 更難、又排擠 source；INITIATION 不降反升 → **已還原**。
  → **預設 = baseline 最佳 config**（plain source + 原 prompt, repair OFF, 無 stem）。repair 與診斷 log/verifier `Outcome` 保留（repair 預設 OFF, `..._REPAIR=on` 才開）。

- **教訓**：對這個 set，**「加 context / 加指示」一律讓 LLM 變差，乾淨 source + 簡單 prompt 最好**。純候選品質的 cheap lever（prompt/repair/stem-dump）
  **全部到頂**（=overflow P1 的翻版）。fired-no-win 的 5 個 loop 失敗橫跨 INITIATION/BOUNDED/DECREASE/CONSECUTION，
  是 single-shot 線性 ranking function 本質上搞不定，不是 context 不足。
  - 若仍要追 INITIATION：需**source-level（非 raw SSA）的入口條件**表示法（更貴、不確定），非本次的便宜嘗試。

---

## 14. 失敗 levers 記錄（不要重試這些便宜路，2026-06-18）

全部在 56-target subset 上實測（每次 ≤1 LLM call/loop，repair 時 +1）。baseline（plain source + 原 prompt）= **WON 4**。

| 試過的 lever | 結果 | 為什麼失敗 |
|--------------|------|-----------|
| **prompt 強推 boundedness/invariant**（「f 必須可證 ≥0，否則必須附 invariant」+ `(<= i n)` 範例）| 4→**3** | LLM 被逼著猛加 invariant，但那些在 loop 入口不成立 → `INITIATION_FAILED` 5→~20 |
| **verify→repair loop**（verifier 回報哪個 check 掛 → 回餵 LLM 修一輪）| 原 prompt 上 **+0** | first round 已抓到 9 個 fired loop 裡所有能贏的（4/9）；repair 沒救回任何一個 |
| **stem facts in prompt**（raw SSA-indexed SMT 傾印當「入口事實」）| 4→**2** | raw SSA SMT 對 LLM 是雜訊、又排擠 source code；INITIATION 不降反升到 ~25 |

**共通教訓：對這個 set，「加 context / 加指示」一律讓 LLM 變差；plain source + 簡單 permissive prompt（baseline）最佳。**
純候選品質的 cheap lever 全部到頂（=overflow P1 的 +0 翻版）。

**結構性瓶頸（非候選品質，便宜路救不了）**：56 個 stock-UNKNOWN 目標裡 **40 個根本沒讓 hook 上場**
（pointer/array/string loop，lasso safety analysis 在產出 lasso 前就 give up，`checkTermination0` 從未被呼叫）。
fired 的 9 個裡 4 個贏、5 個失敗橫跨 INITIATION/BOUNDED/DECREASE/CONSECUTION（single-shot 線性 ranking 本質搞不定）。

**尚未試 / 仍開放**（都不便宜）：
- source-level（非 raw SSA）的 loop 入口條件表示法 — 唯一可能救 INITIATION 的，但要做 ce-summary 級的萃取，不確定。
- **更早的注入點** 救那 40 個 never-fired（v2.1 結構改動，真正的大 headroom）。
- 更強 reasoning model（user 已否決：太慢、無實際價值）。

**現行 code 狀態**：預設 = baseline（plain source + 原 prompt、repair OFF、無 stem）。verifier `Outcome` + 診斷 log 保留；
repair 為 env opt-in scaffolding（`VGUIDE_TERMINATION_RANKING_REPAIR=on`），其唯一活路（stem context）已失敗，價值待 source-level 入口表示法。

---

## 15. 最終結論（verdict, 2026-06-18）

termination ranking-function hook：**已實作、sound、小幅乾淨增益**——孤立 lasso branch **300s +4（60s +3）、0 wrong / 0 lost**，
在 scoped、對 hook 最有利的整數 termination set（146 題）上。誠實上限：

- **天花板小**：cheap 候選品質 lever 全用盡（§13–14，prompt/repair/stem 全 ≤ baseline）；56 個 stock-UNKNOWN 目標只 9 個 fire，
  **40 個結構性碰不到**（pointer/array/string，hook 從未上場）。
- **競賽淨增益 ≤ 孤立值、且（決定）不量**：真實 branch 是 `terminationToSafety ∥ lasso`；terminationToSafety **無 AI 路徑**
  （probe RED）、並行跑 stock，會覆蓋部分 win。增益本來就小，量了不改結論。
- **對未來 LLM 介入的啟示**（user 判斷）：這個介入點（lasso branch 的 ranking function）**天花板小**。更高槓桿的機會在別處——
  救那 40 個 never-fired 的**結構性更早注入**，或**換 category / 換機制**。hook 以 sound、opt-in、零預設成本的 **building block** 留著，**不當 headline 結果**。

**未繼續**：competition-net 量測（`svcomp27--termination` stock vs +hook）、300s 以外的 tuning、結構性更早注入——皆 backlog。

- **貴（記下、之後做）= 真正的大 headroom**：40/56 是 pointer/array/string loop，lasso safety analysis 在產出 lasso 前
  就 give up，hook 無從 fire（`checkTermination0` 從未被呼叫）。要贏需 **更早的注入點** 或讓 safety analysis 處理 pointer/array。
  屬 **v2.1+ 結構改動**。標記於 roadmap backlog。

- **時間**：7 個 timeout → 300s full run 會自然吃掉幾個（非程式 lever）。

**含意**：純候選品質的 cheap lever（prompt/repair）在這個 set 上**到頂了**（=overflow P1 的翻版：+0）。
真正的 headroom 一是**結構面**（40 never-fired，貴），二是**給 LLM stem context 修 INITIATION**（中等，下一步）。
