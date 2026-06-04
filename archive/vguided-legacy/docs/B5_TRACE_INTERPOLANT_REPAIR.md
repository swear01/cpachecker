# B5: Interpolant- and Trace-Guided LLM Predicate Repair

## 1. Motivation: Why B2/V3/V4 Are Insufficient

| Mode | Strategy | Result |
|------|----------|--------|
| B2 | Source-only LLM predicate injection | Effective only on diamond_1-1; not general |
| V3 | Diversified prompt (buckets, accumulator emphasis) | No improvement over B2 |
| V4 | Local SAT-based usefulness scoring | Regression on sum04-2 (2→6), const_1-2 (38→46) |

**Root cause**: B2/V3/V4 all inject predicates based on source code understanding alone.
They receive **no feedback** from CPAchecker about:
- Which counterexample traces appeared (and why they were spurious)
- Which abstraction states were too weak
- What interpolants CPAchecker derived
- Which LLM predicates were used, which were ignored, and which were rejected

The LLM operates blind.

## 2. Why Local blockFormula-Based Scoring Fails

V4's `PredicateScorer` uses `blockFormula` (single-program-point formula) to SAT-test candidates:

```java
// blockFormula ∧ ¬p  UNSAT  →  entailed (low score, B1 path)
// blockFormula ∧ p    SAT    AND  blockFormula ∧ ¬p  SAT  →  non-constant (high score)
```

**Problem**: useful abstraction predicates are often not true at the first loop-head visit.
Example: `(= s (* i v))` at the first visit where `s=0, i=0, v=nondet`.
- `s=0 ∧ s≠0` is UNSAT, so blockFormula ∧ ¬p is SAT → non-constant. OK.
- But the blockFormula captures only one program point, not the **inductive structure**
  that makes the predicate useful.

What makes a predicate useful:
- It can be **proved inductively** across the loop
- It **entails the assertion** at the loop exit
- It **distinguishes states** that the current abstraction conflates

Single-point SAT testing captures none of these properties.

## 3. Rich CEGAR Context for B5

B5 dumps the full CEGAR failure context. The LLM sees:

### 3.1 Spurious Counterexample Trace (ARGPath)

Access: `PredicateCPARefiner.performRefinementForPath(ARGReachedSet, ARGPath)` parameter `allStatesTrace`.

From `ARGPath`:
- `asStatesList()` → `ImmutableList<ARGState>` trace states
- `getInnerEdges()` → `List<@Nullable CFAEdge>` (one per transition)
- `PathIterator` for structured traversal with state/edge access

### 3.2 CFA Locations and Edge Information

From `ARGPath.PathIterator`:
- `getLocation()` → `CFANode` at each state
- `getOutgoingEdge()` → `CFAEdge` to next state (nullable)

From `CFAEdge` subtypes:
- `CAssumeEdge`: branch condition via `getExpression()` + `getTruthAssumption()`
- `CStatementEdge`: assignment statement via `getStatement()`
- `getFileLocation()`, `getLineNumber()` for source-level annotation

Branch condition SSA encoding (using `PathFormulaManager.makeAnd()`):
```java
PathFormula edgePF = pfmgr.makeAnd(
    pfmgr.makeEmptyPathFormulaWithContextFrom(pathFormula),
    cfaEdge);
BooleanFormula edgeSSAFormula = edgePF.getFormula();
```

### 3.3 Block Formulas (Path Formulas Between Abstractions)

From `BlockFormulas.getFormulas()`:
- `ImmutableList<BooleanFormula>` — SSA-encoded formula for each block
- Each formula encodes the conjunct of edge constraints between consecutive abstractions
- Variable names extracted via `fmgr.extractVariableNames(formula)` — gives SSA-encoded names like `|main::x@2|`

### 3.4 Interpolants per Abstraction State

From `CounterexampleTraceInfo.getInterpolants()`:
- `ImmutableList<BooleanFormula>` — N-1 interpolants for N path formulas
- Interpolant[i] is an over-approximation of states reachable at position i

Interpolant content tells exactly what CPAchecker's interpolation engine thinks is needed.
The LLM can see which predicates the engine is missing.

### 3.5 Abstraction State Formulas

From `PredicateAbstractState.getAbstractionFormula()`:
- `asFormula()` → `BooleanFormula` — abstraction formula WITHOUT SSA indices (clean)
- `asInstantiatedFormula()` → `BooleanFormula` — WITH SSA indices
- `getBlockFormula().getFormula()` → the block formula at this state

### 3.6 Current Precision

From `PredicatePrecision` (extracted via `Precisions.extractPrecisionByType()`):
- `getGlobalPredicates()` → `ImmutableSet<AbstractionPredicate>` — all global precision predicates
- `getLocalPredicates()` → `ImmutableSetMultimap<CFANode, AbstractionPredicate>` — per-node predicates
- Each `AbstractionPredicate.getSymbolicAtom()` → `BooleanFormula` — the actual predicate formula

This shows what the abstraction is CURRENTLY tracking.

### 3.7 LLM Candidate Fates

From V-guided injection statistics (already logged):
- V-FATE log: ENTAILED / ABSTRACTION-CANDIDATE / PARSE-ERROR per predicate per location
- V2/V3 scores per candidate
- V4 rejection reasons (from `PredicateScorer`)
- Number of injection successes, fallbacks, SMT validations

### 3.8 Injected vs. Not-Injected Predicates

- Which candidates were injected into precision (via `injectRankedTopK/V4`)
- Which were not (scored too low, rejected by SAT, or out of top-k)

## 4. B5 Offline Workflow

```
┌─────────────────────────────────────────────────────────────┐
│ PHASE 1: Run with dump                                       │
│                                                              │
│  cpa.sh --option cpa.predicate.refinement.useVocabularyGuide=true \
│    --option cpa.predicate.refinement.dumpB5Context=true       \
│    --timelimit 30s benchmark.c                                │
│                                                              │
│  Produces: results/b5_context/benchmark_b5_context.json       │
│                                                              │
├─────────────────────────────────────────────────────────────┤
│ PHASE 2: LLM repair                                          │
│                                                              │
│  python3 scripts/vguided-cegar/b5_offline_repair.py           \
│    --context results/b5_context/benchmark_b5_context.json     \
│    --output results/b5_context/benchmark_repair_candidates.json│
│                                                              │
│  LLM prompt includes:                                        │
│    - Source code                                             │
│    - Spurious trace + CFA locations + branch conditions      │
│    - Interpolants per abstraction state                      │
│    - Current precision predicates                            │
│    - LLM candidate fates (what was injected, what was not)   │
│  LLM output: structured predicate list (location-keyed)      │
│                                                              │
├─────────────────────────────────────────────────────────────┤
│ PHASE 3: Parse, dedup, rank, inject, rerun                   │
│                                                              │
│  cpa.sh --option cpa.predicate.refinement.useVocabularyGuide=true \
│    --option cpa.predicate.refinement.injectB5RepairOnce=true \ │
│    benchmark.c                                                │
│                                                              │
│  Java reads repair file, parses predicates, injects once     │
│  Report: result, refinement count, runtime                   │
└─────────────────────────────────────────────────────────────┘
```

### Phase 1: Dump

Java side: `dumpB5Context()` in `PredicateCPARefiner`.

Trigger: env var `VGUIDE_B5_DUMP_CONTEXT=1` (or config option `dumpB5Context=true`).

Run B2 until N refinements or near timeout, then dump:

1. Source code text
2. Per-refinement (up to 5 recent failures):
   - Spurious counterexample trace (CFANode numbers + line numbers + descriptions)
   - CFA edges: assume conditions (with truth assumptions), statement edges
   - Block formulas (SSA-SMT dump)
   - Interpolants (SMT dump)
   - Abstraction state formulas at each point
3. Current precision (global + local predicates, SMT dump)
4. LLM candidate fates (ENTAILED/ABSTRACTION-CANDIDATE/PARSE-ERROR, scores, injected/not)
5. Assertion expression (extracted from source)
6. Summary statistics (refinements so far, timeout remaining)

### Phase 2: LLM Repair

Python script reads context JSON, formats LLM prompt, calls DeepSeek API.

Prompt structure:
```
You are analyzing a CEGAR-based software verifier that is stuck on a benchmark.

SOURCE CODE: <source>
ASSERTION: <assertion expression>

CONTEXT FROM CEGAR FAILURES (up to 5):

--- REFINEMENT 1 ---
SPURIOUS TRACE:
  N12 (line 5): x=0, y=nondet  |  assume(y != 0) → N15
  N15 (line 6): x=0, y=nondet  |  loop head
  ...
BLOCK FORMULAS:
  [0] (define-fun |main::x@2| () (_ BitVec 32)) ...
INTERPOLANTS:
  [0] (let ...)  ; over-approximation at N15
  [1] (let ...)  ; over-approximation at loop exit
...

CURRENT PRECISION:
  Global: [(not (= (bvurem |main::a@1| #x00000002) #x00000000))]
  Local: N12: [] N15: [(= (bvurem |main::x@3| #x00000002) ...)]

LLM CANDIDATE FATES:
  ENTAILED: N15 "a >= 0" (injected into interpolant B1)
  ABSTRACTION-CANDIDATE: N15 "a % 2 == 0" (V4 REJECT: contradictory)
  INJECTED: N15 "(= (bvurem x@3 2) (bvurem y@3 2))" (V4 score=12, injected)

TASK:
Generate missing predicates that would help CPAchecker prove the assertion.
Focus on predicates not already in the current precision.
Output JSON: {"N<node>": ["(pred1)", "(pred2)", ...]}
```

### Phase 3: Inject and Rerun

Java side: `injectB5RepairOnce()` reads `VGUIDE_B5_REPAIR_CANDIDATES_FILE`, parses predicates, injects into global precision one-shot.

Reuses existing `LLMConnector.parseLocationPredicates()` for parsing the JSON output.
Reuses existing `VocabularyGuide.parsePredicate()` for SMT parsing.

## 5. Key Code Access Points

### In `PredicateCPARefiner` (existing):

| Data | Access Path | Type |
|------|-------------|------|
| Full ARG path | `allStatesTrace` (method parameter) | `ARGPath` |
| CFA path iterator | `allStatesTrace.pathIterator()` | `PathIterator` |
| Abstraction states | filter Ab. states from `allStatesTrace` | `List<ARGState>` |
| Block formulas | `createFormulasOnPath(allStatesTrace, absStates)` | `BlockFormulas` |
| Block SMT list | `blockFormulas.getFormulas()` | `ImmutableList<BooleanFormula>` |
| Interpolants | `counterexample.getInterpolants()` | `ImmutableList<BooleanFormula>` |
| Ab. formula (no SSA) | `pas.getAbstractionFormula().asFormula()` | `BooleanFormula` |
| Ab. formula (SSA) | `pas.getAbstractionFormula().asInstantiatedFormula()` | `BooleanFormula` |
| Current precision | `Precisions.extractPrecisionByType(prec, Pred...Class)` | `PredicatePrecision` |
| Global predicates | `predPrec.getGlobalPredicates()` | `ImmutableSet<AbstractionPredicate>` |
| Predicate atom | `ap.getSymbolicAtom()` | `BooleanFormula` |
| SMT dump | `fmgr.dumpFormula(bf).toString()` | `String` |
| LLM fate log | `V-FATE` logger entries | `Level.INFO` log |
| Edge branch cond | `(CAssumeEdge) edge.getExpression()` | `CExpression` |
| Edge SSA encoding | `pfmgr.makeAnd(emptyCtx, edge).getFormula()` | `BooleanFormula` |
| Candidate fates | `pendingAbstractionCandidates` + `v4BlockContext` | per-node data |

### New to implement (B5-specific):

| Component | File | Role |
|-----------|------|------|
| `dumpB5Context()` | `PredicateCPARefiner.java` | Collects and dumps CEGAR context to JSON |
| `injectB5RepairOnce()` | `PredicateCPARefiner.java` | Reads repair JSON, injects predicates |
| `B5ContextDumper.java` (new) | `cpa/predicate/` | Formats spurious trace, interpolants, precision as structured JSON |
| `b5_offline_repair.py` | `scripts/vguided-cegar/` | Reads context JSON, calls LLM, writes repair candidates |
| `b5_offline_rerun.sh` | `scripts/vguided-cegar/` | Wrapper for Phase 3 rerun |

### B5ContextDumper responsibilities:

1. Collect up to 5 recent refinement failures
2. For each failure:
   - Serialize spurious trace (node numbers, line numbers, descriptions)
   - Dump block formulas as SMT-LIB2 text
   - Dump interpolants as SMT-LIB2 text
   - Dump abstraction formulas at each state
   - Include CFA edge branch conditions
3. Serialize current precision (global + local predicates as SMT-LIB2)
4. Serialize LLM candidate fates (entailed, abstraction-candidate, rejected, injected, scores)
5. Serialize source code and assertion expression
6. Write as JSON

## 6. Target Benchmark Set

| Benchmark | Reason |
|-----------|--------|
| sum04-2 | V4 regressed; B2 success but fragile (depends on LLM nondeterminism) |
| const_1-2 | V4 regressed; needs better predicates |
| diamond_1-2 | bounds-dominated; precision may help |
| eureka_01-2 | No-effect case; test if trace context enables repair |

Plus one positive control (diamond_1-1) to verify B5 does not break known wins.

## 7. Success Criteria

1. **B5 produces predicates that are not already in B2's output** — context provided to LLM leads to different/generated predicates
2. **B5 improves over B2 on at least one B2 no-effect or weak case** — e.g., const_1-2 refinement counts decrease
3. **B5 does not regress on known positive cases** — diamond_1-1 remains at ~2 refinements
4. **B5 repair context is plausible** — dumped interpolants/trace/precision are human-readable and contain the information needed to guide repair

### NOT success criteria (avoid claiming prematurely):
- B5 is generally effective
- B5 works on all benchmarks
- B5 replaces B2
- Refinement reduction equals runtime speedup

## 8. What B5 Adds That B4 Lacked

B4's context was too weak: it dumped aggregate stats (refinement count, fallback count)
but NOT the actual interpolants, trace details, or precision predicates.

B5 provides:
- **Interpolants**: the exact formulas CPAchecker derived, which encode what the engine knows
- **Trace structure**: which paths were spurious and what branches were taken
- **Current precision**: what predicates are already tracked
- **Candidate fates**: which LLM candidates were used, rejected, and why

This gives the LLM a concrete picture of **why CEGAR is failing** at this benchmark.

## 9. Implementation Sequence

1. **Access points** (done — documented above)
2. **`B5ContextDumper.java`**: collect trace/interpolant/precision/fate context, format as JSON
3. **`dumpB5Context()` in `PredicateCPARefiner`**: trigger from env var `VGUIDE_B5_DUMP_CONTEXT=1`
4. **`b5_offline_repair.py`**: LLM prompt with rich context, parse output
5. **`injectB5RepairOnce()`**: read repair JSON, parse, inject predicates
6. **Evaluation**: run target benchmark set, compare B2 vs B5

Do not implement until Step 1 (access points) is confirmed correct.

## 10. Validated Prompt (Original B5)

The validated B5 repair prompt has the structure:

```
SOURCE CODE
TARGET ASSERTION
CEGAR FAILURE CONTEXT (per-refinement: trace, branch conditions, interpolants, block formulas, abstraction states, precision, candidate fates)
REPAIR TASK: "Generate abstraction predicates that would help CPAchecker rule out these spurious traces and prove the assertion. Avoid already-entailed predicates. Avoid duplicates. Prefer relational predicates. Output JSON: {\"N<node>\": [\"(pred1)\", ...]}"
SMT-LIB2 BV SYNTAX GUIDE
OUTPUT FORMAT SPECIFICATION
```

The LLM receives rich CEGAR context and is asked to generate repair predicates with simple rules. There is **no** explicit "find the gap" or "analyze interpolants" instruction. The LLM performs implicit gap analysis from the context.

Validated results: sum04-2 (7→2), const_1-2 (47→36), 0 regressions on 6 benchmarks.

## 11. Rejected Variant: Explicit Interpolant-Gap Prompt (B5-gap)

### What Was Tested

The B5 prompt was extended with explicit gap-analysis instructions:

```
Step 1: Identify the Interpolant Gap
  1. What do the current interpolants already express?
  2. What does the assertion require?
  3. What relation is MISSING?
  4. Where should the predicate be tracked?
Step 2: Generate Repair Predicates
```

### Results (4 benchmarks, 2026-05-29)

| Benchmark | Original B5 | B5-gap | Δ |
|-----------|:-----------:|:------:|-----|
| sum04-2 | 2 (improvement) | 6 (regression) | -4 |
| const_1-2 | 36 (improvement) | 46 (regression) | -10 |
| diamond_1-2 | 27 | 27 | 0 |
| sum01-1 | 11 | 11 | 0 |

### Root Cause

1. **SSA-encoded variable names**: The gap prompt instructs the LLM to "look at the interpolants" where variables appear in SSA-encoded form (`|main::sn@2|`, `|main::i@3|`). The LLM copies these encoded names verbatim into its output, which the parser cannot handle. Result: 0/1 parsed on sum04-2, 0/5 parsed on sum01-1.

2. **Degraded predicate quality**: On const_1-2, the gap prompt produced `x=0` (a simple unary predicate) instead of the accumulator/constraint relations that the original B5 produced. Injection worsened refinements (35→46 vs. original B5's 47→36).

3. **Explicit reasoning side effect**: Forcing the LLM to produce explicit gap analysis before predicates shifts its attention to low-level SMT syntax, degrading its ability to generate correct source-level repair predicates.

### Decision

**B5-gap is rejected.** The original B5 prompt (implied gap reasoning) is the validated variant.

The lesson: **CEGAR context should be provided as background evidence, but the LLM must not be asked to explicitly reason over low-level SMT/SSA formulas. The LLM performs implicit gap analysis from rich context; forcing explicit analysis over encoded formulas degrades output quality.**

## 12. Output Contract (Prompt Discipline)

To prevent regressions like B5-gap, all B5 repair prompts must enforce:

### Allowed Output

- Source-level variable names: `x`, `y`, `i`, `sn`, `distance`, etc.
- Supported SMT-LIB2 BV operators: `=`, `<`, `>`, `<=`, `>=`, `+`, `-`, `*`, `mod` (or aliases `bvslt`, `bvsgt`, `bvsle`, `bvsge`, `bvadd`, `bvsub`, `bvmul`, `bvurem`)
- Numeric constants: `(_ bv5 32)` or simple integers in parser-supported forms

### Forbidden Output

- SSA-encoded variable names: `|main::sn@2|`, `|main::i@3|`
- Internal solver symbols: `.def_43`, `.def_69`
- Raw interpolant terms copied verbatim
- Array theory: `select`, `store` (parser does not support)
- Bitvector shift/bitslice: `bvshl`, `bvlshr`, `(_ extract ...)` (parser does not support)

### Contract Enforcement (Future)

A pre-injection validator can check repair candidates and reject those containing forbidden symbols, returning the diagnostic `REJECTED_INTERNAL_SYMBOL`. This would enable safe multi-round repair with feedback: "Your previous output used internal encoded variables. Use source-level names only."
