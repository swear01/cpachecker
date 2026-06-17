# Source-Prior Ablation Report (2026-06-17)

**Question:** Does CE context (counterexample trace) help the LLM, or is source-code alone sufficient?

**Mechanism:** `vguide.sourcePriorMode=true` fires the LLM once before any CEGAR round, using only the source file as context (no CE trace, no interpolants). Predicates are injected into `PredicateCPA.getInitialPrecision()` so they are active from round 0.

**Comparison:** source_prior vs first_spurious (LLM fires on first spurious CE, with CE trace).

---

## Loops — ReachSafety `unreach-call` (764 tasks, timelimit=300s)

| Mode | Config | TRUE | FALSE | UNKNOWN | **Solved** | **PAR-2** |
|------|--------|-----:|------:|--------:|-----------:|----------:|
| stock (baseline) | predicateAnalysis | 165 | 60 | 539 | 225 | 426.21s |
| base + **first_spurious** (v1.4) | predicateAnalysis-vguide | 202 | 60 | 502 | **262** | **399.72s** |
| base + **source_prior** ← **new** | predicateAnalysis-vguide | 165 | 60 | 539 | 225 | 427.14s |
| svcomp26 + **first_spurious** (v1.5.1) | svcomp26-vguide | 341 | 152 | 271 | **493** | **216.90s** |
| svcomp26 + **source_prior** ← **new** | svcomp26-vguide | 333 | 153 | 278 | 486 | 223.79s |

**Wrong verdicts: 0** in all source_prior runs.

### Finding

- **base + source_prior = stock** (225 = 225, PAR-2 427 ≈ 426). CE context is **critical** for the base predicate analysis — without it the LLM predicates provide zero net gain.
- **svcomp26 + source_prior −7 tasks vs first_spurious** (486 vs 493, PAR-2 +6.9s). CE context still helps but the gap is small in the portfolio setting.

---

## Overflow — `no_overflow` scalar (452 tasks, timelimit=300s)

| Mode | Config | TRUE | FALSE | UNKNOWN | **Solved** | **PAR-2** |
|------|--------|-----:|------:|--------:|-----------:|----------:|
| svcomp26 stock (baseline) | svcomp26-overflow | 160 | 197 | 95 | 357 | 127.32s |
| base + **source_prior** ← **new** | predicateAnalysis-overflow-vguide | 139 | 192 | 121 | 331 | 165.73s |
| svcomp26 + **source_prior** ← **new** | svcomp26-overflow-vguide | 164 | 198 | 90 | **362** | **125.03s** |
| svcomp26 + **first_spurious** (v1.6) | svcomp26-overflow-vguide | 166 | 197 | 89 | **363** | **119.76s** |

**Wrong verdicts: 0** in all source_prior runs.

### Finding

- **base + source_prior** (331 solved) is weaker than the svcomp26 portfolio stock (357) — expected, since the base config is predicate-only and overflow is harder.
- **svcomp26 + source_prior ≈ first_spurious** (362 vs 363, PAR-2 +5.3s). CE context adds almost nothing on overflow in the portfolio; source code alone is nearly sufficient.

---

## Ablation Conclusion

| Property | CE context matters? |
|----------|---------------------|
| Loops / base config | **YES — strongly.** source_prior = stock; CE trace drives the LLM to useful predicates. |
| Loops / svcomp26 portfolio | **Slightly.** −7 tasks, +6.9s PAR-2 without CE. |
| Overflow / svcomp26 portfolio | **No.** −1 task, +5.3s PAR-2 without CE. Nearly identical. |

**Interpretation:** The base predicate analysis relies entirely on the CEGAR loop — without a CE trace to anchor the predicates, the LLM guesses don't land on the right abstraction. The svcomp26 portfolio is more resilient because (a) it runs multiple analysis strategies in parallel and (b) the overflow property is more local (bound checks), making source-code-only prediction easier.

**Implication for thesis:** The ablation supports that CE-guided LLM refinement is the correct design for reachability (base config). For overflow in a portfolio setting, source-prior is a viable low-cost alternative (no need to wait for a CE).

---

## Experiment Artifacts

| Run | Directory |
|-----|-----------|
| base + source_prior loops | `output/vguide/experiments/loops_reachsafety_unreach_source_prior_loops/` |
| base + source_prior overflow | `output/vguide/experiments/no_overflow_scalar_source_prior_overflow/` |
| svcomp26 + source_prior loops | `output/vguide/experiments/loops_reachsafety_unreach_source_prior_svcomp26_loops/` |
| svcomp26 + source_prior overflow | `output/vguide/experiments/no_overflow_scalar_source_prior_svcomp26_overflow/` |

Configs: `config/vguide-experiment-source-prior-{loops,overflow,svcomp26-loops,svcomp26-overflow}.properties`
