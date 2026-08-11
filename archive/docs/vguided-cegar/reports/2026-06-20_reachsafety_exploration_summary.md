# ReachSafety LLM-improvement exploration — stage summary (2026-06-20)

Wrap-up of the post-FM-submission push to raise the ReachSafety (Loops, 764) solve rate. Records what
shipped, what was investigated and **deliberately not pursued** (with reasons, so it is not
re-litigated), and where the remaining headroom actually is.

## Shipped (validated, sound)

Controlled full-764 `svcomp27-vguide` runs, only the LLM-call schedule differs; every solved verdict
cross-checked against the task `.yml` `expected_verdict`.

| step | mechanism | full 764 | net | report |
|------|-----------|----------|-----|--------|
| baseline | old fire-at-#1 schedule | 482 | — | — |
| **v1.7.0** | stock-first schedule (`every_n_or_interval`, K=10/D=15s; never fire at #1) | **493** | +11 (0 wrong) | [stockfirst_guard](2026-06-20_reachsafety_stockfirst_guard.md) |
| **v1.7.1** | peel trigger (fire early when CE unrolls a loop, loop-head visits ≥ 4) | **504** | +11 (0 wrong) | [peel_trigger](2026-06-20_reachsafety_peel_trigger.md) |

**Cumulative +22 (482 → 504), 0 wrong, 12/12 unit tests.** Tags `vguide-v1.7.0`, `vguide-v1.7.1`.
Both are Tier R (only *when* the LLM fires; predicates still SMT-verified) — soundness untouched.

## Investigated and NOT pursued (with reasons)

1. **A2 — portfolio CPU-budget isolation → rejected.** The parallel race (`ParallelAlgorithm`,
   one thread/child, shared global `limits.time.cpu`, no per-child cap) is the *standard* mechanism,
   not broken. VGuide's "greed" is the same coin that wins the +18 and loses the −7; a blunt cap
   would cut the wins too, and the −7 is run-to-run resource noise. Low ROI.
2. **nla-digbench nonlinear → out of mechanism scope (≈70% of remaining UNKNOWN).** Evidence:
   `cohencu-ll` asserts `x==n*n*n`, `y==3n²+3n+1` (cubic/quadratic); loop-head visits stay ≤ 3 (no
   peeling — divergence is *nonlinear*, not loop-unrolling); ~37 s **CPU per refinement** (nonlinear
   SMT is the bottleneck). Across all ~480 nla-digbench, 298 are already solved (289 **without** the
   LLM, by stock/siblings) and only **9** were ever solved *with* the LLM fired — all `divbin`/`hard`/
   `lcm` (near-linear); never the truly nonlinear `cohencu`/`prodbin`/`geo`/`freire`. Linear predicate
   abstraction is the wrong tool; cracking these needs nonlinear invariant synthesis — a separate
   research effort, deferred.
3. **Peel-aware prompt (sharpen the prompt with the diverging loop) → low confidence, deferred.**
   The 47 linear fired-but-failed already get heavy treatment (mostly 5 LLM rounds, 20–45 refinements)
   and the prompt already lists loop heads + asks for loop-carried relations. Their failure looks like
   precision pollution / quality ceiling, not "didn't know which loop." A sharper hint is a gamble
   (and the ablation already showed extra context degrades). Not worth it now.
4. **FALSE / bug-finding → right idea, wrong tool in CPAchecker; deferred.** v1.5's BUG-prompt
   attempt failed (40→38, 0 new FALSE): it injected **predicates** (the artifact for *proving safe*)
   on **spurious** CEs (which can't reach the real error). SOTA LLM bug-finding (HGFuzzer, Locus,
   OSS-Fuzz) instead has the LLM produce **concrete inputs / seeds / harnesses**, verified by
   **execution (directed fuzzing)** — which also sidesteps the nonlinear wall (run an input, don't
   prove an invariant). But **CPAchecker's svcomp config has no fuzzer** (only a toy
   `RandomTestGeneratorAlgorithm` + symbolic test-gen, both in the separate Test-Comp track), so this
   needs a new concrete-execution hook — heavyweight; deferred.

## Where the remaining headroom is (260 UNKNOWN, post-v1.7.1)

- ~70% **nla-digbench nonlinear** → needs nonlinear capability (out of current mechanism).
- ~58 non-nonlinear UNKNOWN-TRUE → at the predicate quality/pollution ceiling (cheap levers spent).
- 81 are actually **FALSE** (61 nonlinear) → only reachable by execution-based bug-finding (no fuzzer in CPAchecker).

## Conclusion

The cheap LLM-on-predicate levers for ReachSafety are exhausted at **+22 / 0 wrong (504/764)** — a
clean, sound stopping point. Further gains require a **new capability** (nonlinear invariant synthesis,
a new injection point such as k-induction/IMC candidate invariants, or execution-based bug-finding),
all high-cost. **Stage paused at v1.7.1.**
