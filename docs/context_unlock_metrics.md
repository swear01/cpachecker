# Context Unlock Metrics

## Before vs After

| Metric | Before Bootstrap | After Bootstrap |
|--------|-----------------:|----------------:|
| Status | ZERO_CONTEXT_TIMEOUT | context_unlocked |
| Refinements | 0 | 39 |
| Context dumps | 0 | 3 |
| Spurious traces | none | yes (12 locations) |
| Interpolants per refinement | 0 | 2 |
| Block formulas per abstraction | 0 | 3 |
| V-FATE ENTAILED predicate count | 0 | 4 |
| V-FATE ABSTRACTION-CANDIDATE count | 0 | 2 |
| V-injection successes | 0 | 2 interpolants strengthened |
| B5-MR operable | no | yes |
| B5-MR attempted | n/a | yes (round 1) |
| B5-MR new valid repair predicates | n/a | 0 (SSA-name rejected) |
| Benchmark solved | no | no |

## Bootstrap Predicates

| # | Predicate | V-FATE | Fate Location |
|---|-----------|--------|---------------|
| 1 | `(bvsge i (_ bv0 32))` | ENTAILED | N30 (first loop entry) |
| 2 | `(bvsge k (_ bv0 32))` | ENTAILED | N30 |
| 3 | `(bvslt i n)` | ABSTRACTION-CANDIDATE | N30 |
| 4 | `(= k i)` | ENTAILED | N30 (key: k tracks i) |
| 5 | `(bvsge n (_ bv0 32))` | ABSTRACTION-CANDIDATE | N30 |
| 6 | `(bvsgt k (_ bv0 32))` | (bounds support) | — |
| 7 | `(bvsle i n)` | (bounds support) | — |
| 8 | `(bvsge k (_ bv1 32))` | (inductive hint) | — |

## B5-MR Generated (Rejected)

| Predicate | Reason |
|-----------|--------|
| `(bvslt |main::i| |main::n|)` | REJECT_INTERNAL_SYMBOL |
| `(= |main::k| |main::i|)` | REJECT_INTERNAL_SYMBOL |
| `(bvslt |main::j| |main::n|)` | REJECT_INTERNAL_SYMBOL |
| `(bvsgt |main::k| (bvsub |main::n| |main::j|))` | REJECT_INTERNAL_SYMBOL |
| `(bvsle |main::j| |main::k|)` | REJECT_INTERNAL_SYMBOL |
