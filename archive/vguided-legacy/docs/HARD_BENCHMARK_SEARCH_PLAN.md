# Hard Benchmark Search Plan for B5-MR Solved-from-UNKNOWN

## 1. Motivation

B5-MR (multi-round repair) is functionally validated: it accumulates predicates across rounds and can reduce refinements more than single-round B5 (sum01-2: 53→2). However, all tested targets were B2-solved within 60s. To test B5-MR's rescue capability (B2 UNKNOWN → B5-MR TRUE), we need benchmarks where B2 cannot solve within a resource budget.

## 2. Current Pool Limitation

- 98 scalar loop benchmarks scanned
- 0 B2_TIMEOUT at 30s
- 0 B2_TIMEOUT at 300s (7 hardest cases tested)
- All benchmarks solve within 300s

The current accessible benchmark set ($HOME/sv-benchmarks-vguided) is exhausted for unsolved cases.

## 3. Target Benchmark Profile

Ideal candidates:
- Scalar integer arithmetic (no arrays, pointers, heap)
- Contains a loop with accumulator/counter/relational pattern
- Has a `__VERIFIER_assert` or equivalent assertion
- B2 times out or returns UNKNOWN at 60s-300s
- Parser-supported operations (BV arithmetic only: `+`, `-`, `*`, `mod`, comparisons)
- Small source code (<200 lines)

## 4. Candidate Sources (Priority Order)

### A. SV-COMP unreach-call benchmarks

Repository: https://gitlab.com/sosy-lab/benchmarking/sv-benchmarks
Categories:
- `c/loops/` — loop benchmarks (likely similar to current pool)
- `c/loop-invariants/` — loop invariant benchmarks
- `c/loop-acceleration/` — loop acceleration benchmarks
- `c/loop-new/` — newer loop benchmarks not in current pool
- `c/loop-crafted/` — crafted loop benchmarks

### B. CPAchecker test programs

- `test/programs/benchmarks/` in CPAchecker source
- These are regression tests for CPAchecker features
- May include hard cases designed to stress CEGAR

### C. Ultimate Automizer examples

- Benchmarks used in Ultimate Automizer evaluations
- Often contain complex relational loop invariants

### D. Manually constructed

- As a fallback, construct benchmarks with known relational bottlenecks
- Parameterize loop bounds to control difficulty

## 5. Import Protocol

For each external benchmark:
1. Copy to `sv-benchmarks-vguided/c/external/` directory
2. Check for `.i` version or preprocess `.c` to `.i`
3. Run B2@60s to classify difficulty
4. Run B2@300s for hard/unsolved cases
5. Filter for parser-supported operations
6. Add to B5-MR target pool

## 6. Evaluation Protocol

For each imported hard benchmark:

| mode | budget | description |
|------|--------|-------------|
| B2@60 | 60s | quick difficulty classification |
| B2@300 | 300s | baseline: can B2 solve at all? |
| B5-1@300 | 300s | single-round B5 comparison |
| B5-MR@300 | 3×100s or 5×60s | multi-round under same total budget |

Success categories:
- **resource_bounded_rescue**: B2@60 UNKNOWN, B5-MR TRUE under same/comparable budget
- **strong_rescue**: B2@300 UNKNOWN, B5-MR TRUE under 300s
- **acceleration**: B2@300 TRUE, B5-MR TRUE with fewer refinements
- **no_effect**
- **parser_limited**: unsupported operations in benchmark

## 7. Required Tooling

Already available:
- B5 repair pipeline (dump, summarize, prompt, repair, validate, inject)
- B5-MR runner (multi-round loop)
- Output contract validator
- Deterministic LLM record/replay

Needed:
- Benchmark import script (copy + preprocess)
- Parser support check (quick scan for unsupported operators)

## 8. Next Steps

1. Download or locate external SV-COMP benchmarks (requires user approval)
2. Import scalar loop benchmarks
3. Run B2@60 + B2@300 pre-scan
4. Select targets with B2_TIMEOUT or B2_HARD@300
5. Run B5-MR evaluation
