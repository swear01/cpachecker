# Linear-Inequality-Inv-A B4 Rescue Validation

## Result

B4 rescue claim: B2 (UNKNOWN/89 refs) → B4 (TRUE/2 refs)

**Validation verdict: NOT VALIDATED as B4 rescue.**

Pure B2 (no forced parity, no repair) also solves in 1 refinement with TRUE result under identical settings. The earlier B2=89 (UNKNOWN) was from a different LLM run with lower-quality predicates.

## Data

| Mode | Refinements | Result |
|------|------------|--------|
| B0 Stock | 58 | UNKNOWN |
| B2 pure | 1 | TRUE |
| B2 + forced parity | 1 | TRUE |
| B4 fixed repair | 2 | TRUE |
| B4 regenerated repair | 2 | TRUE |

## Root Cause

LLM output is non-deterministic. In the current B2 run, the LLM generated the relational predicate `s >= 255*i` which is exactly what CPAchecker needs to prove this program. In the earlier batch run, the LLM did not generate this predicate.

This confirms a fundamental limitation: the LLM in the "rescue" mode did not use CEGAR feedback to discover the missing predicate; it happened to generate a better predicate from source code alone.

## Selected B2 Predicates

- `i >= 0` (ENTAILED)
- `s >= 0` (ENTAILED)  
- `s >= 255*i` (ENTAILED) — the key relational predicate
- `s < 65026` (ENTAILED)

## B4 Repair Predicate Fate

Fixed repair: 1 parsed, 9 failed, 1 injected
Regenerated: 4 parsed, 6 failed, 4 injected

Repair predicates were mostly parity/modulo-related, not directed at the actual bottleneck (missing `s >= 255*i`).

## Implications

1. The "B4 rescue" was an artifact of LLM non-determinism, not CEGAR-guided repair.
2. Pure B2 can solve this benchmark when the LLM generates good initial predicates.
3. Current repair context (result + refinements + vocabulary) is too weak — it doesn't tell the LLM what's missing.
4. B4 needs to expose the actual missing predicate (from spurious traces or interpolant analysis), not just aggregate statistics.

## Next Steps

- B4 repair context must include interpolant predicates from recent refinements
- Or B4 should identify which predicates were missing by comparing final precision with initial vocabulary
- Until then, batch B4 evaluation on hard cases is premature
