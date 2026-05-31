# Claim-to-Evidence Map

## Claim 1: B5-MR alone cannot handle zero-context timeouts

**Status**: validated

**Evidence**: Official SV-COMP CPAchecker TIMEOUT diagnostic (20 tasks, all ZERO_CONTEXT_TIMEOUT). 0 refinements, 0 context dumps. B5-MR requires spurious counterexample traces, interpolants, and candidate fates — none available on zero-context timeouts.

**Files**: `results/vguided-cegar/official_timeout_context/context_diagnostic_v2.md`, `docs/vguided-cegar/INTEGRATED_RESCUE_SYNTHESIS.md`

**Caveat**: True stock CPAchecker (no LLM vocabulary) may be even harder. Local baseline uses `useVocabularyGuide=true` for B2 context.

## Claim 2: Bootstrap unlocks CEGAR context on zero-context timeouts

**Status**: validated (11/11 = 100%)

**Evidence**:
- Scalar: up (43r), down (37r), string_concat-noarr (52-57r), half_2 (67r), seq-3 (43r)
- Level 1: array_3-1 (1r solved), heapsort (8r solved), id_build (1r solved), large_const (5r solved), array_3-2 (47r), array_4 (62r)

**Files**: Individual reproduction CSVs under `results/vguided-cegar/bootstrap_rescue_cases/`

**Caveat**: Context unlock = refinements + dumps produced, not solved.

## Claim 3: Bootstrap+B5-MR rescues selected scalar zero-context timeouts

**Status**: validated (2 directly reproducible, 1 stabilized)

**Evidence**: up (3/3), down (2/3), string_concat-noarr (3/3 fixed-predicate replay, originally 1/3)

**Files**: `results/vguided-cegar/bootstrap_rescue_cases/*/reproduction.csv`, `results/vguided-cegar/rescue_package/final_rescue_accounting.csv`

**Caveat**: string_concat-noarr needs fixed-predicate replay for stability (original instability was LLM-side SSA-name contamination).

## Claim 4: Rescue requires relational predicate combinations

**Status**: validated (ablation on up)

**Evidence**: `k=i` alone → UNKNOWN. `k=n-j` alone → UNKNOWN. Both together → TRUE.

**Files**: `docs/vguided-cegar/case_studies/up.md`, `results/vguided-cegar/rescue_package/key_predicate_ablation.md`

**Caveat**: Ablation done on one case only (up). Generalization assumed but not proven across all rescue cases.

## Claim 5: Variable-name table is necessary

**Status**: validated

**Evidence**: Pre-fix: SA-name contamination on multiple benchmarks (rejected). Post-fix: 0 validator rejects in final successful pipeline. string_concat-noarr instability root cause was SA-name contamination in BB5-MR runs 1-2.

**Files**: `docs/vguided-cegar/b5_mr_failure_analysis.md`, `docs/vguided-cegar/case_studies/string_concat-noarr.md`

**Caveat**: The fix prevents SA-name output but doesn't guarantee source-level names on all prompts. Future prompt variants should be tested.

## Claim 6: Level 1 array-present scalar-bottleneck works without array theory

**Status**: validated

**Evidence**: 6 candidates evaluated. 4/6 bootstrap-only TRUE. 6/6 context unlocked. 0 select/store generated. No array theory implemented.

**Files**: `docs/vguided-cegar/ARRAY_PRESENT_SCALAR_LEVEL1_RESULTS.md`, `docs/vguided-cegar/case_studies/array_3-1.md`

**Caveat**: 6 is a small sample. Only array-present with scalar assertion. The classifier may have false positives/negatives on unseen benchmarks.

## Claim 7: Soundness is preserved

**Status**: validated by design

**Evidence**: All LLM predicates enter PredicateCPA precision only — they are tracked as Boolean features, not trusted as invariants. CPAchecker's CEGAR loop proves TRUE/FALSE. Output validator rejects internal SSA symbols and unsupported operators.

**Caveat**: If a predicate accidentally encodes a contradiction (e.g., `(= x (_ bv0 32))` when x is always 1), PredicateCPA may produce FALSE or UNKNOWN, but should not produce an unsound TRUE.

## Non-Claims (explicitly NOT claimed)

| Non-claim | Reason |
|-----------|--------|
| General solver improvement | Only selected cases rescued |
| Full array theory support | No select/store implemented |
| Pointer/heap support | Out of scope |
| LLM proves properties | CPAchecker proves, LLM provides precision predicates |
| All timeouts are rescued | Only 11 cases evaluated, 4 scalar/Level-1 rescues |
| Deterministic without cache | LLM output varies; fixed-predicate replay needed for stability |
