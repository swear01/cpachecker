# Five-Minute Presentation Script

## 0:00–0:45 — Problem

CPAchecker's PredicateCPA performs CEGAR-based software verification using predicate abstraction. Sometimes the verifier gets stuck before producing any CEGAR context at all — zero refinements, zero spurious traces, zero interpolants. We call this zero-context timeout. Our existing trace-guided LLM repair method, B5-MR, cannot operate because there are no traces to repair from.

## 0:45–1:30 — Method Intuition

So we introduced "Bootstrap" — initial precision seeding. We feed the source code and assertion to an LLM and ask it to generate initial abstraction predicates. These are injected into PredicateCPA's precision only — they are Boolean features that the verifier tracks, NOT invariants that it trusts. CPAchecker remains the sound proof engine. The bootstrap predicates unblock CEGAR — suddenly the verifier can complete refinements and produce traces and interpolants.

Once context exists, B5-MR uses the trace/interpolant feedback to discover proof-relevant relational predicates. A variable-name table in the prompt prevents the LLM from copying internal SSA-encoded variable names into its output.

## 1:30–2:30 — Main Results

On selected zero-context timeout benchmarks from SV-COMP, we achieved local solved-from-UNKNOWN rescue. The benchmark "up" solved three out of three times under repeated runs. "down" solved two out of three. A third case, "string-concat-noarr", was inconsistent until we replayed the successful predicate set — then it solved three out of three. The instability was LLM-side output variance, not a proof problem.

This is stronger than acceleration — the no-LLM baseline couldn't solve these cases at all, and our pipeline solved them under the same 300-second verifier budget.

## 2:30–3:15 — Level 1 Extension

A natural question was: does this only work on purely scalar benchmarks? We added a classifier label for array-present but scalar-bottleneck programs — benchmarks where arrays appear syntactically but the proof depends only on loop indices and counters. On six such candidates, bootstrap rescued four and unlocked context in all six, without ever generating select or store predicates. I can demonstrate this live.

## 3:15–4:00 — Soundness and Ablation

Every LLM-generated predicate enters precision only — it's tracked as an abstraction feature, never trusted as an invariant. CPAchecker proves the final result. An output validator rejects internal SSA symbols and unsupported operators. Ablation on "up" showed that individual predicates are not sufficient — you need the combination of both "k equals i" and "k equals n minus j" for the proof.

## 4:00–5:00 — Limitations and Ask

The claim is targeted: 11 benchmarks evaluated, 2-3 directly reproducible scalar rescues, 4 Level 1 bootstrap rescues. No full array theory support, no pointer or heap. The accessible benchmark pool is exhausted.

My question for you: is this already a strong enough targeted research story, or should I next focus on broader benchmark coverage, Level 2 select predicate support, or writing a formal report draft?
