# Plan

## Current entry point (2026-09-07)

- **#203 integration:** qualify independent changes, then merge harness,
  coverage and Java/context dependencies in sequence. Close overlapping PRs
  only after proving their useful content is in main. #177/#189 documentation
  is consolidated here with the newer #198 census.
- **#180/#198 checkpoint:** the authenticated hard-218 recovery stopped with
  184 matched pairs and two Stock-only executions. Stock/Augmented have
  16/17 correct and 11/11 wrong matched outcomes; 66 arm executions are absent.
  This is partial exploratory evidence, with no formal timing or PAR-2 claim.
  See [`HARD_218_MANIFEST_LINEAGE.md`](vguided-cegar/evaluation/HARD_218_MANIFEST_LINEAGE.md).
- **Pending-only supplement:** the sibling
  `reports/issue198-current-census/SUPPLEMENT_PLAN.md` enumerates 32 Stock and
  34 Augmented missing cells. Admission still requires an explicit stop-policy
  disposition, supported attached jobs, exact frozen runtime, budget and
  resource qualification. #197 has no accepted solver repair.
- **Context follow-up:** #190 fixes factual context; #200 supplies a separate
  bounded A/B design whose production-trigger qualification remains pending.
  The completed #183 wording A/B supports retaining baseline wording; #194
  is closed without merging its cue.

## Frozen boundaries

The comparable 218 cohort is exactly the immutable 224 parent minus six #92
array symbol-conflict tasks. Those six remain diagnostic until a verified fix
and a new comparison qualify them. Historical `full_scalar` (217), source-only
census (245), and broad Loops cohorts (764) have different roles.

The stopped recovery pins runtime `37064e4194a21b130b60f608e8b453a31a86a2db`;
new main commits are separate. Preserve its exact prompt/config/provider
identity for any admitted supplement. `first_spurious` and dump schema 12
are current runtime facts, but scheduling does not impose an unconditional
one-request limit: same-round repair and transport retries must be budgeted.

## Completed or deferred

- #181 compiler/LLM consumer fixtures are bounded mechanism evidence; PR #186
  supplies its provenance checker. No hard-218 solve-rate extrapolation.
- #172 five-fixture mechanism result is complete; #173 remains stopped and
  incomplete. #174 closed through #176 does not certify the six #92 cases.
- VGuide-NLA ordinary KI and final PDR/KI-PDR oracle gates remain STOP,
  0/12 target wins. Historical 764 replays do not reopen prospective full764.

Research decisions remain in the [GitHub Wiki](https://github.com/swear01/cpachecker/wiki);
protocols, results and raw evidence remain in `cpachecker-experiments`.
