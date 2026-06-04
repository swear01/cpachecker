# Bootstrap Rescue Case Studies — Cross-Case Synthesis

## Confirmed Rescue Cases

| case | no-LLM | B2+bootstrap | B2+bootstrap+B5-MR | key predicates | pattern | reproducible |
|------|--------|-------------|---------------------|----------------|---------|:---:|
| up | UNKNOWN (65 refs) | UNKNOWN (44 refs) | **TRUE (1-2 refs)** | `k=i`, `k=n-j` | counter/accumulator | 3/3 |
| down | UNKNOWN (89-94 refs) | UNKNOWN (37 refs) | **TRUE (1-2 refs)** | accumulator | counter/accumulator | 2/3 |
| string_concat-noarr | UNKNOWN (62-67 refs) | UNKNOWN (52-57 refs) | **TRUE (1 ref)** | string/counter | string/counter | 1/3 |

## Context-Unlocked-Only Cases

| case | no-LLM | B2+bootstrap | B2+bootstrap+B5-MR | suspected missing piece |
|------|--------|-------------|---------------------|------------------------|
| half_2 | UNKNOWN | UNKNOWN (67 refs) | UNKNOWN (61 refs) | B5 produces predicates but insufficient |
| seq-3 | UNKNOWN | UNKNOWN (43 refs) | UNKNOWN (37 refs) | B5 produces predicates but insufficient |

## Common Success Pattern

1. **Two-or-more loops** with counter/accumulator variables.
2. **Bootstrap**: source-level predicates (bounds, counters, initial relations) unlock CEGAR context.
3. **B5-MR**: trace/interpolant-guided repair discovers relational predicates (e.g., `k = n - j`) that complete the proof.
4. **Variable-name table**: prevents SSA-name contamination in B5 repair output.
5. **Combination**: neither bootstrap alone nor individual B5 predicates alone suffice; the proof requires both stages.

## Common Failure Modes

1. **B5 repair quality varies**: string_concat-noarr only solved 1/3 runs because B5 repair predicates varied in quality.
2. **Context unlocked but not sufficient**: half_2 and seq-3 produced context and B5 predicates but didn't solve.
3. **Individual predicates insufficient**: Ablation on `up` showed neither `k=i` nor `k=n-j` alone suffices.

## Key Finding

> Bootstrap + B5-MR has produced confirmed local solved-from-UNKNOWN rescue cases on two-or-more-loop counter/accumulator benchmarks. The bootstrap stage creates the missing CEGAR feedback channel; the B5-MR stage discovers the proof-completing relational predicate. The variable-name table fix in the B5 prompt is critical for producing valid source-level predicates.

## Final Claim

Bootstrap + B5-MR has produced confirmed local rescue cases on the listed benchmarks. The observed successful cases share relational counter/accumulator proof structure across two-or-more loops. This supports a targeted rescue claim, not a general solver improvement claim. The claim is limited to benchmarks where (1) bootstrap unblocks CEGAR context, (2) the missing relational predicate is within the BV SMT subset, and (3) the B5 repair prompt with variable-name table generates valid source-level predicates.
