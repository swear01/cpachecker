# Threats to Validity

## 1. Benchmark Selection Bias

We evaluated 11 benchmarks, all from SV-COMP ReachSafety-Loops (specifically loop-invgen and loop-acceleration categories). The selected cases were zero-context timeouts for CPAchecker PredicateCPA at 300s. All rescue cases share counter/accumulator relational patterns across two-or-more loops. This pattern is common in SV-COMP loop benchmarks but may not generalize to other benchmark families.

## 2. LLM Output Nondeterminism

LLM calls at temperature=0 do not guarantee deterministic output. string_concat-noarr originally solved 1/3 runs because B5-MR produced SA-name contaminated output on runs 1-2. Fixed-predicate replay stabilized it to 3/3. Other benchmarks showed similar variance (down 2/3 reproducibility). Record/replay infrastructure exists but requires cached LLM responses.

## 3. Small Sample Size

11 benchmarks total. 2 directly reproducible scalar rescues (up, down). 1 stabilized via fixed replay. 4 Level 1 bootstrap-only rescues. Statistical conclusions are not possible; the result is a proof-of-concept demonstration of targeted rescue.

## 4. Toolchain Dependence

Results depend on:
- CPAchecker 4.2.2 with PredicateCPA and BDD-based predicate abstraction
- DeepSeek chat API (specific model version)
- Local environment (32-bit header issue for .c files)
- 300s verifier budget
- Specific configuration flags

Reproducing results requires matching this toolchain and environment.

## 5. Predicate Parser / Validator Limitations

The predicate parser supports only BV arithmetic operators and comparisons. Array theory (`select`, `store`), bitvector shifts (`bvshl`), and extract operations are not supported. Level 1 works because the proof bottleneck is scalar. Level 2 benchmarks (32 candidates) may require parser extensions that are not yet implemented.

## 6. Reproducibility

Many raw result files are gitignored (under `results/`). Key summaries are tracked in `docs/vguided-cegar/`. Exact predicate lists are available for some cases but not all. Reproducing runs requires either:
- The same LLM API key and model version
- Cached LLM responses via the record/replay infrastructure
- Fixed-predicate replay using tracked predicate lists

## 7. Generality

The claim is targeted: relational scalar proof bottlenecks, including array-present cases where the bottleneck remains scalar. The method does not claim to help:
- Purely bounds-dominated cases
- Pointer/heap/aliasing benchmarks
- Floating-point or concurrency benchmarks
- Cases requiring array content reasoning (Level 2+)
- Benchmarks already solved by B2 in few refinements

## 8. Soundness

LLM predicates enter precision only — they are Boolean features that PredicateCPA tracks, not trusted invariants. CPAchecker's CEGAR loop remains the sound proof engine. An output validator rejects internal SSA symbols and unsupported operators. However, a wrongly chosen precision predicate could theoretically increase the number of refinements needed or lead to a different abstract state exploration, potentially missing a real counterexample. PredicateCPA with wrong precision may still be sound for TRUE properties (precision over-approximates) but could miss FALSE properties if precision is too coarse. We do not claim soundness for FALSE rescue.
