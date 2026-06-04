# Oral Summary: Bootstrap + B5-MR Rescue

**Duration**: 2-3 minutes

---

CPAchecker's PredicateCPA performs CEGAR-based software verification. Sometimes the verifier gets stuck before producing any CEGAR context — zero refinements, zero traces, zero interpolants. We call this zero-context timeout.

B5-MR, our trace/interpolant-guided LLM repair method, cannot help because there's no trace to repair from.

So we introduced "bootstrap" — LLM-generated initial precision predicates from source code and assertion alone. These are injected only as precision predicates, so CPAchecker remains the sound proof engine.

Bootstrap consistently unlocked CEGAR context — 5 out of 5 zero-context timeout cases became refinement-active. Then B5-MR used the newly available traces and interpolants to discover proof-relevant relational predicates.

The result: two confirmed rescues across repeated runs. `up` solved 3/3 times, `down` 2/3 times. A third case, `string_concat-noarr`, needed fixed-predicate replay but proves 3/3 with the right predicates.

Ablation on `up` showed that neither `k=i` nor `k=n-j` alone suffices — the proof requires both relational predicates together.

Two other cases unlocked context but didn't solve yet, suggesting more work is needed.

The key contribution: LLM-generated predicates can rescue CPAchecker from zero-context timeouts. The claim is targeted — it works on counter/accumulator relational patterns — not general acceleration. And the benchmark pool is exhausted, so broader validation needs harder external benchmarks.
