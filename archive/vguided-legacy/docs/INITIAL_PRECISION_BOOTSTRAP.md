# Initial Precision Bootstrap — Direction B

## 1. Motivation

20/20 official CPAchecker TIMEOUT tasks are ZERO_CONTEXT_TIMEOUT: CPAchecker cannot complete even one CEGAR refinement within 300s. Without refinement context, B5-MR trace/interpolant-guided repair has no input.

To help these cases, the LLM must seed initial predicates BEFORE CEGAR gets stuck. If initial predicates enable the first refinement, B5-MR can then take over.

## 2. Method: B0-Init

B0-Init = LLM-generated initial precision seeding before CEGAR refinement.

### Pipeline

1. Read source code and assertion expression.
2. Extract loop variables, counters, accumulator patterns.
3. Ask LLM: "Generate abstraction predicates that would help CEGAR get started on this benchmark."
4. Validate predicates via output contract validator.
5. Inject top-K predicates into initial PredicateCPA precision.
6. Run CPAchecker.
7. If context appears → switch to B5-MR.

### Soundness

Predicates are not trusted as invariants. They only enter precision. Formal proof remains CPAchecker's responsibility. The LLM provides candidate features, not claims.

### Output Contract

Same as B5:
- Source-level variable names only
- No `|main::x@k|`, no `.def_*`
- Supported BV operators only
- Validator enforced

## 3. Prompt Design

```
You are helping a CEGAR-based verifier analyze a loop benchmark.

SOURCE CODE:
<source>

ASSERTION: __VERIFIER_assert(<expr>)

This benchmark is a ZERO_CONTEXT_TIMEOUT: CEGAR cannot complete even
one refinement because the initial abstraction is too weak.

Generate 5-10 initial abstraction predicates that would help CEGAR
get started. Focus on:
- Loop counters and their bounds
- Accumulator variables and their relations
- Branch conditions
- Variables appearing in the assertion

Output JSON: {"N<node>": ["(pred1)", "(pred2)", ...]}
Use SMT-LIB2 BV syntax. Use source-level variable names only.
```

## 4. Evaluation Plan

### Phase 1: Smoke test on 1-3 zero-context tasks

- Run B0-Init with top-5 predicates.
- Check if CPAchecker produces ANY refinement context.
- If not: increase to top-10, retry.
- Record: whether context appears, whether result solves.

### Phase 2: If context appears on any task

- Combine B0-Init + B5-MR on that task.
- B0-Init seeds initial predicates → CPAchecker runs → context appears → B5-MR repairs.

### Success Criteria

| category | definition |
|----------|-----------|
| bootstrap_rescue | no-LLM ZERO_CONTEXT_TIMEOUT, B0-Init+B5-MR TRUE under 300s |
| context_unlocked | ZERO_CONTEXT_TIMEOUT, bootstrap produces context but not solved |
| no_effect | no change |
| parser_limited | unsupported operations |

## 5. Risks

- Source-only guesses may be too weak to unblock CEGAR.
- Too many predicates may slow PredicateCPA.
- May duplicate B2 limitations (source-only = same weakness).
- No CEGAR feedback before bootstrap.
- Current local benchmark pool includes no B2_TIMEOUT cases — these are all from SV-COMP and may have parser issues.

## 6. Implementation

Script: `scripts/vguided-cegar/b5_initial_precision_bootstrap.sh`

### Usage

```bash
bash scripts/vguided-cegar/b5_initial_precision_bootstrap.sh \
  <benchmark.c> <output_dir> \
  --top-k 5 --timelimit 300
```

### Steps

1. Read source, extract assertion.
2. Build bootstrap prompt.
3. Call LLM.
4. Validate candidates.
5. Build injection JSON from validated predicates.
6. Run CPAchecker with VGUIDE_INJECT_REPAIR_PREDICATES_ONCE + VGUIDE_B5_DUMP_CONTEXT.
7. Record result, refs, time, and whether context appeared.

## 7. Status

Not yet implemented. Design only.
