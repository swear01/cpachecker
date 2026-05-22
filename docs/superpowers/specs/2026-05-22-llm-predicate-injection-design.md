# LLM Predicate Injection for CEGAR — Design Spec

**Date:** 2026-05-22
**Status:** draft
**Supersedes:** `2026-05-18-vocabulary-guided-cegar.md` (strategy-selection approach)

## Overview

Replace the multi-strategy interpolation selection with direct LLM predicate injection.
The LLM produces per-location predicates (V) from source code, and CEGAR uses V in two ways:

- **Direction 1 — Predicate Injection:** during refinement, pick relevant V predicates for the current trace, SMT-validate them, and use them *instead of* interpolation. Fall back to interpolation when V is too weak.
- **Direction 2 — Predicate Filter:** after refinement, drop predicates whose variables have no overlap with V, keeping the abstraction lean.

Both directions reuse the existing `VocabularyGuide` and `LLMConnector` infrastructure.
The multi-IM scoring (`VocabularyGuide.score`, `selectBest`, `subsumptionScore`, `varOverlapScore`) is removed.

---

## Architecture changes

### Files

| File | Action | Summary |
|------|--------|---------|
| `LLMConnector.java` | Modify | New prompt: per-location predicates (structured JSON). Keep async sidecar. |
| `VocabularyGuide.java` | Modify | Predicates now carry location info (`VocabEntry` gets `CFANode` or `String` location key). Add `getPredicatesForLocation(loc)` query. Remove scoring methods. |
| `PredicateCPARefiner.java` | Modify | Remove multi-IM path. Add V-injection path before interpolation. Add filter after refinement. |
| `PredicateCPARefinerFactory.java` | Modify | Remove 6-IM creation. Single stock `InterpolationManager`. |
| `docs/superpowers/plans/2026-05-18-vocabulary-guided-cegar.md` | Archive | Mark as superseded. |

### Removed code

- `PredicateCPARefiner.allInterpolationManagers` + `interpolationManagerLabels`
- `PredicateCPARefinerFactory` — 6-IM loop, `imLabels`
- `VocabularyGuide.score()`, `selectBest()`, `subsumptionScore()`, `varOverlapScore()`, `jaccard()`, `recordConsidered()`, `recordSelected()`, `getUsageStats()`
- `VocabularyGuide.S scoredResult`
- Config options `vocabularyGuideAlpha`, `vocabularyGuideTau` (no longer needed)

### Kept code

- `LLMConnector` — async daemon with `requestInitialVocab()`, `start()`, `stop()`, background/CE updates, Jackson parsing, env-var config
- `VocabularyGuide` — `addPredicates()`, `removePredicates()`, `isEmpty()`, `getAllPredicates()`, `VocabEntry`
- `PredicateCPARefiner.triggerVocabularyUpdate()`, `isEmpty()` fallback

---

## Direction 1 — Predicate Injection

### New LLM prompt

```
You are a software verification expert analyzing a C program.
For each important program point (loop head, function entry, key condition),
output a JSON object mapping location to predicate arrays.

Format:
{
  "loop at line 12": ["i >= 0", "i < n"],
  "function foo entry": ["x != NULL"]
}

Rules:
- Only produce predicates you are HIGHLY confident about.
- If unsure, produce nothing (empty object or skip the location).
- Use variable names exactly as they appear in the source code.

Source code:
<source>
```

The LLM chooses which locations and how many predicates. The output is a JSON object with string keys (location descriptions). The existing `parsePredicates()` in `LLMConnector` uses regex to extract quoted strings; it must be adapted to also extract the location key from the JSON structure. A Jackson-based approach (already available) can parse the full JSON object: iterate keys as location strings, iterate values as predicate arrays.

### VocabEntry with location

```java
static class VocabEntry {
    final String locationKey;       // e.g. "loop at line 12", "function foo entry"
    final BooleanFormula predicate;
    // ... usage stats can stay but are not used for scoring
}
```

### Refinement flow (in `performInterpolatingRefinement`)

```
1. if (!useVGuide || vocabularyGuide == null || vocabularyGuide.isEmpty())
     → stock interpolation (existing path)

2. Map V predicates to ABA locations on the current trace:
     For each ABA state in abstractionStatesTrace:
       find V predicates whose locationKey matches this state's CFA node
     → candidatePredicates[stateIndex] = List<BooleanFormula>

3. SMT-validate candidates:
     For each candidate p at state s:
       check: blockFormula(s) ∧ ¬p  is UNSAT?
       (i.e. p is implied by the path formula at that state → p holds)
     If UNSAT → p is valid on this trace → keep
     Else → drop

4. If validated predicates are empty:
     triggerVocabularyUpdate(traceFormulas)  // ask LLM for more
     → fall back to stock interpolation

5. If validated predicates exist:
     Build CounterexampleTraceInfo.infeasible(validatedPredicates)
     Record this refinement succeeded with V

6. Same-trace guard:
     If repeatedCounterexample is true AND we used V predicates last time:
       → skip V, go straight to stock interpolation
       (V predicates were too weak to rule out this trace)
```

### Location matching

CFA nodes don't carry source line numbers natively in CPAchecker's `CFANode`. We need a mapping:

**Option A (simpler):** Prompt the LLM to use function/loop names as location keys (e.g., `"function main"`, `"loop main::for_i"`). Map `CFANode.getFunctionName()` and loop structure to these keys.

**Option B:** Extract line numbers from `CFANode` (some CFA nodes carry `ASTNode` → line info via the CFA edge's `FileLocation`). More precise but fragile.

Choose **Option A** for v1.

---

## Direction 2 — Predicate Filter

### Filter after refinement

After `strategy.performRefinement()` returns, the list of new predicates is known (it's the `counterexample.getInterpolants()` passed into `performRefinement`). The filter runs on these predicates:

```
for each predicate p in refined predicates:
  vars(p) = extractVariableNames(p)
  if vars(p) ∩ vars(V) is empty:
    remove p from precision increment
```

The filter only removes predicates that have zero variable overlap with *any* V predicate. This is a conservative filter: only obviously-irrelevant predicates get dropped.

### Config option

```java
@Option(secure = true,
    description = "Filter refinement predicates by V vocabulary overlap")
private boolean vocabularyFilter = false;
```

Defaults to `true` when `useVocabularyGuide=true`, but can be toggled independently.

---

## V lifecycle

```
Factory.create():
  llm.start()              // daemon thread
  llm.requestInitialVocab() // async, non-blocking

CEGAR starts immediately. V may be empty initially → stock interpolation.

First refinement with V (when daemon eventually populates it):
  - try V injection → if works, use V predicates
  - else fallback interpolation

Background updates (daemon thread):
  - traces accumulate in pendingTraces
  - every 10+ traces → backgroundUpdate() → LLM generates more predicates
  - CE_GUIDED: triggered when V injection fails 3+ consecutive times

V grows over time. Later refinements benefit from richer V.
```

---

## Config options

| Option | Default | Description |
|--------|---------|-------------|
| `useVocabularyGuide` | false | Enable LLM predicate injection |
| `vocabularyFilter` | true | Filter refinement predicates by V variable overlap |

`vocabularyGuideAlpha` and `vocabularyGuideTau` are removed.

---

## Testing

1. **Unit:** Verify location-key mapping from CFA node to V entry
2. **Integration:** Run `array-1.c` with V-guided — should use V predicates (verify via stats/log)
3. **Fallback:** Run with invalid API key — should fallback to stock interpolation, produce correct result
4. **Filter:** Run a program with irrelevant interpolant atoms — verify they get filtered out when `vocabularyFilter=true`
5. **Regression:** Stock CPAchecker (no V-guided) produces identical results to before

---

## Open questions

1. **Location mapping precision:** Option A (function/loop name) may be ambiguous for programs with multiple loops in the same function. Acceptable for v1; iterate with line numbers later.
2. **SMT-validate cost:** One SMT call per candidate predicate per refinement. With small V (< 20 predicates), this is negligible. Track in stats.
3. **Filter aggressiveness:** The current conservative filter (overlap=0 → remove) is safe. A more aggressive filter (e.g., cosine similarity threshold) could be explored later.
