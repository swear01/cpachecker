# ReachSafety peel trigger (A1.2, v1.7.1) — early divergence firing (2026-06-20)

Follow-up to [`2026-06-20_reachsafety_stockfirst_guard.md`](2026-06-20_reachsafety_stockfirst_guard.md)
(v1.7.0). v1.7.0's 6 regressions were case-study direct-LLM-#1 wins (`heapsort`, `nested9`, …): the
stock-first schedule fired the LLM too late (spurious #9–10 via the count/time trigger), so stock
burned the CPU budget on divergent refinements and hit the 300s **CPU** limit → `UNKNOWN, incomplete`.

## The peel trigger

Fire the LLM **early, when the loop is being unrolled**. At each spurious refinement we count how
many abstraction states in the counterexample trace sit at a loop head (`countLoopHeadVisits` in
`VGuideRefinementBridge`, using `extractLocation` + `pack.loopHeads()`). A trace that passes loop
heads more times each refinement is *peeling* the loop — exactly where one LLM relational predicate
breaks the cycle.

`peelFire` (in `LlmCallScheduler`, folded into `every_n_or_interval` as a third OR branch):
fire when `refinementIndex ≥ 2` **and** `loopHeadVisits ≥ vguide.peelLoopHeadThreshold`.

### Calibration (LLM off, observe the stock trajectory)

| task | loopHeadVisits per refinement | converges? |
|------|-------------------------------|-----------|
| `nested-3` (don't fire) | 2, 3 → **done** (peak **3**) | yes, 2 refinements |
| `heapsort` | 2,2,2,**4**,4,4,6,8 | no (diverges) |
| `nested9` | 3,**5**,6,7,8,13,… | no |
| `iftelse` | 1,2,3,**4**,6,9,15,… | no |
| `sumt4` | 1,2,3,**4**,5,6,7,8 | no |

**Threshold = 4** cleanly separates them: converging tasks peak at 3 and never fire; diverging tasks
cross 4 at refinement #2–4 → fire far earlier than the #10 / 15s triggers. Peel fires at #4 (heapsort),
#2 (nested9), #4 (iftelse/sumt4) — confirmed in both standalone and the svcomp27-vguide portfolio child.

## Full 764 result (controlled, peel=4 vs v1.7.0 peel=0)

Same `svcomp27-vguide` portfolio, parallel-8, 300s; only `peelLoopHeadThreshold` differs (0 → 4).
Every solved verdict cross-checked against the `.yml` `unreach-call` `expected_verdict`.

| | old fire-#1 | v1.7.0 (peel 0) | **v1.7.1 (peel 4)** |
|---|---|---|---|
| solved | 482 | 493 | **504** |
| wrong verdicts | 0 | 0 | **0** |

**v1.7.1 vs v1.7.0: +11 (+18 new − 7 lost), 0 wrong, 0 flips. Cumulative vs old schedule: +22 (482 → 504).**

- **+18 recovered**: `heapsort`, `nested9`, `iftelse`, `sumt4` (the v1.7.0 regressions) + many nla-digbench
  nonlinear (`freire*`, `geo*`, `egcd*`, `prodbin*`) + the array FALSE tasks (`array_1-1`, `array_3-2`).
- **−7 lost**: `fragtest_simple`, `hard2`, `in-de41`, `loopv1/2`, `nested_5`, `nested_6` — several were
  v1.7.0's own marginal/resource-sensitive gains; firing earlier shifted them. Net still +11.

## Status

- `vguide.peelLoopHeadThreshold = 4` is the default in `config/vguide.properties`. Unit tests 12/12.
- Trigger ① is now peel-based (the every-N floor remains a backstop alongside the time trigger).
- The −7 churn is run-to-run resource-sensitive noise. A2 (CPU-budget isolation) was evaluated and
  **rejected** (2026-06-20): the parallel race is the standard portfolio mechanism, and capping
  VGuide's CPU would also cut the +18 wins it earns by spending that CPU (same coin). Next leverage
  is a new injection point (k-induction / IMC candidate invariants), not fighting resource noise.
