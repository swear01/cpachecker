# Overview

## What This Is

CPAchecker is a configurable software verifier for C programs, used in SV-COMP competitions. This fork adds **VGuide (Vocabulary-Guided CEGAR)**: an LLM-in-the-loop extension that injects predicate candidates into the PredicateCPA refinement loop, improving solve rates on reachability/loops benchmarks without compromising soundness. The LLM only proposes candidates; the SMT solver/checker validates them (Tier S) or controls resource/routing decisions only (Tier R). No Tier X (direct LLM verdict) is ever allowed.

## Key Concepts / Domain

| Term | Meaning |
|------|---------|
| CEGAR | Counterexample-Guided Abstraction Refinement — the core loop VGuide hooks into |
| PredicateCPA | The predicate-abstraction component; VGuide fires here on refinement |
| Tier S / R / X | Soundness tiers: S = verified candidate, R = resource/config only, X = forbidden |
| VGuide | The LLM bridge; Java class at `src/.../vguide/` |
| `run.sh` | Single entry point for all experiments; reads benchmark manifests |
| `full_scalar` | 217-task benchmark set (SV-COMP reachability); main eval suite |
| `sample` | 8-task subset for quick smoke tests |
| svcomp26-vguide | The competition config: routes reachability + overflow through VGuide |
| Class-A | Config-only generalization (no Java change needed) |
| Class-B | Requires Java engine hook; not yet attempted |
| PAR-2 | Penalized Average Runtime × 2 — the competition scoring metric |
| `min_interval` / `every_n` | LLM call scheduling knobs in `config/vguide.properties` |
| L1 / L2 | Predicate validation: contract + parse (always on) |
| noL3 | L3 SMT entailment not used (`enableL3Entailment=false`); ablation showed worse solved count / PAR-2 |

## External Resources

- Upstream CPAchecker: https://cpachecker.sosy-lab.org
- SV-COMP benchmark repo: `~/sv-benchmarks/c` (not in repo; required for experiments)
- LLM API: DeepSeek V4 — see `docs/vguided-cegar/llm/LLM_API.md`
- Architecture: `docs/vguided-cegar/architecture/UNIFIED_VGUIDE_ARCHITECTURE.md`
- Run instructions: `docs/vguided-cegar/RUN_EXPERIMENTS.md`
