# Source-Prior Ablation Report (2026-06-17)

**Question:** Does CE context (counterexample trace) help the LLM, or is source-code alone sufficient?

**Mechanism:** `vguide.sourcePriorMode=true` fires the LLM once before any CEGAR round, using only the source file as context (no CE trace, no interpolants). Predicates are injected into `PredicateCPA.getInitialPrecision()` so they are active from round 0.

**Comparison baseline:** stock (no LLM). Delta vs stock is the primary metric.

---

## Loops — ReachSafety `unreach-call` (764 tasks, timelimit=300s)

| Mode | Config | Solved | Δ stock | PAR-2 |
|------|--------|-------:|--------:|------:|
| predicateAnalysis stock | predicateAnalysis | 225 | — | 426.21s |
| base + **first_spurious** (v1.4) | predicateAnalysis-vguide | **262** | **+37** | 399.72s |
| base + **source_prior** ← new | predicateAnalysis-vguide | 225 | **0** | 427.14s |
| svcomp26 stock | svcomp26 | 486 | — | — |
| svcomp26 + **first_spurious** (v1.5.1) | svcomp26-vguide | **493** | **+7** | 216.90s |
| svcomp26 + **source_prior** ← new | svcomp26-vguide | 486 | **0** | 223.79s |

**Wrong verdicts: 0.**

### Finding

- **base + source_prior = stock** (225 = 225): source code alone gives **zero gain**. CE trace is what drives the LLM to useful predicates.
- **svcomp26 + source_prior = svcomp26 stock** (486 = 486): again **zero gain**. The portfolio improvement from VGuide (+7) disappears entirely when the CE context is removed.

---

## Overflow — `no_overflow` scalar (452 tasks, timelimit=300s)

| Mode | Config | Solved | Δ svcomp26 stock | PAR-2 |
|------|--------|-------:|-----------------:|------:|
| svcomp26 stock | svcomp26-overflow | 357 | — | 127.32s |
| base + **source_prior** ← new | predicateAnalysis-overflow-vguide | 331 | −26 | 165.73s |
| svcomp26 + **source_prior** ← new | svcomp26-overflow-vguide | 362 | **+5** | 125.03s |
| svcomp26 + **first_spurious** (v1.6) | svcomp26-overflow-vguide | **363** | **+6** | 119.76s |

**Wrong verdicts: 0.**

### Finding

- **base + source_prior** (331) is weaker than portfolio stock (357): the base predicate config alone is insufficient for overflow regardless of LLM mode.
- **svcomp26 + source_prior ≈ svcomp26 + first_spurious** (+5 vs +6 over stock, PAR-2 gap 5.3s). For overflow, the property is local enough (bound checks) that source code alone is nearly as good as CE-guided refinement.

---

## Ablation Conclusion

| Benchmark | Config | source_prior Δ stock | first_spurious Δ stock | CE context matters? |
|-----------|--------|---------------------:|----------------------:|---------------------|
| Loops | base | **0** | +37 | **Yes — critical** |
| Loops | svcomp26 | **0** | +7 | **Yes** |
| Overflow | svcomp26 | +5 | +6 | Marginal |

**Interpretation:** For reachability (loops), CE context is necessary — without a CE trace to anchor the predicates, the LLM guesses are no better than running without VGuide at all. For overflow, the property structure is simpler and more local, so source-code-only prediction nearly matches CE-guided refinement (+5 vs +6).

**Implication for thesis:** The ablation confirms that CE-guided refinement (`first_spurious`) is the correct design for the reachability property. The source-prior mode is effectively a control condition showing that the LLM's contribution comes specifically from reasoning about the counterexample, not from general program understanding.

---

## Experiment Artifacts

| Run | Directory |
|-----|-----------|
| base + source_prior loops | `output/vguide/experiments/loops_reachsafety_unreach_source_prior_loops/` |
| base + source_prior overflow | `output/vguide/experiments/no_overflow_scalar_source_prior_overflow/` |
| svcomp26 + source_prior loops | `output/vguide/experiments/loops_reachsafety_unreach_source_prior_svcomp26_loops/` |
| svcomp26 + source_prior overflow | `output/vguide/experiments/no_overflow_scalar_source_prior_svcomp26_overflow/` |

Configs: `config/vguide-experiment-source-prior-{loops,overflow,svcomp26-loops,svcomp26-overflow}.properties`
