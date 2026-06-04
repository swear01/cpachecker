# Report Outline: Bootstrap + B5-MR for CEGAR Rescue

## 1. Motivation
- CEGAR-based software verification can get stuck before producing any refinement context.
- Zero-context timeout: verifier times out with 0 refinements, 0 traces, 0 interpolants.
- Trace-guided LLM repair cannot help without traces to analyze.
- Question: can LLM-generated predicates rescue such cases?

## 2. Background: Predicate Abstraction + CEGAR
- CPAchecker PredicateCPA: predicate abstraction with counterexample-guided refinement.
- B5 = trace/interpolant-guided LLM repair: LLM sees spurious traces and generates abstraction predicates.
- B5-MR = multi-round B5 repair.
- Previous results: acceleration on HARD_SOLVED cases (sum01-2 53→2, etc.).

## 3. Initial B5-MR Limitation
- B5-MR requires CEGAR context (traces, interpolants).
- Official SV-COMP CPAchecker-unsolved timeout cases were 100% zero-context.
- B5-MR cannot start on zero-context timeouts.

## 4. Initial Precision Bootstrap
- Bootstrap: LLM generates initial precision predicates from source + assertion.
- Predicates enter precision only — not trusted as invariants.
- Soundness: CPAchecker remains the proof engine.
- Implementation: bootstrap prompt builder, candidate generator, validator, existing injection path.

## 5. B5-MR Repair with Variable-Name Table
- B5-MR repair needs CEGAR context produced after bootstrap.
- Critical fix: variable-name table in B5 prompt prevents SSA-name contamination.
- Previous failure: LLM copied `|main::i|` from interpolants. Fix: explicit mapping table.

## 6. Evaluation Setup
- Budget: 300s verifier, low reasoning effort.
- Mode comparison: no-LLM @300s, bootstrap-only @300s, bootstrap+B5-MR @300s.
- Initial candidates: 5 ZERO_CONTEXT_TIMEOUT tasks from SV-COMP loop-invgen.
- Reproduction: K=3 repeated runs.

## 7. Results

| Case | no-LLM | Bootstrap | B5-MR | Repro | Status |
|------|--------|-----------|-------|:---:|--------|
| up | ZERO_CONTEXT | unlocked | TRUE | 3/3 | stable_confirmed_rescue |
| down | ZERO_CONTEXT | unlocked | TRUE | 2/3 | confirmed_rescue |
| string_concat-noarr | ZERO_CONTEXT | unlocked | TRUE | 3/3* | stabilized_via_fixed_predicates |
| half_2 | ZERO_CONTEXT | unlocked | UNKNOWN | — | context_unlocked_only |
| seq-3 | ZERO_CONTEXT | unlocked | UNKNOWN | — | context_unlocked_only |

*stabilized via fixed-predicate replay; original reproduction 1/3 due to LLM variance.

## 8. Case Studies
- up: counter/accumulator. Key predicates: `k=i`, `k=n-j`. Both needed.
- down: counter/accumulator. Similar two-loop pattern.
- string_concat-noarr: string/counter. Fixed-predicate replay confirms instability was LLM-side.

## 9. Ablation
- up: `k=i` alone insufficient. `k=n-j` alone insufficient. Combination needed and sufficient.
- Proof requires multiple relational predicates; neither bootstrap nor individual predicates alone suffice.

## 10. Soundness
- All LLM predicates are precision predicates only.
- CPAchecker proves TRUE/FALSE.
- Output validator enforces source-level variable discipline.
- Internal SSA-name contamination is caught and rejected.

## 11. Limitations
- 2 directly reproduced rescues; 1 stabilized via fixed replay.
- All successful cases share counter/accumulator relational pattern.
- Current benchmark pool exhausted — 0 new ZERO_CONTEXT_TIMEOUT candidates.
- Bootstrap doesn't always lead to solved (2/5 solved after B5-MR).
- string_concat-noarr needed fixed-predicate replay.
- Not a general solver improvement.

## 12. Future Work
- Extend to harder external SV-COMP benchmark suites.
- Improve B5 repair predicate quality (reduce LLM variance).
- Investigate local precision injection (per-CFANode).
- Extend parser for bvshl (halving patterns) and array select/store.
- Multi-round B5-MR with accumulated context for context_unlocked cases.
