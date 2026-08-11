# Combined Class-A VGuide @300s（competition-grade，2026-06-16）

把兩個已驗證的 VGuide Class-A category 在**競賽級 300s CPU 時限**、同 jar（v1.6.0）、parallel 6、path-keyed 下一起量。
透過 unified `svcomp26-vguide` config（一個 config 同時 route reachability + overflow）。

## 結果（分 category —— SV-COMP 本來就分 category 計分）

| Category | set | stock | vguide | net | new | lost | wrong（stock/vguide）|
|----------|-----|------:|-------:|----:|----:|-----:|---|
| **Reachability** | Loops 764 | 479 | **494** | **+15** | 16 | 1 | 0 / 0 |
| **NoOverflow** | 452 | 362 | **366** | **+4** | 4 | 0 | 0 / 0 |

> aggregate（方便看的加總，**不是**單一 SV-COMP 指標）：stock 841 → vguide 860，**+19 / 20 new / 1 lost / 0 wrong**。

## 誠實 caveat

1. **時限敏感**：overflow 在 120s 是 +6，到 **300s 縮成 +4**。給更多時間，baseline 自己追上 2 題（stock 357→362）；
   剩下 **4 題是 stock 連 300s 都解不掉、只有 VGuide 解出**的穩健 VGuide-only 解。reach 在 300s 是 +15。

2. **「免費 LLM 時間」量化後很小**：VGuide 的 new-win 都很快 —— reach median **7.0s**（max 76.8s）、overflow median **4.4s**；
   **0/20 個 win 的 wall 超過 300s**。所以 VGuide **不是靠「燒超出 CPU 預算的 LLM 延遲」贏的**。
   CPU 時限藏 LLM 延遲的優勢理論上存在，但在這些 win 上沒實際發生。

3. **非競賽情境**：用外部 DeepSeek API（真實 SV-COMP 網路隔離 → 需 local model）；CPU 時限（真實比賽也有 wall 限制）。

4. **不可跟公佈的 486 比**：那是 parallel 1（每題吃滿機器）；這裡 parallel 6 → fresh stock 是 **479**。

5. **run-to-run 變異**：reach v1.5.1 跑是 +7、這次 +15（LLM 非確定性 + portfolio timing）。單跑 delta 有噪音。

## 淨結論

競賽級 300s、同條件、**0 wrong**：VGuide 在兩個 Class-A category 都給乾淨、sound 的邊際正增益
（**reach +15、overflow +4 穩健**），由**單一 unified config** 完成，win 是快速 sound 的解、不是靠超時。
保守邊界：外部 API 非競賽、增益隨時限/跑次變動。

## Provenance

- 4 arm，同 jar（HEAD @ `ea72385d64` / `vguide-v1.6.0`），300s CPU + 420s wall，parallel 6：
  - `output/vguide/experiments/combined300_loops_svcomp26{,vguide}/`
  - `output/vguide/experiments/combined300_noovf_svcomp26overflow{,vguide}/`
- path-keyed（避免 basename 跨目錄碰撞；參 [`2026-06-15_svcomp26_overflow_vguide.md`](2026-06-15_svcomp26_overflow_vguide.md) 的更正）。
