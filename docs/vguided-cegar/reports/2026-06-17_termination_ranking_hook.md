# Termination Ranking-Function Hook — first full run (2026-06-17)

First end-to-end result for the v2.0 **termination ranking-function hook** (Class-B): an LLM proposes
candidate ranking functions (+ optional supporting invariants) for loops where LassoRanker's
template synthesis returns UNKNOWN; each candidate is verified by a decrease+bounded SMT check before
use (Tier S). Plan: [`TERMINATION_RANKING_HOOK_PLAN.md`](../TERMINATION_RANKING_HOOK_PLAN.md).

## Setup

| Item | Value |
|------|-------|
| Set | `termination_scalar` (146 tasks: 125 terminating / 21 non-terminating; termination-crafted + crafted-lit + numeric) |
| Config | lasso-only termination (`components/termination-composition-lassoBasedAnalysis.properties`), isolates the lasso route |
| Arms | `termination-stock` vs `termination-vguide` (same jar, `classes/` HEAD) |
| Timelimit | 60s CPU, parallel 8, `analysis.machineModel=Linux64` (LP64 tasks) |
| LLM | DeepSeek V4 non-thinking, env-gated `VGUIDE_TERMINATION_RANKING=on`, ≤1 call/loop |

## Results

| Arm | TRUE | FALSE | solved | wrong | UNKNOWN |
|-----|-----:|------:|-------:|------:|--------:|
| stock | 69 | 11 | **80** | **0** | 66 |
| **vguide** | **72** | 11 | **83** | **0** | 63 |

**NET +3 / 3 new wins / 0 lost / 0 wrong.** All 3 new solves are LLM-decided (template synthesis had
returned UNKNOWN); all verified by the SMT decrease+bounded check before use.

### The 3 verified wins (attribution)

| Task | Verified ranking function | Supporting invariant |
|------|---------------------------|----------------------|
| `BradleyMannaSipma-CAV2005-Fig1` | `y1 + y2` | `y1 > 0 ∧ y2 > 0` (verified inductive) |
| `LeikeHeizmann-WST2014-Ex9` | `x` | none |
| `twisted` | `k - i` | none |

`BradleyMannaSipma-CAV2005-Fig1` required the supporting invariant for the decrease check to hold —
it validates the v1 decision to co-synthesise `(f, I)` (the LLM's `I` is verified inductive, not
assumed). The other two are pure ranking functions outside LassoRanker's Affine/Nested templates.

## Soundness

0 wrong verdicts (independently re-checked: no `TRUE` on a non-terminating task, no `FALSE` on a
terminating one). The verifier is the backstop: the hook fires only after LassoRanker's
non-termination synthesis has already failed, and a candidate is accepted only if `I ∧ T ⟹ f(x') <
f(x)` and `I ∧ T ⟹ f(x) ≥ 0` (plus `I` inductive) are all UNSAT against the **real** loop transition
`T`. A non-terminating lasso cannot pass the decrease check, so the LLM can never flip a
non-terminating program to `TRUE`. The 11 non-terminating tasks stayed `FALSE`.

## Caveats

1. **60s, not competition 300s** — first validation; a 300s confirmation (and a longer per-loop cap)
   is the natural follow-up, mirroring the overflow P2 step.
2. **External DeepSeek API** — not a network-isolated competition run.
3. **Once-per-loop, first-verified-candidate** — no ensemble; many of the 56 terminating-UNKNOWN
   targets are timeouts or need non-linear / multi-phase measures outside the current linear-integer
   grammar. Headroom remains.
4. **run-to-run variance** — LLM non-determinism; the 3 wins are stable (verified, deterministic
   check), but the count can vary with timelimit.

## Provenance

- Code: `core/algorithm/termination/lasso_analysis/vguide/` (`RankingFunctionVerifier`,
  `RankingTermParser`, `RankingRelationFactory`, `LlmRankingFunctionProvider`) + `LassoAnalysis`
  fallback wiring + `LassoBuilder` StemAndLoop exposure. Unit tests: 14 passing (verifier 4, parser 10).
- Runs: `output/vguide/experiments/termination_scalar_termination_{stock,vguide}/`.
- Compare: `task,result` joined with `expected` from `benchmark_sets/termination_scalar.list`.

## Net

On a category VGuide had **never touched**, the ranking-function hook gives a clean, sound **+3** at
60s with **0 wrong / 0 lost** — including one win that needed a co-synthesised supporting invariant.
The verified-candidate-provider role generalises from predicates (reachability/overflow) to ranking
functions (termination), exactly as the roadmap proposed.

## Follow-up (2026-06-18): 300s, set scope, competition-net caveat

- **300s competition-grade (lasso-only, isolated)**: termination_scalar 146, stock vs vguide,
  parallel-6 → stock 80 → **vguide 84 (+4 / 0 lost / 0 wrong)**. stock is unchanged from 60s, so the
  UNKNOWNs are **template-unsolvable, not timeout-limited**; vguide +4 vs +3 at 60s is LLM
  nondeterminism. New code (diagnostic logging + verifier `Outcome`, repair OFF by default, no stem).
- **Cheap candidate-quality levers exhausted** (see `TERMINATION_RANKING_HOOK_PLAN.md` §13–14):
  prompt-strengthen (4→3), verify→repair (+0), stem-facts-in-prompt (4→2) all ≤ baseline; "adding
  context/instructions hurts; plain source + simple prompt is best". Best config = baseline.
- **Set scope (important)**: `termination_scalar` = termination-crafted + crafted-lit + numeric (146,
  integer ranking families). **NOT the full SV-COMP Termination category** (~1816 tasks; the big
  reactive dirs — product-lines/eca-rers2012/seq-mthreaded/… — are excluded as non-ranking targets).
  So these are hook-favourable scoped numbers, not a competition-category delta.
- **Competition-net caveat (lasso-isolated ≠ portfolio-net)**: this runs the *isolated* lasso config.
  The real SV-COMP termination branch is `terminationToSafety ∥ lassoBasedAnalysis` (+ recursion).
  **terminationToSafety has NO AI path** (probe RED 2026-06-15: CPAAlgorithm + `TerminationToReachCPA`
  memory-based recurrent-state detection, no predicate-CEGAR refinement; the ranking hook is
  lasso-only). It runs stock in parallel and may independently solve some of the hook's wins, so the
  competition-net gain (`svcomp27--termination` stock vs +hook) is **≤ the isolated +4**. This was
  **not measured (by decision, 2026-06-18)**: the gain is already small and the portfolio-net can
  only be smaller, so it would not change the conclusion.

## Bottom line (verdict)

The termination ranking-function hook is **implemented, sound, and gives a small clean gain**
(+3/+4 on the isolated lasso branch, **0 wrong / 0 lost**) on a scoped, hook-favourable
integer-termination set. Honest limits:

- **Small ceiling.** Cheap candidate-quality levers (prompt-strengthen, verify→repair, stem-context)
  are all exhausted — each ≤ baseline (plan §13–14). On the 56 stock-UNKNOWN targets the hook only
  *fires* on 9; **40 never produce a lasso** (pointer/array/string loops) and are structurally out of
  reach of this injection point.
- **Competition-net ≤ isolated, unmeasured by decision** — `terminationToSafety ∥ lasso`, and
  terminationToSafety has no AI path and runs stock in parallel.
- **Takeaway for future LLM-intervention work**: this point (LLM ranking functions on the lasso
  branch) has a small ceiling. Higher-impact opportunities lie elsewhere — the structural
  earlier-injection that would reach the 40 never-fired loops, or a different category/mechanism. The
  hook stays in as a validated, sound, opt-in building block (zero default overhead), not a headline
  result.
