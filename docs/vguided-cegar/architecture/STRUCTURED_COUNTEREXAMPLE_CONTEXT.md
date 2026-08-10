# Structured counterexample context

`structured-ce-v1` is the deterministic, read-only counterexample artifact sent to the VGuide prompt. It replaces the former free-form CE relation block for new spurious-refinement contexts.

## Schema

```json
{
  "schema_version": "structured-ce-v1",
  "assertion": "...",
  "trace": [{"node": 12, "function": "main", "loop_head": "N12", "repeat_count": 3}],
  "relations": "...",
  "unavailable": ["branch_conditions", "ssa_values", "assignments"]
}
```

`trace` preserves the abstraction trace order and combines only adjacent identical CFA locations. `node` and `function` come from the CPAchecker location state; `loop_head` is present only when the node is a detected loop head. `relations` is the existing formula-derived relation summary. The serializer uses fixed field and list order.

## Evidence boundary

The artifact is prompt context, not a verification witness or truth source. Branch conditions, SSA values, and assignments are explicitly marked unavailable because the current refinement hook does not expose authoritative path-edge/value artifacts. They must not be inferred or synthesized. Future schema versions may add them only from a verified CPAchecker source.

## Limits

The current schema has no raw log input and no cross-round history. Counterexample history, native predicates, refinement outcomes, and predicate lifecycle remain owned by Issues #5–#8.

## Relation to Issue #4

The `loop_head` labels in the structured CE are the same labels the LLM must reuse in
`loop-head-candidate-v1` candidates (`loop_head`/`loop_heads` keys, see
[`LOOP_HEAD_INVARIANT_PLAN.md`](../LOOP_HEAD_INVARIANT_PLAN.md)): a candidate naming a label
that is not in the `LOOP HEADS` list is rejected with `unknown_loop_head`, and a candidate naming
an existing head that is not on the trace is rejected with `head_not_on_trace`.
