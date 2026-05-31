# Meeting Notes: Bootstrap + B5-MR Rescue

## 1. Current Checkpoint

- **Commit**: `1a3c9963`
- **Status**: advisor-demo-ready
- **Live demo validated**: array-level1 (TRUE, 1 ref, ~30s)
- **Audit**: 0 overclaims, 0 secrets in tracked docs

## 2. One-Sentence Claim

Bootstrap + B5-MR rescues selected PredicateCPA zero-context timeouts by using LLM-generated precision predicates to unlock CEGAR context and then repair abstraction precision, while CPAchecker remains the sound proof engine.

## 3. Five-Minute Narrative

1. **Problem**: PredicateCPA can timeout before producing any CEGAR context — zero refinements, zero traces, zero interpolants.
2. **B5-MR alone fails**: trace-guided repair needs traces; zero-context timeouts provide none.
3. **Bootstrap**: LLM generates initial precision predicates from source code + assertion. Injected into precision (not trusted as invariants). Unlocks CEGAR context.
4. **B5-MR**: Uses newly available traces/interpolants to discover relational predicates. Variable-name table prevents SSA-name contamination.
5. **Results**: up (3/3), down (2/3) directly reproduced rescues. string_concat-noarr stabilized via fixed-predicate replay (instability was LLM-side).
6. **Level 1**: Array-present benchmarks work when bottleneck is scalar (4/6 rescued, 0 select/store, no array theory needed).
7. **Soundness**: LLM predicates are precision-only. CPAchecker proves.

## 4. Main Result Table

| Category | Cases | Result |
|----------|-------|--------|
| Scalar rescue | up, down, string_concat-noarr | solved-from-UNKNOWN |
| Context unlocked | half_2, seq-3 | context appears, not solved |
| Level 1 rescue | array_3-1, heapsort, id_build, large_const | bootstrap-only TRUE |
| Level 1 unlocked | array_3-2, array_4 | context appears, not solved |

## 5. Live Demo Plan

```bash
bash scripts/vguided-cegar/run_advisor_demo.sh array-level1
```

Expected: TRUE, 1 refinement, ~30s, 0 select/store.

Backup dry-runs:
```bash
bash scripts/vguided-cegar/run_advisor_demo.sh scalar-up --dry-run
bash scripts/vguided-cegar/run_advisor_demo.sh context-unlock --dry-run
```

## 6. If Demo Fails

- Show `FINAL_TABLES_FOR_REPORT.md` with tracked results.
- Show `CLAIM_TO_EVIDENCE_MAP.md` for evidence mapping.
- Explain LLM/API/toolchain variance may cause different output.
- Do not claim live success if it fails.

## 7. Soundness Story

- LLM predicates enter PredicateCPA precision only — Boolean features to track.
- They are NOT trusted invariants; CPAchecker's CEGAR proves TRUE/FALSE.
- Output validator rejects SSA names, internal symbols, unsupported operators.
- Wrong predicates may harm performance but do not produce unsound TRUE.

## 8. Limitations

- 11 benchmarks total, targeted not general
- No full array theory (Level 1 only: array-present, scalar bottleneck)
- No pointer/heap/aliasing
- string_concat-noarr needed fixed-predicate replay
- LLM output variance exists
- Benchmark pool exhausted

## 9. Questions to Ask Advisor

1. Is targeted rescue enough for a project/report?
2. Should next step be broader benchmark search or deeper case studies?
3. Should Level 2 simple select/store be pursued?
4. Position as precision synthesis rather than invariant generation?
5. Which venue/style should the report target?

## 10. Next-Step Options

| Option | Effort | Risk |
|--------|--------|------|
| A. Broader benchmark search | medium | may find no more rescues |
| B. Stabilize more scalar rescues via replay | low | incremental |
| C. Level 2 simple select/store support | medium | parser extension |
| D. Improve classifier | low | incremental |
| E. Write formal report/paper draft | low | documentation |
