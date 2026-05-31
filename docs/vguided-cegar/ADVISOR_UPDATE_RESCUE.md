# Advisor Update: Bootstrap + B5-MR Rescue

## One-Paragraph Summary

We found local solved-from-UNKNOWN rescue cases. The no-LLM PredicateCPA baseline timed out with zero CEGAR context, while Bootstrap + B5-MR solved selected cases under the same 300s budget. Bootstrap uses LLM-generated source-level predicates to unlock CEGAR refinement context; B5-MR then uses trace/interpolant-guided repair to add proof-relevant relational predicates. Result confirmed on `up` (3/3 reproduction) and `down` (2/3), with `string_concat-noarr` as an unstable candidate (1/3).

## Main Result Table

| Case | no-LLM @300s | Bootstrap | Bootstrap+B5-MR | Repro | Status |
|------|-------------|-----------|-----------------|:---:|--------|
| up | ZERO_CONTEXT_TIMEOUT | context unlocked | **TRUE (1-2 refs)** | 3/3 | stable confirmed rescue |
| down | ZERO_CONTEXT_TIMEOUT | context unlocked | **TRUE (1-2 refs)** | 2/3 | confirmed rescue |
| string_concat-noarr | ZERO_CONTEXT_TIMEOUT | context unlocked | TRUE (1 ref) | 1/3 | unstable rescue candidate |
| half_2 | ZERO_CONTEXT_TIMEOUT | context unlocked | UNKNOWN | — | context unlocked only |
| seq-3 | ZERO_CONTEXT_TIMEOUT | context unlocked | UNKNOWN | — | context unlocked only |

## Why This Is Stronger Than Acceleration

Previous B5 work showed refinement reduction on HARD_SOLVED cases (e.g., sum01-2 53→2). But those benchmarks were always solvable by B2 — B5 just made them faster. **Rescue is different**: the no-LLM baseline could not solve these benchmarks at all (zero CEGAR context), and the LLM-assisted pipeline solved them.

## How the Method Works

1. **Bootstrap**: LLM reads source code + assertion, generates 8-17 initial abstraction predicates (bounds, counters, loop relations). These are injected into PredicateCPA precision — they're tracked as Boolean features, not trusted as invariants.
2. **Context unlocked**: With initial predicates, CPAchecker can now complete CEGAR refinements, producing spurious counterexample traces, interpolants, and candidate fates.
3. **B5-MR repair**: LLM receives the CEGAR context (trace, interpolants, precision) and generates additional relational predicates. A critical fix prevents the LLM from copying internal SSA-encoded variable names.
4. **CPAchecker proves**: All LLM predicates are precision predicates only. CPAchecker remains the sound proof engine.

## Ablation Evidence

On `up`: neither `k=i` alone nor `k=n-j` alone is sufficient. The combination of both predicates is required for the proof.

## Limitations

- 5 benchmarks evaluated, 2 confirmed reproducible rescues.
- Rescue is limited to two-or-more-loop counter/accumulator relational benchmarks.
- B5 repair predicate quality varies across runs (string_concat-noarr).
- Zero-context timeout pool is exhausted; need external harder benchmarks to find more cases.
- Local no-LLM baselines used `useVocabularyGuide=true`; the true "stock" CPAchecker baseline may be even harder.

## Next Steps

1. Stabilize string_concat-noarr (deterministic replay).
2. Search for harder benchmarks from external SV-COMP suites.
3. Test whether local precision injection (per-CFANode) improves unstable cases.
