# Master Result Index — Bootstrap + B5-MR Rescue

## Scalar Rescue Results

| case | no-LLM @300s | bootstrap | B5-MR | repro | diagnosis | pattern |
|------|-------------|-----------|-------|:---:|-----------|--------|
| up | ZERO_CONTEXT | unlocked (43r) | TRUE (1-2r) | 3/3 | stable_confirmed_rescue | counter/accumulator |
| down | ZERO_CONTEXT | unlocked (37r) | TRUE (1-2r) | 2/3 | confirmed_rescue | counter/accumulator |
| string_concat-noarr | ZERO_CONTEXT | unlocked (52-57r) | TRUE (1r) | 3/3 fixed | stabilized_via_fixed_predicates | string/counter |
| half_2 | ZERO_CONTEXT | unlocked (67r) | UNKNOWN (61r) | — | context_unlocked_only | counter/halving |
| seq-3 | ZERO_CONTEXT | unlocked (43r) | UNKNOWN (37r) | — | context_unlocked_only | sequential loops |

## Level 1 Array-Present Scalar

| case | bootstrap | refs | select/store | diagnosis |
|------|----------|-----:|:---:|-----------|
| array_3-1 | TRUE | 1 | no | bootstrap_only_rescue |
| heapsort | TRUE | 8 | no | bootstrap_only_rescue |
| id_build | TRUE | 1 | no | bootstrap_only_rescue |
| large_const | TRUE | 5 | no | bootstrap_only_rescue |
| array_3-2 | UNKNOWN | 47 | no | context_unlocked_only |
| array_4 | UNKNOWN | 62 | no | context_unlocked_only |

## Counts

| category | count |
|----------|------:|
| stable_confirmed_rescue | 1 |
| confirmed_rescue | 1 |
| stabilized_rescue | 1 |
| bootstrap_only_rescue (Level 1) | 4 |
| context_unlocked_only | 4 |
| total evaluated | 11 |
| bootstrap context unlock rate | 11/11 (100%) |
| select/store generated | 0 |
| validator rejects (post-fix) | 0 |

## Safe Claim

Bootstrap + B5-MR produced local solved-from-UNKNOWN rescues on selected zero-context timeout benchmarks with relational scalar proof bottlenecks. The approach extends to array-present benchmarks when the proof bottleneck remains scalar. No array theory is implemented.
