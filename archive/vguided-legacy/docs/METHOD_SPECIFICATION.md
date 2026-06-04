# Method Specification

## Algorithm 1: Bootstrap Precision Seeding

**Purpose**: Seed initial PredicateCPA precision for zero-context timeout benchmarks.

**Input**:
- Source program (C/.i file)
- Assertion expression (extracted from `__VERIFIER_assert`)
- Variable-name table (source-level → SSA mapping)
- Predicate grammar (BV-only SMT-LIB2 subset)

**Steps**:

1. Read source code, extract assertion expression.
2. Identify source-level variable names from C declarations.
3. Build bootstrap prompt: source code + assertion + instruction ("generate 5-10 initial abstraction predicates").
4. Call LLM (DeepSeek chat, temperature=0, low reasoning effort).
5. Parse JSON response: `{"N<node>": ["pred1", ...]}`.
6. Validate predicates via output contract validator:
   - Reject if contains `|main::...|` (SSA pipe names)
   - Reject if contains `.def_*` (internal solver terms)
   - Reject if contains `select`, `store` (array theory)
   - Reject if contains `bvshl`, `bvlshr` (unsupported shifts)
7. Convert validated predicates to PredicateCPA AbstractionPredicate objects.
8. Inject as global PredicatePrecision predicates.
9. Run PredicateCPA with per-round timelimit.

**Output**: (result, refinements, context dumps)

**Soundness**: Predicates enter precision only. Not trusted as invariants.

## Algorithm 2: B5-MR Multi-Round Repair

**Purpose**: Discover proof-relevant relational predicates from CEGAR context.

**Input**:
- CEGAR context dumps (spurious traces, interpolants, block formulas, precision, candidate fates)
- Source code
- Current precision predicates
- Variable-name table
- Max rounds R (default 5)
- Per-round timelimit (default 60s)

**Steps**:

For round r = 1..R:
1. Run PredicateCPA with current accumulated precision predicates.
2. If TRUE/FALSE reached, stop.
3. Dump CEGAR context (ARGPath, interpolants, precision, candidate fates).
4. Summarize context to compact Markdown.
5. Build B5 repair prompt: FULL context + Variable Name Contract (source-level names only, mapping from SSA names).
6. Call LLM.
7. Validate repair predicates via output contract validator.
8. Deduplicate against previously injected predicates.
9. If no new valid predicates, stop (stagnation).
10. Inject new predicates into precision.
11. If cumulative predicate count exceeds cap (30), stop.

**Output**: (result, refinements, rounds used, total predicates)

## Algorithm 3: Applicability Classifier

**Purpose**: Select benchmarks likely to benefit from Bootstrap+B5-MR.

**Input**: Source program (C/.i file)

**Features Extracted**:
- `has_array`, `has_pointer`, `has_malloc`, `has_struct`, `has_float`
- `num_loops`, `has_counter`, `has_accumulator`
- `assertion_vars`, `assertion_mentions_array`, `assertion_mentions_loop_vars`
- `likely_cross_loop_relation`

**Labels**:
- `RUN_SCALAR`: scalar loops, counter/accumulator, assertion-loop relation
- `RUN_ARRAY_SCALAR`: array present, scalar assertion, scalar bottleneck likely
- `RUN_ARRAY_SELECT_EXPERIMENTAL`: array in assertion, may need select
- `SKIP_POINTER_HEAP`: malloc, struct, pointer syntax
- `SKIP_UNSUPPORTED_THEORY`: float, pthread, concurrency
- `PARSER_RISK`: bitshift, uncertain pointer
- `UNKNOWN`: fallback

**Usage**: Filter candidate pool before running. Prevents wasted LLM calls and formal runs on inapplicable benchmarks.
