# Pipeline Diagram (ASCII)

```
                        ┌────────────────────┐
                        │ no-LLM PredicateCPA │
                        │    @300s budget     │
                        └──────────┬─────────┘
                                   │
                                   ▼
                        ┌────────────────────┐
                        │ ZERO_CONTEXT_TIMEOUT│
                        │  0 refinements      │
                        │  0 context dumps    │
                        └──────────┬─────────┘
                                   │
                                   ▼
                        ┌────────────────────┐
                        │ Bootstrap Initial   │
                        │ Precision Seeding   │
                        │                     │
                        │ source + assertion  │
                        │  → LLM prompt      │
                        │  → scalar BV preds  │
                        │  → validator gates  │
                        │  → inject precision │
                        └──────────┬─────────┘
                                   │
                                   ▼
                        ┌────────────────────┐
                        │ Context Unlocked    │
                        │  refinements > 0    │
                        │  spurious traces    │
                        │  interpolants       │
                        │  candidate fates    │
                        └──────────┬─────────┘
                                   │
                                   ▼
                        ┌────────────────────┐
                        │ Fixed B5-MR Repair  │
                        │                     │
                        │ trace/interpolant   │
                        │  → LLM prompt      │
                        │  → variable table   │
                        │  → relational preds │
                        │  → validator gates  │
                        │  → inject precision │
                        └──────────┬─────────┘
                                   │
                                   ▼
                        ┌────────────────────┐
                        │   CPAchecker TRUE  │
                        │ (sound proof by    │
                        │  formal engine)    │
                        └────────────────────┘

All LLM predicates enter precision only.
CPAchecker remains the sound proof engine.
Output validator enforces source-level variable discipline.
Variable-name table prevents SSA-name contamination.
```

# Claim Hierarchy

```
Level 0: No effect / too easy
  → no improvement possible

Level 1: Refinement acceleration
  → B2 solves but B5-MR reduces refinements (e.g., sum01-2 53→2)

Level 2: Context unlock
  → zero-context timeout becomes refinement-active (bootstrap)

Level 3: Solved-from-UNKNOWN rescue
  → no-LLM UNKNOWN, Bootstrap+B5-MR TRUE (up, down)

Level 4: Array-present scalar extension
  → Level 1 classifier: array there but bottleneck is scalar

Future: Simple select/store predicates (Level 2 array)
Out of scope: Pointer/heap, aliasing, quantified invariants
```

# Classifier Flow

```
Benchmark
    │
    ▼
┌──────────────────┐
│  Preflight check  │── preprocess fail ──→ SKIP
│  Static features  │── parser limited  ──→ SKIP
└────────┬─────────┘── pointer/heap     ──→ SKIP
         │              float/concurrent ──→ SKIP
         ▼
    ┌─────────┐
    │ Scalar? │── YES, loop+assertion ──→ RUN_SCALAR
    └────┬────┘
         │ NO (array present)
         ▼
    ┌──────────────┐
    │ Assertion    │── scalar assertion ──→ RUN_ARRAY_SCALAR (Level 1)
    │ mentions     │── array assertion  ──→ RUN_ARRAY_SELECT_EXPERIMENTAL
    │ array?       │── uncertain        ──→ PARSER_RISK
    └──────────────┘
```
