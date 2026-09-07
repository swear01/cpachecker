# Hard-218 manifest lineage

Current documentation snapshot: 2026-09-07. The accepted exploratory cohort
is the 218-task child of the frozen 224-task parent. The stopped #180 recovery
has 184 matched pairs; a complete current 218-pair result is still unavailable.
These hashes identify bytes outside this repository; do not regenerate either
manifest during a run.

| Role | Count | SHA-256 | Selection/exclusion | Latest accepted run | Caveat / next action |
|---|---:|---|---|---|---|
| Frozen hard-case parent, `runs/candidate-manifest-224.json` | 224 | `7ad21cb5ca4360689f00dca6f3a5eb7ec2385b9793315cfe5828892ded0ab49f` | Stock-only hard-case selection | 2026-08-11 224×2 verdict-only evidence | Six #92 array symbol-conflict tasks remain diagnostic; no timing claim |
| Accepted comparable child, `manifests/candidate-manifest-218.json` | 218 | `3350720a0c643cf9557c76dafd67ab2aed10d692f5ea50cbd2515fe5ab5f3bb6` | Parent minus the six explicit #92 tasks below | Stopped #180 recovery: 184 matched pairs | 32 Stock + 34 Augmented executions absent; see #198 census and supplement plan |
| Historical `full_scalar` | 217 | N/A (list, not this manifest) | `RUN_SCALAR` minus `id_build`, `half_2`, `seq-3` | Legacy runs only | Not the current hard-case evaluation |
| Historical source-only mechanism census | 245 | N/A | Census population | 2026-08-25 mechanism census | Capability evidence, not solve-rate evidence |
| Historical broad Loops/portfolio cohort | 764 | N/A (multiple dated manifests/configs) | Broad historical cohort; not hard-218 | v1.5.1/v1.7.x dated replays | Preserve exact config/version distinctions; prospective full764 is stopped |
| Compiler consumer fixtures | 5 | N/A (fixture manifests) | Bounded #170/#172/#173 mechanism sets | #172 C3b: 2 TRUE, 3 UNKNOWN | Mechanism evidence only; #173 matrix remains STOP |

## Exact 224 → 218 derivation

The child records parent SHA-256
`7ad21cb5ca4360689f00dca6f3a5eb7ec2385b9793315cfe5828892ded0ab49f` and the
same `unreach-call.prp` property hash
`0c6a90cfc3ad4545225a0537ddc37b8a11ea5a37b906c053bb298b748f810150`. The six-task exclusion ledger advertised
by the source PR has SHA-256
`a1e9812ac92e601bda8163cf6348f0a3bc13855c2b295c0d38666ab83871ac8f`. Its 218
task rows are the parent rows in the same order. Every compared row field matches: task identity/path,
source/property hashes, expected label, data model, family, benchmark set,
seed/provenance and license fields.

The excluded diagnostic stratum is exactly:

- `c/array-crafted/zero_sum2.yml`
- `c/array-patterns/array5_pattern.yml`
- `c/array-patterns/array13_pattern.yml`
- `c/array-patterns/array19_pattern.yml`
- `c/array-patterns/array27_pattern.yml`
- `c/array-patterns/array29_pattern.yml`

These six are excluded from comparable mechanism evaluation; they are not
UNKNOWN or solved evidence. Re-admission requires a verified #92 fix and a new
preregistered comparison. PR #99 advertised historical 218 hash
`a969cad2e01bdeaa21a6bb54f90199b864264c63449002f5e143f5578cf9ed6a`; it is
retained as a discrepancy and is not substituted for the authenticated current
bytes above.

## Current navigation boundary

The production default is `first_spurious`, SAFE-only, Meta
`muse-spark-1.2-contributor`, minimal reasoning, and dump schema 12. The owner
authorized exploratory execution for trend evidence only; it does not reopen
stopped artifacts or relax crash/provider/official-label classification. See
the [GitHub Wiki](https://github.com/swear01/cpachecker/wiki) for decisions and
`/home/swear01/cpachecker-experiments/` for protocol, logs and reports.

## Current checkpoint versus current main

The [#198 census](https://github.com/swear01/cpachecker/issues/198) reports
184 matched pairs: Stock/Augmented have 16/17 officially correct, 11/11
officially wrong, and 157/156 unresolved outcomes. Two additional Stock-only
executions leave 66 absent arm executions. These are partial exploratory
observations; they do not establish 218 completed pairs, zero wrong results,
a repeatable prompt gain, or formal timing results.

That recovery freezes runtime commit
`37064e4194a21b130b60f608e8b453a31a86a2db`, default prompt, compiler OFF and
L3 OFF. [#203 integration](https://github.com/swear01/cpachecker/issues/203)
advances main separately. Merging code does not change the frozen run or
authorize filling its missing cells with a different runtime. The supplement
plan retains unresolved stop-policy, attached-job, runtime, budget and resource
admission checks. #197 has no accepted solver repair.

Evidence and the pending-only plan are in the sibling experiment checkout:
`reports/issue198-current-census/REPORT.md` and `SUPPLEMENT_PLAN.md`. The
completed [#183 wording A/B](https://github.com/swear01/cpachecker/issues/183)
had 2 TRUE / 6 timeouts in each arm; PR #194 was closed without adopting the
cue. Factual context work in #190 is a separate change.
