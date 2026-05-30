# B5-MR Failure Analysis

## Summary

B5-MR Round 1 attempted repair on top of bootstrap. 5 candidates generated, all semantically correct, all rejected by validator.

## Root Cause

**SSA-name contamination in B5 repair prompt.** The LLM reads interpolant SMT-LIB2 text which uses SSA-encoded variable names (`|main::i@2|`). The LLM copied these into its output, violating the source-level variable name contract. The validator correctly rejected all 5 candidates.

## Candidate-by-Candidate Analysis

| # | Generated | Semantically Correct | Rejection | Would Work With Source Names? |
|---|-----------|:---:|--------|:---:|
| 1 | `(bvslt |main::i| |main::n|)` | yes | REJECT_INTERNAL_SYMBOL | `(bvslt i n)` → YES |
| 2 | `(= |main::k| |main::i|)` | yes | REJECT_INTERNAL_SYMBOL | `(= k i)` → YES |
| 3 | `(bvslt |main::j| |main::n|)` | yes | REJECT_INTERNAL_SYMBOL | `(bvslt j n)` → YES |
| 4 | `(bvsgt |main::k| (bvsub |main::n| |main::j|))` | yes | REJECT_INTERNAL_SYMBOL | `(bvsgt k (bvsub n j))` → YES |
| 5 | `(bvsle |main::j| |main::k|)` | yes | REJECT_INTERNAL_SYMBOL | `(bvsle j k)` → YES |

## LLM Reasoning Quality

The LLM correctly analyzed the benchmark:
- Identified `k = i` as the key missing relation after the first loop
- Derived `k > n - j` as the invariant that implies `k > 0` when `j < n`
- Understood the two-loop structure with accumulator tracking

The reasoning was correct. The failure is purely an output format issue.

## Logging Gaps

1. **No variable name mapping in prompt**: The B5 repair prompt includes interpolants with SSA names but doesn't provide a mapping table to source-level names.
2. **Validator rejects all but doesn't suggest fix**: The rejection message `REJECT_INTERNAL_SYMBOL` is clear but could include a hint: "use 'i' instead of '|main::i|'".
3. **No per-candidate rejection trace**: The validator could show which specific token triggered the rejection.

## Recommended Fix

Add a "Variable Name Table" section to the B5 repair prompt:

```
### Variable Names (from source code)
i, k, n, j
NEVER use: |main::...|, .def_*
```

This gives the LLM explicit names to use rather than just a negative rule.
