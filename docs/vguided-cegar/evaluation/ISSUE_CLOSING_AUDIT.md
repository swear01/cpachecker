# Issue Closing Audit (2026-08-14)

Requested by the user: before closing the completed-but-open issues below, verify the
completion claims via bot review. Evidence links and residual risks for each item.

## #71 — regression: base analysis no longer stops at its CPU-time limit

- **Claim:** fixed by PR #72 (`fix(harness): wall timeout = TIMELIMIT (grace 0)`).
- **Evidence:** merged `43096fa550`; TIMEOUT_GRACE 30→10, recorded wall capped at
  TIMELIMIT, TIMELIMIT/TIMEOUT_GRACE validation; `test_core_only_harness.py` 10 passed.
- **Residual risk:** the 224 and 764 run data were produced by the pre-fix harness
  (wall 330s for 300s CPU tasks). PAR-2 absolute values are inflated; relative
  stock-vs-augmented comparisons remain valid.

## #66 — harvest: 764-line svcomp26-vguide full-set run with V4 Pro (OpenCode gateway)

- **Claim:** harvest posted.
- **Evidence:** `cpachecker-experiments/docs/vguided-cegar/reports/2026-08-13_full764_v4pro_official_harvest.md`
  — 502 solved (vs June 493), PAR-2 80.5, 242 LLM rounds, 0 failures.
- **Residual risk:** pre-#72 harness wall inflation; opencode-go ~1.5x cost → #73.

## #67 — verify: LLM candidate rejection rate after the array vocabulary bridge

- **Claim:** reject-rate measured and posted.
- **Evidence:** 30-task verification: 24.6% → 5.6% → 0.0% (reject_rate_verify* runs).
- **Residual risk:** measured on the 30-task sample, not the full 224.

## #55 — repository cleanup: experiments/docs/logs → sibling directory

- **Claim:** main cleanup done.
- **Evidence:** docs/output/archive/report/slides/artifact moved to
  `/home/swear01/cpachecker-experiments/`; AGENTS.md points there; repo is code-only.
- **Residual risk:** benchmark_sets/predicate_sets/evaluation stay in-repo (referenced
  by scripts/config); the sibling directory is not version-controlled.

## #58/#59 — vguide root cause: no vocabulary bridge for array-element predicates

- **Claim:** fixed by PR #62 (ArrayTermTranslator + VocabularyGuide select/bvshl/
  sign_extend/udiv, varBits, contract/prompt), follow-ups #68/#69/#70 merged.
- **Evidence:** merged PRs #62/#69/#70; ARRAY_VOCABULARY_BRIDGE_SPEC.md updated.
- **Residual risk:** kept as reference issues (root-cause history); closing is cosmetic.

## Not closing (still active)

- #73 provider decision (waiting on the V4-Flash run #76), #54 triage policy,
  #63 official-Pro 764 (possibly superseded by Flash), #56 cross-validation,
  #46/#39-#45 epic tracking.
