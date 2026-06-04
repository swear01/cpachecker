# Failure Analysis: `half_2` (context_unlocked_only)

## Benchmark Summary
- **Task**: `half_2` (loop-invgen)
- **Source**: SV-COMP 2026 ReachSafety-Loops
- **Property**: Scalar loop with counter halving pattern
- **No-LLM @300s**: ZERO_CONTEXT_TIMEOUT

## Bootstrap Effect
Bootstrap produced 7 predicates and unlocked CEGAR context (67 refinements, 3 context dumps). The context unlock rate is 100% — bootstrap consistently works.

## B5-MR Result
After B5-MR repair: UNKNOWN, 61 refinements (modest improvement from 67). Not solved.

## Why It Did Not Solve
The B5 repair produced predicates but they were insufficient to complete the proof. The benchmark likely requires a more complex relational predicate than the B5 repair round discovered.

## Suspected Missing Relation
The "half_2" pattern involves a counter being halved each iteration. The missing predicate is likely a recursive or exponential relation (`k * 2^n = initial_value`) which is not easily expressible in the BV-only SMT subset supported by the parser.

## Next Possible Experiment
- Run B5-MR with more rounds (7-10) to give LLM more attempts.
- Extend parser to support bitvector shifts (`bvlshr`) which could express halving patterns.
- Investigate whether source-only bootstrap can be improved for halving patterns.

## Classification
`context_unlocked_only` — not rescue. Bootstrap works but B5-MR repair is insufficient.

# Failure Analysis: `seq-3` (context_unlocked_only)

## Benchmark Summary
- **Task**: `seq-3` (loop-invgen)
- **Source**: SV-COMP 2026 ReachSafety-Loops
- **Property**: Sequential loop with counter/accumulator
- **No-LLM @300s**: ZERO_CONTEXT_TIMEOUT

## Bootstrap Effect
Bootstrap produced 9 predicates, unlocked CEGAR context (43 refinements, 3 dumps). Bootstrap works.

## B5-MR Result
B5-MR produced 7 repair predicates. After combined injection: UNKNOWN, 37 refinements. Not solved.

## Why It Did Not Solve
The B5 repair predicates provided refinement reduction (43→37) but were insufficient for the proof. The sequential loop structure may require more complex invariants spanning multiple loop phases.

## Suspected Missing Relation
Sequential multi-phase loop relations that span across loop boundaries.

## Next Possible Experiment
- Run B5-MR with more rounds.
- Investigate per-CFANode local precision injection.
- Test whether multiple sequential B5 repair rounds (not just one) can accumulate needed predicates.

## Classification
`context_unlocked_only` — not rescue. Bootstrap works. B5-MR improves refinements but doesn't solve.
