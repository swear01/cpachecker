# Evaluation Modes

## Baseline Matrix

| Mode | Name | Description | Source |
|------|------|-------------|--------|
| B0 | Stock | Original CPAchecker | — |
| B1 | Entailed-only | LLM locally entailed facts → strengthen interpolant | LLM auto |
| B2 | LLM precision | LLM abstraction-candidates → one-shot precision injection | LLM auto |
| B3a | Assertion oracle | Assertion condition as predicate → one-shot precision | Auto extract |
| B3d | Manual oracle | Expert-annotated key predicate → one-shot precision | Manual (few) |

## B3a: Assertion Oracle Design

### Rationale

For many loop benchmarks, the assertion expression itself is the key relational predicate that CEGAR needs to track. Using the assertion directly as an abstraction predicate provides a cheap diagnostic upper bound:

- If B3a improves but B2 does not: LLM failed to find/rank the key predicate → fix prompt/ranking
- If B3a improves and B2 also improves: LLM succeeded
- If neither improves: the assertion predicate is not the bottleneck
- If B2 regresses but B3a improves: B2 candidate pool too noisy

### Extraction

Parse assertion expressions from C source:

```c
assert(x == y);                → (= x y)
__VERIFIER_assert((x % 2) == (y % 2));  → (= (mod x 2) (mod y 2))
if (!(y == 2 * x)) { ERROR: ... }       → (= y (* 2 x))
```

### Supported Operators

The predicate converter reuses the existing BV parser, so the same operator support applies:
`=, >=, <=, >, <, +, -, *, mod, and, or, not`

### Implementation

New env flag: `VGUIDE_INJECT_ASSERTION_ORACLE_ONCE=1`

Adds the extracted assertion predicate to PredicateCPA precision exactly once (same one-shot guard as B2).

## Diagnosis Matrix

| B2 result | B3a result | Interpretation |
|-----------|-----------|----------------|
| improves | improves | LLM found effective predicate ✓ |
| no change | improves | **LLM missed key predicate** — fix prompt/ranking |
| no change | no change | assertion predicate not the bottleneck |
| regresses | improves | B2 candidate pool too noisy — fix selection |
| regresses | regresses | precision injection itself is harmful here |
