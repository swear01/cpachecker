# Source-Prior Ablation Report (2026-06-17)

**Question:** Does CE context (counterexample trace) help the LLM, or is source-code alone sufficient?

**Mechanism:** `vguide.sourcePriorMode=true` fires the LLM once before any CEGAR round, using only the source file as context (no CE trace, no interpolants). Predicates are injected into `PredicateCPA.getInitialPrecision()` so they are active from round 0.

**Config:** base predicate analysis (`predicateAnalysis-vguide`). Comparison baseline: stock (no LLM).

---

## Loops — ReachSafety `unreach-call` (764 tasks, timelimit=300s)

| Mode | Solved | Δ stock | PAR-2 |
|------|-------:|--------:|------:|
| stock (baseline) | 225 | — | 426.21s |
| **source_prior** ← new | 225 | **0** | 427.14s |
| **first_spurious** (v1.4) | **262** | **+37** | **399.72s** |

**Wrong verdicts: 0.**

source_prior = stock (225 = 225). CE trace is what drives the LLM to useful predicates; source code alone provides zero gain.

---

## Overflow — `no_overflow` scalar (452 tasks, timelimit=300s)

| Mode | Solved | Δ stock | PAR-2 |
|------|-------:|--------:|------:|
| stock (baseline) | 357 | — | 127.32s |
| **source_prior** ← new | 331 | **−26** | 165.73s |
| **first_spurious** (v1.6) | **363** | **+6** | **119.76s** |

**Wrong verdicts: 0.**

> Note: stock here is `svcomp26-overflow` (the fair baseline for the overflow property); the base predicate config alone is weaker than the portfolio on overflow regardless of LLM mode.

source_prior is actually worse than stock (331 < 357) — the LLM without CE context injects predicates that slow down the analysis without helping.

---

## Conclusion

| Benchmark | source_prior Δ stock | first_spurious Δ stock |
|-----------|---------------------:|----------------------:|
| Loops | **0** | **+37** |
| Overflow | **−26** | **+6** |

CE context is **necessary**. Without a counterexample trace to anchor the predicates, the LLM output is no better than stock — and can be worse. The improvement from VGuide comes specifically from reasoning about the counterexample, not from general program understanding.

---

## Experiment Artifacts

| Run | Directory |
|-----|-----------|
| base + source_prior loops | `output/vguide/experiments/loops_reachsafety_unreach_source_prior_loops/` |
| base + source_prior overflow | `output/vguide/experiments/no_overflow_scalar_source_prior_overflow/` |

Configs: `config/vguide-experiment-source-prior-{loops,overflow}.properties`
