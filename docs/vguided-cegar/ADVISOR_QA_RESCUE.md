# Advisor Q&A — Bootstrap + B5-MR Rescue

## 1. Is this sound if the LLM generates wrong predicates?

Yes. LLM predicates are used only as precision predicates — Boolean features that PredicateCPA tracks. They are never trusted as invariants or added to the proof assumptions. CPAchecker's CEGAR loop remains the sound proof engine. An output validator rejects internal SSA-encoded symbols and unsupported operators.

## 2. Why is this not just prompt engineering?

The core contribution is not prompt design. It's the two-stage architecture: Bootstrap seeds initial precision to unlock CEGAR context, then B5-MR uses the resulting trace/interpolant feedback to discover proof-relevant relational predicates. The prompt variants (V3 diversified, B5-gap explicit gap analysis) were tested and rejected as negative results. The variable-name table is a safety fix, not a prompt tuning.

## 3. Why does Bootstrap help zero-context timeouts?

Zero-context timeout means CPAchecker's initial abstraction is too weak to produce any spurious counterexample. Bootstrap injects source-level predicates (bounds, counters, loop relations) that are precise enough to trigger the first CEGAR refinement. Once one refinement completes, the normal trace/interpolant feedback loop starts.

## 4. Why does B5-MR alone fail?

B5-MR requires spurious counterexample traces, interpolants, and candidate fates to guide repair. On zero-context timeouts, none of these exist. Bootstrap provides the missing initial context.

## 5. Why not run this on every benchmark?

The method is not always-on. A classifier identifies benchmarks likely to benefit: scalar loops with counter/accumulator relations, including array-present cases where the proof bottleneck remains scalar. Pointer/heap, floating-point, concurrency, and complex array-content benchmarks are excluded.

## 6. What is the role of the classifier?

It selects targets where the method is likely useful, avoiding wasted LLM calls and formal runs on benchmarks it cannot help. Labels: RUN_SCALAR, RUN_ARRAY_SCALAR (Level 1), RUN_ARRAY_SELECT_EXPERIMENTAL (Level 2 future), and skip categories.

## 7. Does this support arrays?

Level 1 only: array-present benchmarks where the proof bottleneck is scalar index/counter reasoning. No select/store predicates are generated or parsed. Level 2 (simple select predicates) is future work. Full array theory, pointer/heap, and aliasing are out of scope.

## 8. What does Level 1 mean?

Arrays appear syntactically in the source code, but the assertion and proof depend only on scalar loop variables. The LLM generates only scalar SMT-LIB2 predicates. The benchmark's arrays are incidental to the proof.

## 9. What failed?

- B5-gap explicit gap-analysis prompt: caused SSA-name contamination, rejected.
- V3 prompt diversification: no improvement over B2.
- V4 local SAT scoring: over-filtered, caused regression.
- Context-unlocked-only cases (half_2, seq-3, array_3-2, array_4): bootstrap unlocks context but B5-MR doesn't solve. Likely need additional relational predicates or more rounds.
- B5-MR alone cannot handle zero-context timeouts.

## 10. How many rescues are stable?

up: 3/3 reproduction (stable). down: 2/3 (confirmed but slightly less stable). string_concat-noarr: originally 1/3, stabilized to 3/3 via fixed-predicate replay (instability was LLM-side). Level 1 cases: 4/6 solve with bootstrap alone (no reproduction yet for the new ones).

## 11. Why is string_concat-noarr fixed replay acceptable?

The original instability was LLM-side SSA-name contamination on runs 1-2. Run 3's LLM used correct source-level names and solved. Replaying the same successful predicate set on 3 fresh runs gave 3/3 TRUE at 1 refinement. This proves the instability was not a verifier or proof problem.

## 12. What is the next experiment?

1. Stabilize context_unlocked cases (half_2, seq-3) with more B5-MR rounds.
2. Expand benchmark pool beyond exhausted SV-COMP candidates.
3. Level 2 simple select/store predicate support.
4. Local per-CFANode precision injection.

## 13. What are the main threats to validity?

- 11 total benchmarks evaluated, only 2-3 directly reproducible rescues.
- LLM output variance requires occasional fixed-predicate replay.
- Benchmark pool exhausted — cannot test broader generality.
- Parser limited to BV subset; array theory, shifts not supported.

## 14. How would this scale?

The bottleneck is not the method but the benchmark pool. The current pool has 0 zero-context timeout candidates remaining. Scaling requires harder external benchmarks (wider SV-COMP suites, larger loop bounds). The per-benchmark cost is: 1 bootstrap LLM call + up to 5 B5-MR LLM calls + 1 baseline run + 1-6 verification runs. All runs fit in 300s per benchmark.
