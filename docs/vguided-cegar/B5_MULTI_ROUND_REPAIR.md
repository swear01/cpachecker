# B5-MR: Multi-Round Trace/Interpolant-Guided LLM Repair

## 1. Motivation

### Current B5 Status

B5 (single-round trace/interpolant-guided repair) has demonstrated:
- Stable refinement reduction on 5/10 B2-hard solved cases (K=3, 100% improvement frequency)
- 0 algorithm-level regressions across 14 evaluated benchmarks
- Output contract validator prevents internal-symbol injection

### Gap

B5 has **not yet converted a B2 UNKNOWN/TIMEOUT into TRUE**. All improved cases were B2-hard but solved (e.g., 74→41 refinements). The accessible benchmark pool (98 scalar loops) contains 0 B2_TIMEOUT cases at 30s timelimit.

Single-round repair may be insufficient for truly hard cases:
- A hard benchmark may require multiple auxiliary predicates discovered over successive CEGAR rounds.
- The first repair round may not produce the right predicate; subsequent rounds can refine based on updated CEGAR context.
- Each round exposes new spurious traces as the abstraction improves.

### Research Question

> Can multi-round trace/interpolant-guided LLM repair convert resource-bounded UNKNOWN/TIMEOUT into TRUE on harder relational-loop benchmarks, under the same total verifier budget?

## 2. Method Definition

```
B5-1  = current one-shot B5 repair (single LLM call, single injection)
B5-MR = multi-round B5 repair (K rounds, K LLM calls, cumulative injection)
```

### B5-MR Loop

```
Initialize precision ← B2 baseline
Initialize transcript ← [source code, assertion]
Initialize injected ← {}

for round r in 1..R:
  Run CPAchecker with current precision + injected predicates
  Timelimit: per_round_budget
  If TRUE/FALSE: STOP (solved)

  Dump CEGAR context:
    - spurious traces (up to N)
    - CFA edge branch conditions
    - block formulas (SMT-LIB2)
    - interpolants per abstraction state
    - current precision predicates
    - previously injected predicates
    - LLM candidate fates

  Append round context to transcript (append-only)
  Build repair prompt from transcript

  Call LLM for repair predicates
  Validate candidates via output contract validator
  Dedup against previously injected predicates
  Inject new validated predicates into precision

  If no new valid predicates: STOP (stagnation)
  If predicate count exceeds cap: STOP (precision explosion)
  If total budget exhausted: STOP
```

## 3. Budget Fairness

All comparisons use the same total verifier budget:

| Mode | Per-round budget | Rounds | Total budget |
|------|-----------------:|-------:|-------------:|
| B2 baseline | 300s | 1 | **300s** |
| B5-MR (short) | 60s | 5 | **300s** |
| B5-MR (long) | 120s | 5 | **600s** |

**Resource-bounded rescue**: B2@60s UNKNOWN → B5-MR@300s total TRUE.
**Strong rescue**: B2@300s UNKNOWN → B5-MR@300s total TRUE.

## 4. Transcript Design (Append-Only)

### Structure

```
SOURCE CODE
ASSERTION
---
ROUND 1
  SPURIOUS TRACE
  CFA EDGES / BRANCH CONDITIONS
  INTERPOLANTS (SMT-LIB2, atoms extracted)
  CURRENT PRECISION
  LLM CANDIDATE FATES
  FORMAL RESULT: result=R, refs=N, time=T
---
ROUND 2
  (appended context)
---
...
```

### Rules

1. **Append-only**: previous rounds remain byte-identical.
2. **Only append new sections**: current round context is appended, not inserted.
3. **Preserve prompt cache friendliness**: each round's prompt is a strict prefix of the next round's prompt (except when checkpointing).
4. **Output contract always included**:
   - Source-level variable names only (`x`, `y`, `i`, `sn`)
   - NO `|main::x@k|` (SSA pipe names)
   - NO `.def_*` (solver terms)
   - NO raw let-bound SMT temporaries

### Prompt Example (Round R)

```
You are helping a CEGAR-based verifier stuck on a benchmark.

SOURCE CODE:
<source>

ASSERTION: __VERIFIER_assert(<expr>)

PREVIOUS ROUNDS:

--- ROUND 1 ---
<round 1 context>
FORMAL RESULT: result=X, refs=N, time=T
LLM GENERATED: <predicates>
LLM INJECTED: <predicates>

--- ROUND 2 ---
...

--- ROUND R ---
CURRENT SPURIOUS TRACE:
<trace>
CURRENT INTERPOLANTS:
<interpolants>
CURRENT PRECISION:
<precision>
PREVIOUSLY INJECTED:
<all predicates injected so far>

Generate additional repair predicates that address the remaining spurious traces,
focusing on relations not yet captured by the previously injected predicates.
Output JSON: {"N<node>": ["(pred1)", ...]}
```

## 5. Candidate Management

### Per-Round

- **Generated**: LLM output after parsing
- **Accepted**: after validator pass
- **Rejected**: rejected by validator, with reason
- **Injected**: actually inserted into precision

### Across Rounds

- **Cumulative injected**: all predicates ever injected
- **Duplicate detection**: skip predicates already in cumulative set
- **New per round**: predicates not seen before
- **Stagnation detection**: 0 new predicates for 2 consecutive rounds → STOP

### Stop Conditions

1. TRUE/FALSE reached.
2. No new valid predicates in a round.
3. All candidates rejected by validator.
4. Same predicates repeat across rounds.
5. Cumulative predicate count exceeds cap (default: 50).
6. No improvement in refinement count for 2 consecutive rounds.
7. Total budget exhausted.

## 6. Evaluation Plan

### Modes

| mode | LLM calls | rounds | total budget |
|------|----------:|-------:|-------------:|
| B2 | 1 | 1 | 300s |
| B5-1 | 2 (B2+repair) | 1 | 300s |
| B5-MR | 1+R | R | 300s |

### Metrics

| metric | B2 | B5-1 | B5-MR |
|--------|----|------|-------|
| result (TRUE/FALSE/UNKNOWN) | | | |
| total verifier time | | | |
| total refinements | | | |
| rounds used | — | — | |
| predicates injected | | | |
| solved-from-UNKNOWN | | | |
| resource-bounded rescue | | | |

### Success Criteria

1. **At least one** B2 UNKNOWN/TIMEOUT → B5-MR TRUE under same budget.
2. **Or** B5-MR solves within lower total budget than B2.
3. **Or** B5-MR reduces refinements more than B5-1 on hard solved cases.

## 7. Risks and Mitigations

| risk | mitigation |
|------|-----------|
| Context unavailable before timeout | Increase per-round budget or relax first round budget |
| Repeated repair predicates | Dedup against cumulative injected set |
| Precision explosion | Cap cumulative predicate count (50 default) |
| Parser limitations on harder benchmarks | Pre-filter parser-supported benchmarks |
| B5-MR accelerates but doesn't rescue | Accept as valid improvement, not failure |
| Benchmark pool lacks suitable hard cases | Search external SV-COMP benchmark repositories |

## 8. Implementation Sequence

1. Search for harder benchmarks (RESOURCE_TIMEOUT / STRONG_TIMEOUT)
2. Run B2 baseline @60s and @300s
3. Classify and select B5-MR targets
4. Implement B5-MR runner (multi-round loop)
5. One-target smoke test
6. If smoke succeeds: small evaluation (≤5 targets)
7. Full evaluation only if smoke shows rescue potential
