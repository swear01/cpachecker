# Final Synthesis — LLM-Guided Predicate Discovery for CEGAR

## 1. Project Goal

This project studies whether LLMs can generate useful abstraction predicates for CEGAR-based software model checking in CPAchecker. The core question is not "Can LLMs solve verification?" but "Can LLMs propose semantic repair predicates when given CEGAR-rich failure context, and can formal tools preserve soundness by parsing, filtering, and injecting these predicates into precision?"

## 2. Method Evolution

| Mode | Approach | Result | Lesson |
|------|----------|--------|--------|
| B1 | Entailed-only: local facts strengthen interpolants | Narrow: only blockFormula-entailed predicates | Safety gate is correct but too conservative |
| B2 | Source-only LLM precision injection | Works on diamond_1-1 but unstable | LLM can generate useful predicates from source alone, but quality depends on non-determinism |
| V3 | Diversified prompting (buckets) | No improvement over B2 | Prompt format is not the bottleneck |
| V4 | Local SAT-based usefulness scoring | Regression on sum04-2 | Single-program-point SAT checks over-filter; need CEGAR feedback |
| B4 | CEGAR-guided offline repair | Not validated (weak context) | Aggregate stats are insufficient; need actual trace/interpolant data |
| B5 | Trace/interpolant-guided repair | 4/14 improved, 0 real regressions | Rich CEGAR context enables LLM to identify missing relations |

## 3. Key Technical Insight: Predicate ≠ Invariant

LLM-generated formulas fall into two classes:

- **ENTAILED** (blockFormula ⇒ p): Can safely strengthen interpolants. Example: `x >= 0`.
- **ABSTRACTION-CANDIDATE** (not entailed): Boolean features that PredicateCPA should track in precision. Example: `(bvurem x 2) == (bvurem y 2)` — not true at first loop visit but exactly the assertion predicate.

Only ENTAILED predicates affect soundness (strengthening interpolants). ABSTRACTION-CANDIDATEs are injected only into precision — they are tracked, not assumed.

## 4. Validated B5 Mechanism

B5 works in three phases:

1. **Dump**: During B2 CEGAR refinement, collect spurious counterexample trace, CFA edge branch conditions, block formulas (SMT-LIB2), interpolants per abstraction state, current precision predicates, and LLM candidate fates. Write to structured JSON.

2. **Repair**: Summarize context into compact Markdown (~4-8K tokens). Call DeepSeek with the original validated prompt: source code + assertion + CEGAR context + simple "generate repair predicates" request. Parse predicates, validate against output contract (reject SSA names, internal symbols, unsupported operators).

3. **Inject**: Parse validated predicates into AbstractionPredicate objects using CPAchecker's VariableGuide (BV formula parser with SMT-LIB2 operator aliases). Inject into global PredicatePrecision once. Rerun CPAchecker.

### Output Contract

Validator enforces:
- **Forbidden**: `|main::x@2|` (SSA pipe names), `.def_*` (solver terms), `select`/`store` (array theory), `bvshl`/`bvlshr` (unsupported BV shifts)
- **Allowed**: source-level variable names (`x`, `y`, `i`, `sn`), BV operators (`=`, `<`, `>`, `+`, `-`, `*`, `mod`, and SMT-LIB2 aliases), `(_ bvN 32)` constants

18 unit tests. Validated on real outputs: correctly rejects B5-gap SSA-name contamination, preserves original B5 clean predicates.

## 5. Negative Results and Why They Matter

Each negative result ruled out a plausible hypothesis:

- **V3**: Prompt engineering (buckets, accumulator emphasis) is not the bottleneck. The LLM already generates diverse predicates from a simple prompt.
- **V4**: Local SAT scoring at one program point cannot assess whether a predicate is useful as an abstraction feature across loop iterations.
- **B4**: Aggregate statistics (refinement count, fallback count) are too weak as CEGAR context. Interpolants and trace structure are needed.
- **B5-gap**: Explicit "find the interpolant gap" instructions cause the LLM to copy SSA-encoded variable names from interpolants, degrading predicate quality.
- **Local entailment gate**: `blockFormula ⇒ p` rejects useful predicates like `x%2==y%2` that are not true at the first loop-head visit but are the exact bottleneck.

## 6. Evaluation Summary

### Cumulative Results (14 benchmarks, 4 evaluation rounds)

| Category | Count | Benchmarks |
|----------|------:|------------|
| Improved | 4 | sum04-2, const_1-2, functions_1-2, nested_1-2 |
| No effect | 6 | diamond_1-2, sum01-1, linear-inequality-inv-c, phases_1-2, sum03-1, underapprox_1-2 |
| No B5 headroom | 2 | linear-ineq-inv-a, sum01-2 |
| Parser-limited | 1 | eureka_01-2 |
| Regression (algorithm) | 0 | — |
| Regression (nondeterminism) | 1 | sum01_bug02 |

### Key Confounder: B2 LLM Non-determinism

The same B2 prompt produces different predicate quality across runs:
- sum01-2: 37 refs (pre-scan) vs 2 refs (B5 run) — 18x variance
- const_1-2: 154 vs 47 vs 38 refs across different runs
- linear-ineq-inv-a: from 89 to 1 ref depending on whether LLM generates `s>=255*i`

This means B2 vs B5 comparison is confounded: B5 "improvement" depends partly on whether B2 happened to get unlucky. A B2 run that luckily generates the right predicate leaves no headroom for B5; an unlucky B2 run allows B5 to show a large delta.

## 7. Applicability Boundary

B5 helps when:
1. The CEGAR bottleneck is a missing auxiliary relational predicate (not bounds)
2. The predicate is expressible in supported BV SMT operators
3. B2's source-only prompt misses the predicate (not non-deterministically lucky)
4. The benchmark has ≥10 B2 refinement room (not too-easy)

B5 does NOT help when:
1. The benchmark is bounds-dominated (diamond_1-2)
2. B2 already solves in ≤5 refinements (linear-ineq-inv-a)
3. The benchmark requires array/pointer/shift operations (eureka_01-2)
4. The benchmark is too-easy for any predicate to matter
5. The LLM happens to generate the perfect predicate for B2 (no headroom)

## 8. Limitations

1. **B2 non-determinism**: Fair comparison requires deterministic B2 baselines (see DETERMINISTIC_REPLAY_PLAN.md)
2. **Parser subset**: Array theory, bitvector shifts, and extract not supported
3. **One-shot**: B5 injects repair predicates once; multi-round repair is not tested
4. **Benchmark pool**: Most SV-BENCH loop benchmarks are too-easy for CEGAR with LLM predicates
5. **Global precision only**: Local precision injection (per-CFANode) not explored
6. **One LLM call**: No ensemble or Best-of-N, by design (cost concern)

## 9. Future Work

1. **Deterministic replay**: Cache and replay LLM outputs to eliminate B2 non-determinism as a confounder.
2. **Interpolant gap automation**: Automatically detect when interpolants are bounds-only and the assertion requires a relational predicate — use this as a B5 trigger without LLM inspection.
3. **Local precision injection**: Inject predicates only at relevant CFANodes, not globally.
4. **Timeout snapshot**: Handle benchmarks where B2 times out before producing refinement dumps.
5. **Parser extension**: Support `bvshl`, array `select`/`store` for benchmarks involving bitvector shifts and arrays.
6. **Multi-round repair**: B5 → rerun → dump new context → B5 → rerun → ..., using append-only transcript for prompt-cache reuse.
