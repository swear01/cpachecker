# Level 1 Array-Present Scalar-Bottleneck Results

## Summary

6 `RUN_ARRAY_SCALAR` candidates evaluated. 4/6 bootstrap-only rescued, 6/6 context unlocked. 0 select/store predicates generated. No array theory was implemented or needed.

## Result Table

| Candidate | Bootstrap Result | Refs | Select/Store | Diagnosis |
|-----------|-----------------|-----:|:---:|-----------|
| array_3-1 | TRUE | 1 | no | bootstrap_only_rescue |
| heapsort | TRUE | 8 | no | bootstrap_only_rescue |
| id_build | TRUE | 1 | no | bootstrap_only_rescue |
| large_const | TRUE | 5 | no | bootstrap_only_rescue |
| array_3-2 | UNKNOWN | 47 | no | context_unlocked_only |
| array_4 | UNKNOWN | 62 | no | context_unlocked_only |

## Safe Claim

Level 1 array-present scalar-bottleneck support is validated: scalar Bootstrap predicates can handle selected array-present benchmarks without select/store support when the proof bottleneck is scalar index/counter reasoning.

## Non-Claims

- This is NOT full array theory support.
- This does NOT support select/store predicates.
- This does NOT support pointer/heap reasoning.
- This does NOT prove all array benchmarks are supported.

## What Level 1 Means

Arrays appear syntactically in the source code, but the assertion and proof depend only on scalar loop variables (counters, indices, bounds). The LLM generates only scalar SMT-LIB2 predicates. No `select`, `store`, or array theory operators are used.

## Context-Unlocked Cases

array_3-2 and array_4 unlocked context (47 and 62 refs) but did not solve with bootstrap alone. They may benefit from B5-MR repair or require additional scalar relations. They are NOT rescue cases. Classifier correctly identified them as array-present scalar-bottleneck; the bootstrap step worked but the predicates were insufficient for the proof.

## Future Work (Level 2+)

Not yet evaluated or implemented:
- `RUN_ARRAY_SELECT_EXPERIMENTAL` (32 candidates) — may need `select` predicates
- Simple select/store parser support
- Pointer/heap/aliasing
- Quantified array invariants
