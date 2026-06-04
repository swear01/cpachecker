# Advisor Index: Bootstrap + B5-MR Rescue

## Start Here

1. [Meeting Notes](MEETING_NOTES_RESCUE.md) — agenda, main table, demo plan, questions
2. [Advisor Update](ADVISOR_UPDATE_RESCUE.md) — longer summary with method explanation
3. [Final Tables](FINAL_TABLES_FOR_REPORT.md) — all result tables
4. [Pipeline Diagram](FIGURE_PIPELINE_ASCII.md) — ASCII pipeline + claim hierarchy

## Core Documents

- [Integrated Synthesis](INTEGRATED_RESCUE_SYNTHESIS.md)
- [Method Specification](METHOD_SPECIFICATION.md) — algorithms
- [Paper Skeleton](PAPER_SKELETON.md) — abstract + 8 sections
- [Oral Summary](ORAL_SUMMARY_RESCUE.md) — 2-3 minute script
- [5-Minute Script](FIVE_MINUTE_PRESENTATION_SCRIPT.md) — timed presentation

## Evidence

- [Claim-to-Evidence Map](CLAIM_TO_EVIDENCE_MAP.md) — 7 claims with evidence
- [Bootstrap Rescue Case Studies](BOOTSTRAP_RESCUE_CASE_STUDIES.md)
- [Level 1 Results](ARRAY_PRESENT_SCALAR_LEVEL1_RESULTS.md)
- [Failure Analysis](case_studies/failure_analysis.md)

## Reproducibility

- [Demo Guide](ADVISOR_DEMO.md) — how to run demos
- [Demo Checklist](ADVISOR_DEMO_CHECKLIST.md) — before/during/if-fails
- [Artifact Index](ARTIFACT_INDEX.md) — scripts + results
- [Predicate Sets](predicate_sets/) — frozen bootstrap predicates

## Case Studies

| Case | File | Status |
|------|------|--------|
| up | [case_studies/up.md](case_studies/up.md) | stable confirmed rescue |
| down | [case_studies/down.md](case_studies/down.md) | confirmed rescue |
| string_concat-noarr | [case_studies/string_concat-noarr.md](case_studies/string_concat-noarr.md) | stabilized rescue |
| array_3-1 | [case_studies/array_3-1.md](case_studies/array_3-1.md) | Level 1 rescue |
| half_2, seq-3 | [case_studies/failure_analysis.md](case_studies/failure_analysis.md) | context unlocked only |

## Live Demo

```bash
bash scripts/vguided-cegar/run_advisor_demo.sh array-level1
```

Expected: TRUE, 1 refinement, ~30s. 0 select/store.

## Future Work

- Level 2 simple select/store predicate support
- Broader benchmark search (pool currently exhausted)
- Multi-round B5-MR for context-unlocked cases
- Formal paper draft
