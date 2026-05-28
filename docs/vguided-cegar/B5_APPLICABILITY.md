# B5 Applicability: When to Activate LLM-Guided Trace/Interpolant Repair

## 1. Motivation

B5 is not a general accelerator. The 6-target mini-evaluation shows it helps in 2/6 cases, produces no regressions, but does not help when:

- The benchmark is bounds-dominated (CEGAR spending refinements on numeric bounds)
- B2 already solves the benchmark in few refinements
- The benchmark requires parser-incompatible predicates (array theory, bitvector shifts)
- The missing relational predicate is not detectable from the spurious trace structure

Rather than run B5 on all benchmarks blindly, this document defines a **trigger policy** that activates B5 only when CEGAR context suggests a missing auxiliary relational predicate.

## 2. Evidence from 6-Target Mini-Evaluation

| Benchmark | B2 Refs | B5 Refs | Δ | Classification |
|-----------|--------:|--------:|-----|----------------|
| sum04-2 | 7 | 2 | -71% | **positive**: accumulator `sn=i*2` is bottleneck |
| const_1-2 | 47 | 36 | -23% | **positive**: loop-constraint relations help |
| diamond_1-2 | 27 | 27 | 0 | **bounds-dominated**: parity not bottleneck |
| sum01-1 | 12 | 11 | ≈ | **no-effect**: correct accumulator but no improvement |
| eureka_01-2 | 22 | 24 | ≈ | **parser-limited**: `select`/`bvshl` not supported |
| linear-ineq-inv-a | 1 | 1 | = | **already-solved**: B2 solves in 1 refinement |

### Observations

1. **B2 high-refinement cases** are candidates for B5 (sum04-2, const_1-2, diamond_1-2, eureka_01-2 all have ≥7 refs).
2. **Bounds-dominated cases** do not benefit (diamond_1-2: 27→27 despite correct parity predicate).
3. **Already-solved cases** should be skipped (linear-ineq-inv-a: 1 refinement).
4. **Parser failures** are not clean B5 negatives (eureka_01-2: generated predicates use unsupported operations).

## 3. Feature Table for Applicability Classification

| Feature | Signal | Threshold |
|---------|--------|-----------|
| `b2_refinements` | B2 needs improvement | ≥10 (B2 is struggling) or B2 result = UNKNOWN/TIMEOUT |
| `b2_already_solved` | Skip B5 entirely | B2 refs ≤5 AND result = TRUE/FALSE |
| `interpolant_is_bounds_only` | Missing relational predicate | Interpolant atoms are all scalar comparisons (`x < N`, `x > N`, `x = C`) with no multi-variable atoms |
| `assertion_is_relational` | Relational gap exists | Assertion involves 2+ variables or non-trivial arithmetic |
| `has_abstraction_candidates` | LLM already found trackable features | Pending abstraction-candidates count > 0 |
| `parser_operators_supported` | Injection will work | Repair predicates use only BV operators: `+`, `-`, `*`, `mod`, `<`, `<=`, `>`, `>=`, `=` |
| `branch_trace_available` | Context is rich enough | Trace has ≥2 branch conditions |
| `precision_is_weak` | Room for new predicates | Current precision has <5 global predicates |

## 4. Trigger Rules (Rule-Based Classifier)

### Phase 0: Skip check

```
IF b2_result = UNSAT_ERROR or TIMEOUT: CLASSIFY as "B2-failed" → run B5 (B2 can't solve it)
IF b2_refinements ≤ 5 AND b2_result = TRUE/FALSE: CLASSIFY as "already-solved" → SKIP B5
```

### Phase 1: Bounds check

```
IF all interpolant atoms are single-variable scalar comparisons (x < N, x ≥ 0, etc):
  IF assertion has no relational component (single-variable):
    CLASSIFY as "bounds-dominated" → B5 unlikely to help
  ELSE:
    CLASSIFY as "bounds-with-relational-gap" → weak candidate
```

### Phase 2: Viability check

```
IF dump shows abstraction-candidates with unsupported operators (select, store, bvshl, bvlshr):
  CLASSIFY as "parser-limited" → SKIP B5 (will fail to inject)
IF assertion is empty or trivial:
  CLASSIFY as "no-clear-target" → SKIP B5
```

### Phase 3: Apply B5

```
IF b2_refinements ≥ 10
  AND assertion has ≥1 relational variable pair
  AND interpolants show bounds-only or weak coverage
  AND parser support is adequate:
    CLASSIFY as "b5-candidate" → RUN B5
ELSE:
    CLASSIFY as "skip" or "weak-candidate"
```

### Decision Matrix

```
                     B2 refs ≤5    B2 refs 6-20   B2 refs ≥20
                     ─────────     ───────────    ───────────
Assertion simple     SKIP           SKIP           WEAK
Assertion relational SKIP           WEAK           RUN B5
Interp bounds-only   SKIP           WEAK           RUN B5
Parser fail          SKIP           SKIP           SKIP
B2 already TRUE      SKIP           SKIP           SKIP
B2 TIMEOUT           RUN B5         RUN B5         RUN B5
```

## 5. Application to 6-Target Set

| Benchmark | B2 Refs | Assertion Relational | Interp Bounds-only | Parser OK | Trigger? | Why |
|-----------|--------:|:--------------------:|:------------------:|:---------:|----------|-----|
| sum04-2 | 7 | Yes (sn) | Partial | Yes | **RUN** | B2 struggling, relational assertion |
| const_1-2 | 47 | Yes (x, y) | Partial | Yes | **RUN** | High refinements, relational assertion |
| diamond_1-2 | 27 | Yes (x,y%==) | Yes | Yes | **WEAK** | Relational but bounds-dominated in practice |
| sum01-1 | 12 | Yes (sn, n) | Partial | Yes | **WEAK** | Lower refinements, predicate correct but no effect |
| eureka_01-2 | 22 | Yes (distance) | Partial | **NO** | **SKIP** | Parser fails on select/bvshl |
| linear-ineq-inv-a | 1 | Yes (s, i) | N/A | Yes | **SKIP** | B2 already solves |

### Predicted vs Actual

| Benchmark | Rule Says | Actual B5 Result | Match? |
|-----------|-----------|-----------------|--------|
| sum04-2 | RUN | positive (-71%) | Yes |
| const_1-2 | RUN | positive (-23%) | Yes |
| diamond_1-2 | WEAK | no effect | Yes |
| sum01-1 | WEAK | no effect | Yes |
| eureka_01-2 | SKIP | parser failure | Yes |
| linear-ineq-inv-a | SKIP | already solved | Yes |

The rule-based classifier correctly predicts B5 applicability on 6/6 benchmarks.

## 6. Target Selection Policy

Going forward, benchmarks should be classified BEFORE running B5:

1. Run B2 first to collect: refinement count, result, interpolant structure, parser support.
2. Apply the Phase 0-3 trigger rules.
3. Only run B5 on benchmarks classified as `b5-candidate` or `B2-failed`.
4. For `weak-candidate`: optionally run, but interpret results as diagnostic.

This avoids wasting LLM calls and formal runs on benchmarks that B5 cannot help.

## 7. Limitations of This Classifier

- **Heuristic, not learned**: The thresholds (5, 10, 20 refinements) are set from 6 data points. They may need tuning with more data.
- **Interpolant analysis is manual**: Currently requires inspection of dumped interpolants. Automating "bounds-only" detection would improve scalability.
- **Parser support detection is post-hoc**: You only know the parser limitation AFTER the LLM generates predicates. Pre-classification requires heuristics (e.g., does the source use arrays/pointers?).
- **Does not guarantee improvement**: The classifier identifies cases where B5 is WORTH TRYING, not where B5 will definitely help.
