# SV-COMP 27 VGuide integration verification（2026-06-13）

Branch：`svcomp-integration`

## Commits

| Commit | Purpose |
|--------|---------|
| `e0aa0491dd` | P0-1 frozenDir uses config `@FileOption` path resolution |
| `f3c5ddd47d` | P0-2 dump task isolation and shutdown hook removal |
| `d899736704` | P0-3 disable VGuide under BAM with WARNING fallback |
| `a6a60bc29e` | P0-4 process-wide LLM round cap |
| `047c9e0b6d` | P1-1/P1-3 option text and LLM client availability check cleanup |
| `b9a76c317b` | P1-4 frozen-seed timing documentation |
| `4baeb087c1` | Add scoped `svcomp27-vguide` config variants |
| `65ffdba921` | Add scoped svcomp runner mode |

## Mechanical verification

| Command | Result |
|---------|--------|
| `ant build-project` | PASS (`BUILD SUCCESSFUL`) |
| `java -cp ... org.junit.runner.JUnitCore org.sosy_lab.cpachecker.cpa.predicate.vguide.*Test` | PASS: 36 tests OK |
| `bash -n scripts/vguided-cegar/run.sh scripts/vguided-cegar/run_benchmark_set.sh` | PASS |
| `ant checkstyle` | PASS (`BUILD SUCCESSFUL`) |
| runner trace: stock/vguide/scoped svcomp dry-run | PASS: stock/vguide still pass global false/true; scoped svcomp does not pass global `useVocabularyGuide` and uses `sv-comp-reachability.spc` |

## Smoke tests

All smoke tests used JDK 21 from `~/.local/bin/java`, `VGUIDE_LLM_THINKING=disabled`, and 60s CPA timelimit. LLM use was limited by `vguide.maxLlmRoundsPerProcess=2` for route A runs.

| Route | Task | Command shape | Evidence | Verdict |
|-------|------|---------------|----------|---------|
| A: official config + global option | `loops/count_up_down-1.c` | `config/svcomp27.properties` + `--option cpa.predicate.refinement.useVocabularyGuide=true` | log contains `Unified VGuide CEGAR enabled` and `VGuide LLM round # 1`; witness.yml produced | TRUE, expected TRUE |
| A: official config + global option | `loops/count_up_down-2.c` | same | log contains `Unified VGuide CEGAR enabled`; witness.graphml and witness.yml produced | FALSE, expected FALSE |
| A: recursive/BAM | `recursive/Addition01-2.c` | same | log contains `VGuide is not supported under BAM, falling back to standard refiner`; no crash | UNKNOWN within 60s |
| A: recursive/BAM | `recursive/EvenOdd01-1.c` | same | same BAM fallback WARNING; no crash | UNKNOWN within 60s |
| B: scoped config | `loops/count_up_down-1.c` | `config/svcomp27-vguide.properties`, no global `useVocabularyGuide` option | log contains `svcomp27-vguide--singleLoop-predicateAnalysis.properties`, `VGuide LLM round # 1`, and predicate injection; witness.yml produced | TRUE, expected TRUE |
| B: scoped recursive | `recursive/Addition01-2.c` | `config/svcomp27-vguide.properties`, no global option | log contains official `svcomp27--recursion.properties`; no `Unified VGuide CEGAR enabled`, no `VGuide LLM round`, no `VGuide predicate`; no crash | UNKNOWN within 60s |

Additional attempted smoke: `loop-invgen/up.i` under route A showed VGuide enablement and one LLM round, but stayed UNKNOWN within 60s; it was replaced by the smaller `count_up_down-*` tasks for verdict evidence.

## Artifacts

Smoke logs are local, not committed:

```text
output/vguide/svcomp_integration_smoke/routeA_count_up_down_1/cpa.log
output/vguide/svcomp_integration_smoke/routeA_count_up_down_2/cpa.log
output/vguide/svcomp_integration_smoke/routeA_recursive_addition01/cpa.log
output/vguide/svcomp_integration_smoke/routeA_recursive_evenodd01/cpa.log
output/vguide/svcomp_integration_smoke/routeB_scoped_count_up_down_1/cpa.log
output/vguide/svcomp_integration_smoke/routeB_scoped_recursive_addition01/cpa.log
```

## Notes / deviations

- `@FileOption(FileOption.Type.OPTIONAL_INPUT_FILE)` is used for `vguide.frozenDir` as planned. The annotation is also used broadly for CPAchecker config paths; the frozen predicate directory can remain absent without `FrozenPredicateLoader` failing, because the loader checks files with `Files.isRegularFile` and returns empty when none exists.
- The prompt-level requirement that the first bridge keep the original task directory name overrides the older plan text that suggested always adding `__b0`.
- Full `./scripts/vguided-cegar/run.sh cpa --set sample` was not executed because the smoke budget was capped at 10 tasks. Instead, runner dry-run/trace checks verified command construction, and the targeted CPA smoke tests covered both official-route and scoped-route execution.
