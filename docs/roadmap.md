# Roadmap

Research decisions live in the [GitHub Wiki](https://github.com/swear01/cpachecker/wiki);
the sibling experiments checkout owns protocols, reports and logs.

## Active (2026-09-07)

1. **#203/#205 integration:** the qualified integration and Java/context
   successor are merged. Judge #178/#179 runtime and record-integrity work
   from merged code and current tests.
2. **#208 current checkpoint:** prepare the new-main 24-task-to-218 checkpoint
   under one freeze. Keep #180/#198's 66-cell old-runtime supplement separate
   from its 184-pair partial census.
3. **#109/#200 factual context:** the #109/#205 implementation is complete;
   finish production-trigger qualification in #206 and keep the #200 context
   A/B separate from the frozen checkpoint. #183's null wording experiment is
   complete; its cue is not adopted.
4. **#92 diagnostic cohort:** the original-symbol fix is complete, but the six
   excluded tasks still have three separate interpolation limitations. #197
   remains on safety hold with no accepted repair; do not treat diagnostic
   evidence as a solved issue.

## Status boundaries

- **Current cohort:** 218 = frozen 224 minus the six #92 tasks. The current
  stopped recovery has 184 matched pairs, not a full result. See
  [`HARD_218_MANIFEST_LINEAGE.md`](vguided-cegar/evaluation/HARD_218_MANIFEST_LINEAGE.md).
- **Historical only:** `full_scalar` 217, source-only census 245, broad
  Loops/portfolio 764. Preserve dated configs and manifests separately.
- **Current runtime facts:** `first_spurious`, SAFE-only, dump schema 12.
  Older schedules, schema ≤9 claims and frozen runtime bytes are not current
  defaults merely because an old report references them.
- **Completed mechanism evidence:** #172 and #181 do not establish population
  gains. #173 remains stopped/incomplete.

## Deferred

New full-cohort prompt variants, full764 relaunches and broad provider sweeps
need evidence and an explicit experiment budget. Completing code integration
does not itself launch a new experiment or overwrite a frozen one.
