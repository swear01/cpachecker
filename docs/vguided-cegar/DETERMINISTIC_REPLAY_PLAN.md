# Deterministic Replay Plan — Fixing B2 LLM Non-determinism as a Confounder

## 1. Problem

B2 uses an LLM to generate predicates from source code. The same prompt produces different predicate quality across runs due to LLM non-determinism (temperature=0 is not a guarantee).

This confounds B2 vs B5 comparison:
- When B2 luckily generates the right predicate (e.g., sum01-2: 2 refs), B5 has no headroom.
- When B2 generates weak predicates (e.g., sum01-2: 37 refs), B5 shows improvement.
- The "B5 improvement" delta depends partly on whether B2 happened to be unlucky.

We cannot claim B5 superiority over B2 without controlling for this variance.

## 2. Solution: LLM Output Cache + Replay

Record B2's LLM output once. On replay, bypass the LLM call and inject the cached predicates. This gives a deterministic B2 baseline.

Then record B5's LLM output once. On replay, inject the same cached B5 repair predicates. This gives a deterministic B5 vs B2 comparison where the only difference is the B5 repair predicates.

### Env Flags

| flag | value | meaning |
|------|-------|---------|
| `VGUIDE_LLM_RECORD` | `1` | Record LLM output to `VGUIDE_LLM_CACHE_DIR/<benchmark>/` |
| `VGUIDE_LLM_REPLAY` | `1` | Bypass LLM, inject cached predicates from cache dir |
| `VGUIDE_LLM_CACHE_DIR` | `<path>` | Cache directory root |

### Record Mode

```
VGUIDE_LLM_RECORD=1 VGUIDE_LLM_CACHE_DIR=<dir>
```

During B2's `initializeVocabBlocking()`:
1. LLM is called normally.
2. The raw LLM response text is saved to `<cache_dir>/<benchmark>/b2_llm_output.json`.
3. The parsed/generated predicates are saved to `<cache_dir>/<benchmark>/b2_vocabulary.json`.
4. Normal B2 execution continues.

During B5's repair call:
1. LLM is called normally.
2. The raw LLM response is saved to `<cache_dir>/<benchmark>/b5_repair_output.json`.
3. The validated repair candidates are saved to `<cache_dir>/<benchmark>/b5_repair_candidates.json`.
4. Normal B5 injection continues.

### Replay Mode

```
VGUIDE_LLM_REPLAY=1 VGUIDE_LLM_CACHE_DIR=<dir>
```

During B2's `initializeVocabBlocking()`:
1. LLM is NOT called.
2. Cached vocabulary is loaded from `<cache_dir>/<benchmark>/b2_vocabulary.json`.
3. Injected into VocabularyGuide exactly as if the LLM had generated it.
4. B2 runs with the same predicates every time.

During B5's repair (if enabled):
1. LLM is NOT called.
2. Cached repair candidates are loaded from `<cache_dir>/<benchmark>/b5_repair_candidates.json`.
3. Validated and injected exactly as if the LLM had generated them.
4. B5 rerun uses the same repair predicates every time.

## 3. Evaluation Workflow

### Phase 1: Record

For each benchmark in the confirmed positive set (sum04-2, const_1-2, functions_1-2, nested_1-2):

1. Run B2 with RECORD mode to capture a specific B2 run.
2. Run B5 with RECORD mode using the same B2 cache to capture a specific B5 repair.

### Phase 2: Replay B2 alone

For each benchmark, replay the cached B2 predicates (no B5). Record B2 refinement count. This is the deterministic B2 baseline.

### Phase 3: Replay B2 + B5

For each benchmark, replay the cached B2 predicates AND inject the cached B5 repair predicates. Record B5 refinement count.

### Phase 4: Compare

| benchmark | B2 (deterministic) | B5 (deterministic) | Δ |
|-----------|-------------------:|-------------------:|-----|
| sum04-2 | | | |
| const_1-2 | | | |
| functions_1-2 | | | |
| nested_1-2 | | | |

### Phase 5: Sensitivity test

Re-record with a different LLM run (re-record B2 and B5 from a fresh LLM call). Replay and compare. This tests whether B5 improvement is robust across different LLM outputs.

## 4. Implementation Plan

### Java Changes

In `LLMConnector.java`:
- Add `recordMode` and `replayMode` fields initialized from env vars.
- In `initializeVocabBlocking()`: if replay mode, load from cache instead of calling LLM.
- After LLM call: if record mode, save output to cache.
- Add `loadVocabularyFromCache()` and `saveVocabularyToCache()` methods.

In `PredicateCPARefiner.java`:
- In `injectAbstractionCandidates()` / `injectRepairPredicatesOnce()`: if replay mode and B5 candidates file exists, load instead of relying on current run's dumper output.

### Python Changes

In `b5_repair_from_prompt.py`:
- Add `--record` and `--replay` flags.
- If replay: skip LLM call, load cached candidates.
- If record: save LLM output to cache dir after call.

## 5. Expected Benefits

1. **Eliminates LLM non-determinism**: Same predicates every run, same B2 baseline.
2. **Enables fair B2 vs B5 comparison**: The only variable is whether B5 repair predicates are injected.
3. **Enables sensitivity analysis**: Re-record with different LLM runs to see if improvement is robust.
4. **Makes results reproducible**: Any researcher can replay the exact cached predicates.
5. **Enables controlled experiments**: Vary one factor at a time (e.g., B2 predicates only, B5 predicates only, both).
