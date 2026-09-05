# Overview

## What This Is

CPAchecker is a configurable software verifier for C programs, used in SV-COMP competitions. This fork adds **VGuide (Vocabulary-Guided CEGAR)**: an LLM-in-the-loop extension with implemented predicate and termination-ranking candidate paths. The current research entry point is the authenticated hard-218 manifest lineage; current exploratory work is trend evidence, not formal timing or publication data. The LLM only proposes candidates/search spaces (Tier S) or controls resource/routing decisions (Tier R). No Tier X (direct LLM verdict or unverified assumption) is allowed.

## Key Concepts / Domain

| Term | Meaning |
|------|---------|
| CEGAR | Counterexample-Guided Abstraction Refinement — the core loop VGuide hooks into |
| PredicateCPA | The predicate-abstraction component; VGuide fires here on refinement |
| Tier S / R / X | Soundness tiers: S = verified candidate, R = resource/config only, X = forbidden |
| VGuide | The LLM bridge; Java class at `src/.../vguide/` |
| VGuide-NLA | Stopped after ordinary KI and final PDR/KI-PDR oracle gates: every reference-candidate arm produced 0/12 target wins |
| Usefulness gate | Opt-in Tier-R pre-injection guard: short traces with multiple multiplicative predicates keep standard refinement but skip VGuide precision injection and later LLM rounds |
| `run.sh` | Single entry point for all experiments; reads benchmark manifests |
| `hard-218` | Current comparable hard-case cohort: frozen 224 parent minus six #92 diagnostic tasks |
| `full_scalar` | Historical 217-task scalar subset; not the current hard-case evaluation |
| `sample` | 8-task subset for quick smoke tests |
| svcomp26-vguide | Historical competition config; current checkpoint uses the frozen hard-218 protocol |
| Class-A | Config-only generalization (no Java change needed) |
| Class-B | Requires a Java engine hook; termination ranking hook exists, but is bounded mechanism evidence |
| PAR-2 | Penalized Average Runtime × 2 — the competition scoring metric |
| `first_spurious` | Current LLM call schedule in `config/vguide.properties`; older schedules are historical |
| L1 / L2 | Predicate validation: contract + parse (always on) |
| noL3 | L3 SMT entailment not used (`enableL3Entailment=false`); ablation showed worse solved count / PAR-2 |

## External Resources

- Upstream CPAchecker: https://cpachecker.sosy-lab.org
- SV-COMP benchmark repo: `~/sv-benchmarks/c` (not in repo; required for experiments)
- LLM API: Meta Muse Spark 1.2 Contributor, minimal reasoning, via the production Java client
- Research design: [GitHub Wiki](https://github.com/swear01/cpachecker/wiki)
- Run protocol and artifacts: `/home/swear01/cpachecker-experiments/`
- Final hard-case Dataset v2 evidence: `docs/vguided-cegar/evaluation/HARD_CASE_DATASET_V2_FINAL.md`
- Current manifest lineage: `docs/vguided-cegar/evaluation/HARD_218_MANIFEST_LINEAGE.md`
