# Demo Fallback Notes

## If array-level1 demo fails

Say: "The demo was validated at commit `1a3c9963`. It previously produced TRUE, 1 refinement, 8 scalar predicates, 0 select/store. Live failure may be environment, LLM API, or toolchain variance. Let me show the tracked evidence instead."

## Evidence to show immediately

1. **Result table**: `FINAL_TABLES_FOR_REPORT.md` — shows all rescues and counts.
2. **Claim-to-evidence**: `CLAIM_TO_EVIDENCE_MAP.md` — maps every claim to data.
3. **Case study**: `case_studies/array_3-1.md` — the demo case in detail.
4. **Advisor update**: `ADVISOR_UPDATE_RESCUE.md` — longer narrative.

## Commands to show (even if live fails)

```bash
bash scripts/vguided-cegar/run_advisor_demo.sh --help
bash scripts/vguided-cegar/run_advisor_demo.sh array-level1 --dry-run
bash scripts/vguided-cegar/run_advisor_demo.sh scalar-up --dry-run
```

These prove the pipeline exists and is scripted.

## What NOT to say

- Do NOT claim "it works, just the API failed."
- Do NOT blame CPAchecker without evidence.
- Do NOT expand the claim beyond tracked results.
- Do NOT promise it will work if we just fix one thing.
- Do NOT hide the failure — acknowledge it and pivot to tracked evidence.
