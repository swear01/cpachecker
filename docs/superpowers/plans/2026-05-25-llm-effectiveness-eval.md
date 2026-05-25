# LLM Effectiveness Evaluation Plan

**Goal:** Demonstrate LLM-guided CEGAR reduces refinement count vs stock CPAchecker.

**Metric:** Number of predicate refinements (lower = better).

**Status:** Proof-of-concept on diamond_1-2: 51 → 26 (-49%).

---

## Phase 1: Benchmark Selection

Select 5-10 programs from the SV-COMP vguided set where:
- Stock CPAchecker takes ≥ 10 refinements (otherwise too trivial to show improvement)
- Program has clear loop invariants (linear arithmetic, no arrays/pointers)
- Stock successfully verifies within time limit

| Priority | Category | Examples |
|----------|----------|----------|
| High | loop-acceleration | diamond_1-1, diamond_1-2, phases_1-1, underapprox_1-1 |
| High | loop-crafted | simple_array_index_value_1-1 |
| Medium | loops | count_up_down-1, eureka_01-2 |
| Medium | loop-invariants | linear-inequality-inv-a, even, odd |

Filter criteria:
- `refinements >= 10` in stock baseline
- `result != UNKNOWN` (stock can solve it)
- Simple arithmetic (V parser can handle)

---

## Phase 2: Experiment Setup

**For each benchmark:**
1. Run stock CPAchecker (3 times, record min/median/max refinements)
2. Run V-guided CPAchecker (3 times, same)
3. Compare median refinement counts

**Configuration:**
```
Stock:
  --predicateAnalysis --timelimit 300s --heap 8000M

V-guided:
  --predicateAnalysis --timelimit 300s --heap 8000M
  --option cpa.predicate.refinement.useVocabularyGuide=true
  OPENROUTER_API_KEY=... OPENROUTER_TIMEOUT_SECONDS=60
  unset OPENROUTER_REASONING_TOKENS
```

**Run command:**
```bash
scripts/cpa.sh --predicateAnalysis --stats --no-output-files \
  --timelimit 300s --heap 8000M \
  --spec config/specification/default.spc \
  [--option cpa.predicate.refinement.useVocabularyGuide=true] \
  <program>
```

**Extract from stats output:**
- `Number of predicate refinements`
- `V-injection attempts / successes / fallbacks`
- `V SMT-validated predicates / V SMT-failed predicates`
- `Total time for CPAchecker`
- `Verification result`

---

## Phase 3: Results Table

```
| Program              | Stock Refs | V-guided Refs | Δ%   | V-Inj Success | SMT Validated |
|----------------------|------------|---------------|------|---------------|---------------|
| diamond_1-2          | 51         | 26            | -49% | 25/26 (96%)   | ???           |
| diamond_1-1          | ??         | ??            | ??   | ??            | ??            |
| ...                  |            |               |      |               |               |
```

---

## Phase 4: Analysis

For programs where V-guided reduces refinements, check:
1. **What V predicates were generated?** (extract from `LLM: [ N?? ] -> [preds]`)
2. **Which locations got V predicates?** (N-prefix matching)
3. **How many passed SMT validation?** (validated vs failed count)
4. **Did the key invariant appear at the right location?**

For programs where V-guided does NOT reduce refinements, check:
1. Was V_0 empty? (LLM API failure)
2. Did V predicates not match any ABA location? (location mismatch)
3. Were all V predicates SMT-failed? (parser/formula compatibility issue)

---

## Phase 5: Deliverables

1. **Results table** with refinement counts and Δ%
2. **V quality analysis** per program (predicates generated, validated, injected)
3. **Case study** on the best and worst performing program
4. **Summary**: average Δ% across benchmarks, V-injection success rate
