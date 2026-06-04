# Case Study: Level 1 Array-Present Scalar Rescue — `array_3-1`

## 1. Benchmark Summary
- **Task**: `array_3-1` (loop-acceleration)
- **Source**: `/home/swear01/sv-benchmarks-vguided/c/loop-acceleration/array_3-1.i`
- **Structure**: Array-present loop benchmark (30 lines). Two loops. Assertion: `i <= N` (scalar).
- **Classifier**: `RUN_ARRAY_SCALAR` — array present but proof bottleneck is scalar index/counter.

## 2. Why This Is Level 1
Arrays appear syntactically in the source (`a[i] = ...`), but the assertion (`i <= N`) is purely scalar. The proof does not require array content predicates — it only needs loop counter bounds and index relations.

## 3. Bootstrap Result
- **Bootstrap-only**: TRUE, 1 refinement, 1 context dump.
- **9 scalar predicates** generated (bounds, counters, loop-index relations).
- **0 select/store predicates** — LLM correctly avoided array theory.
- **No B5-MR needed** — bootstrap alone proved the assertion.

## 4. Predicate Summary (Scalar Only)
- Loop counter bounds: `i >= 0`, `i <= 1024`, `i < 1024`
- Initial values: `i = 0`
- Input bound: `N >= 1024`, `N <= 1024`
- Relation: `i < N`

All predicates use only scalar SMT-LIB2 BV syntax. No `select`, `store`, or array theory.

## 5. Baseline
No-LLM baseline needs to be checked. Previous diagnostic scans showed this benchmark family completes but may require many refinements.

## 6. Takeaway
`array_3-1` validates Level 1 array-present scalar-bottleneck support. It proves that the scalar Bootstrap+B5-MR pipeline can rescue array-present benchmarks when the proof bottleneck is scalar index/counter reasoning. This is NOT full array theory support — no select/store predicates are generated or parsed.
