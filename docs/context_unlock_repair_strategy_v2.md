# Context-Unlock Repair Strategy v2

## Root Cause of B5-MR Failure

B5-MR Round 1 generated 5 semantically correct repair predicates but all were rejected (`REJECT_INTERNAL_SYMBOL`). The LLM copied `|main::i|` SSA-encoded names from interpolant context into output.

The LLM's reasoning was **correct**: it identified `k = i` (first loop body relation) and `k > n - j` (second loop invariant implying k > 0).

The fix is **not** a prompt re-engineering — it's strengthening the output contract enforcement in the B5 repair prompt.

## Recommended Fix: Explicit Variable Name Table

Before the JSON output instruction, include a variable name table derived from the source code and assertion:

```
### Required Variable Names (from source code)
Use ONLY these simple names:
- i (source line 5)
- k (source line 7)
- n (source line 4)
- j (source line 10)

NEVER use:
- |main::i|, |main::k@2| (SSA-encoded)
- .def_43, .def_69 (internal solver terms)
```

This gives the LLM an explicit mapping that it MUST follow, rather than just a negative rule ("don't use internal names").

## Alternative: Source-Level Variable Extraction

Modify the B5 prompt builder (`b5_build_prompt.py`) to:
1. Extract all C variable names from the source code section of the prompt.
2. Append a "Required Variable Names" section listing only these names.
3. The LLM can only output names from this list.

## Expected Effect

With proper variable names, the B5-MR would have produced:
1. `(= k i)` — passed, injectable
2. `(bvsgt k (bvsub n j))` — passed, injectable, proves k > 0
3. `(bvsle j k)` — passed, injectable

These three predicates together would likely be sufficient to prove `k > 0` at the assertion site.

## Immediate Next Step

1. Update `b5_build_prompt.py` to include a "Required Variable Names" section derived from source.
2. Re-run B5-MR with the fixed prompt.
3. Check if valid repair predicates are generated and injected.
