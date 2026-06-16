# Roadmap

See `docs/vguided-cegar/LLM_RESEARCH_ROADMAP.md` for the full long-horizon map.

## Backlog

- **v2.0: Ranking-function hook for Termination** — requires new Java engine hook in `TerminationToReachCPA`; Class-B (cannot be done config-only). See `SVCOMP26_TERMINATION_VGUIDE_PROBE.md`.
- **MemSafety / DataRace probes** — check if predicate-CEGAR fires; if yes, Class-A config generalization. See `LLM_RESEARCH_ROADMAP.md §3.1`.
- **FALSE path / witness generation** — LLM for counterexample witness hints (Tier S). Long horizon.
- **Offline corpus learning** — pre-compute predicate libraries per program class. Exploratory.
- **svcomp27 full integration** — packaging VGuide into the competition submission.

## Recently Done

- **消融實驗 source-prior 實作** — `vguide.sourcePriorMode`、`ContextPackBuilder.buildSourceOnly()`、`PredicateCPA.registerPreCegarBridge()`、兩個實驗 config；`run.sh` 加 `source-prior-loops` / `source-prior-overflow` mode (2026-06-16)
- v1.6: Overflow Class-A generalization — `svcomp26-vguide` now routes overflow through VGuide; +6 solved, 0 wrong (2026-06-15)
- v1.6 termination probe: RED (Class-B confirmed; tabled for v2.0) (2026-06-13)
- v1.5.1: Loops + full_scalar on svcomp26-vguide; 16 direct LLM predicate wins (2026-06-14)
- v1.5: Broad Loops set +37 vs stock (2026-06-13)
- Unified VGuide architecture: replaced all B2/B4/B5 sidecar designs with single Java path
