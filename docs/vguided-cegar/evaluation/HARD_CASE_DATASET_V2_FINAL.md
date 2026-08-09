# Hard-case Dataset v2 final evidence

Issue [#16](https://github.com/swear01/cpachecker/issues/16) is closed only through the PR that adds this record. The immutable evidence bundle is [hard-case-dataset-v2-final-20260809](https://github.com/swear01/cpachecker/releases/tag/hard-case-dataset-v2-final-20260809).

## What is final

- Cap-8 candidate dataset: 270 classified tasks; 248 primary hard candidates. Its historical formal ledger is unchanged.
- Cap-16 candidate manifest: **224 distinct tasks**.
- Cap-16 final validation consists of two repetitions: repetition 1 is 224 rows (161 preserved seed rows plus 63 completed here); repetition 2 is 224 rows completed here.
- The final release's new Cap-16 ledger records **287 accepted rows** (`63 + 224`), while the full two-repetition validation corpus is **448 rows over 224 distinct tasks**.

Do not describe 287 as 287 distinct validation cases.

## Acceptance and provenance

The final release contains 40 attempt terminals and matching per-attempt anchors. Its final scheduler ledger has pending `0 + 0`; status totals for its 287 newly accepted rows are 181 TIMEOUT, 63 OUT OF MEMORY, 27 `false(unreach-call)`, 13 `true`, and 3 SEGMENTATION FAULT.

Six registered operational corrections are included with evidence. They preserve task identities, verifier configuration, limits, and accepted measured rows. The scheduler is evidence/replay-inspection material, not a portable runtime because it uses deployment-specific paths.

## Use by subsequent agents

Treat the final release's `final-summary.json` and `FINALIZATION-SHA256SUMS` as the authority for this dataset. Before using it in any new validation, download the release, verify its outer SHA-256 and `FINALIZATION-SHA256SUMS`, and keep the 224-task manifest fixed. Issue [#2](https://github.com/swear01/cpachecker/issues/2) owns the next A/B/C/D evaluation contract; augmented outcomes must not alter this dataset.
