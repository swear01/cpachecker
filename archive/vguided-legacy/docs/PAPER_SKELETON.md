# Paper Skeleton: Bootstrap + B5-MR Rescue

## Title Candidates

1. "Rescuing Zero-Context CEGAR Timeouts with LLM-Guided Predicate Precision"
2. "From No Context to Proof: LLM-Guided Bootstrap and Repair for Predicate Abstraction"
3. "Precision Seeding and Trace-Guided Repair for PredicateCPA Timeouts"

## Abstract (draft)

Predicate abstraction with CEGAR is a standard software verification approach, but the verifier can get stuck before producing any refinement context — zero traces, zero interpolants, zero candidate fates. We present a two-stage LLM-guided method to rescue such cases. First, Bootstrap generates initial precision predicates from source code and assertion, which unblocks CEGAR refinement. Second, B5-MR uses the newly available trace/interpolant context to discover proof-relevant relational predicates. All LLM-generated predicates are used only as precision predicates; CPAchecker remains the sound proof engine. On selected zero-context SV-COMP timeout benchmarks, the method achieves local solved-from-UNKNOWN rescue (up 3/3, down 2/3) under the same 300s verifier budget. The approach also extends to array-present benchmarks when the proof bottleneck remains scalar.

## 1. Introduction
- CEGAR-based predicate abstraction can timeout before producing any context.
- Existing LLM trace-guided repair cannot help without traces.
- Bootstrap seeds initial precision from source+assertion.
- B5-MR uses resulting context to discover relational predicates.
- All LLM predicates are precision-only; soundness preserved.

## 2. Background
- Predicate abstraction / PredicateCPA
- CEGAR loop: refinement → interpolants → precision update
- Zero-context timeout: verifier stalls before any refinement

## 3. Method

### 3.1 Bootstrap Initial Precision
- Source + assertion → LLM → scalar BV predicates
- Injected as global precision predicates
- Output validator enforces source-level variable discipline

### 3.2 B5-MR Trace-Guided Repair
- CEGAR context (traces, interpolants, candidate fates) → LLM → relational predicates
- Variable-name table prevents SSA-name contamination
- Multi-round: accumulate predicates across rounds

### 3.3 Applicability Classifier
- Static features → RUN_SCALAR / RUN_ARRAY_SCALAR / skip labels
- Level 1: array-present but scalar bottleneck

## 4. Evaluation

### 4.1 Scalar Rescue
- 5 zero-context timeout cases evaluated
- up: 3/3 rescue, down: 2/3 rescue
- string_concat-noarr: stabilized via fixed-predicate replay

### 4.2 Level 1 Array-Present Scalar
- 6 candidates, 4 rescued, 6/6 context unlocked
- 0 select/store generated

### 4.3 Ablation
- `k=i` alone insufficient, `k=n-j` alone insufficient, combination needed

## 5. Results
- Tables from FINAL_TABLES_FOR_REPORT.md

## 6. Threats to Validity
- Small number of rescues (11 total evaluated)
- LLM output variance (string_concat-noarr 1/3 original)
- Benchmark selection from SV-COMP only
- Parser limited to BV subset
- No array theory / pointer / heap support
- Pool exhausted: 0 new zero-context candidates

## 7. Related Work (placeholders)
- LLM-guided invariant generation
- CPAchecker / PredicateCPA
- CEGAR and interpolation
- Predicate abstraction for software verification
- Machine learning for solver/verifier guidance

## 8. Conclusion
Bootstrap + B5-MR achieves local solved-from-UNKNOWN rescue on selected zero-context CEGAR timeouts. The approach is targeted, not general. Future work includes select/store predicate support and broader benchmark evaluation.
