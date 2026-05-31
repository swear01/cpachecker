# Integrated Rescue Synthesis

## 1. One-Sentence Thesis

Bootstrap + B5-MR rescues selected PredicateCPA zero-context timeouts by seeding initial scalar precision predicates to unlock CEGAR context, then using LLM-guided repair to add proof-relevant relational predicates.

## 2. Problem

PredicateCPA (CPAchecker's predicate abstraction) can timeout before producing any usable CEGAR context — zero refinements, zero spurious traces, zero interpolants. B5-MR trace/interpolant-guided LLM repair cannot operate because there is no trace to analyze. These are ZERO_CONTEXT_TIMEOUT cases.

## 3. Method Overview

```
no-LLM PredicateCPA
  → ZERO_CONTEXT_TIMEOUT (0 refinements, 0 dumps)
Bootstrap initial precision
  → CEGAR context unlocked (spurious traces, interpolants)
B5-MR repair
  → TRUE (proof completed)
```

## 4. Components

### Bootstrap (Initial Precision Seeding)
- LLM reads source code + assertion, generates 7-17 scalar abstraction predicates.
- Predicates enter PredicateCPA precision only — not trusted as invariants.
- CPAchecker remains the sound proof engine.

### B5-MR (Multi-Round Repair)
- Uses newly available trace/interpolant context.
- Variable-name table prevents SSA-encoded name contamination.
- Validator enforces source-level predicate discipline.

### Classifier
- `RUN_SCALAR`: scalar loops, counter/accumulator relations.
- `RUN_ARRAY_SCALAR`: array present but scalar bottleneck (Level 1).
- `RUN_ARRAY_SELECT_EXPERIMENTAL`: may need select (Level 2, future).
- `SKIP_POINTER_HEAP`, `SKIP_UNSUPPORTED_THEORY`, `PARSER_RISK`: excluded.

## 5. Scalar Rescue Results

| Case | no-LLM | Bootstrap | B5-MR | Repro | Status |
|------|--------|-----------|-------|:---:|--------|
| up | ZERO_CONTEXT | unlocked | TRUE (1-2r) | 3/3 | stable_confirmed_rescue |
| down | ZERO_CONTEXT | unlocked | TRUE (1-2r) | 2/3 | confirmed_rescue |
| string_concat-noarr | ZERO_CONTEXT | unlocked | TRUE (1r) | 3/3* | stabilized_via_fixed_predicates |
| half_2 | ZERO_CONTEXT | unlocked (67r) | UNKNOWN (61r) | — | context_unlocked_only |
| seq-3 | ZERO_CONTEXT | unlocked (43r) | UNKNOWN (37r) | — | context_unlocked_only |

*Originally 1/3; fixed-predicate replay 3/3. Instability was LLM-side SSA-name variance.

## 6. Level 1 Array-Present Scalar Results

| Candidate | Bootstrap | Refs | Select/Store | Diagnosis |
|-----------|----------|-----:|:---:|-----------|
| array_3-1 | TRUE | 1 | no | bootstrap_only_rescue |
| heapsort | TRUE | 8 | no | bootstrap_only_rescue |
| id_build | TRUE | 1 | no | bootstrap_only_rescue |
| large_const | TRUE | 5 | no | bootstrap_only_rescue |
| array_3-2 | UNKNOWN | 47 | no | context_unlocked_only |
| array_4 | UNKNOWN | 62 | no | context_unlocked_only |

6 candidates, 4 rescues, 6/6 context unlocked, 0 select/store. No array theory implemented.

## 7. Ablation Evidence

On `up`: `k=i` alone insufficient. `k=n-j` alone insufficient. Both needed and sufficient. Predicate combination required for proof.

## 8. Soundness

- LLM predicates are precision predicates only — never trusted as invariants.
- CPAchecker proves TRUE/FALSE.
- Output validator rejects internal symbols, SSA names, unsupported operators.
- Variable-name table prevents contamination.

## 9. Negative Results and Boundaries

- B5-MR alone cannot handle zero-context timeout (needs trace context).
- B5-gap explicit gap-analysis prompt was rejected (SSA-name contamination).
- V3 prompt diversification and V4 local SAT scoring did not improve systematically.
- Full array theory not implemented (no select/store).
- Pointer/heap/aliasing out of scope.
- Context-unlocked-only cases remain unsolved (half_2, seq-3, array_3-2, array_4).

## 10. Final Safe Claim

Bootstrap + B5-MR produced local solved-from-UNKNOWN rescues on selected zero-context timeout benchmarks with relational scalar proof bottlenecks. The approach extends to some array-present benchmarks when the proof bottleneck remains scalar index/counter reasoning. This is a targeted rescue result, not a general solver improvement claim.
