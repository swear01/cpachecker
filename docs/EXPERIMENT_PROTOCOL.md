# Experiment Protocol (evidence tiers, CPU isolation & load management)

> Strict CPU controls apply to formal timing/performance measurement, not to
> every predicate capability or mechanism experiment.
> Derived from the previous agents' fleet operations (Codex records,
> `cap16_scheduler.py`, `monitor.py`, `dataset.py` — see the GitHub Wiki
> Baseline-Protocol).

## 1. Choose the evidence tier

| Tier | Question | Resource rule | Accepted claim |
|---|---|---|---|
| Capability | Can predicates change `UNKNOWN` into the correct solved verdict? | Record host, limits, load and provenance; idle-ready placement is optional. Replicate the transition. | Verdict/capability only; timing is descriptive. |
| Mechanism | Which predicate, location or later refinement changes the trajectory? | Match commit/config/limit/replay artifacts. Record load; rerun near-timeout or visibly asymmetric cases. | Predicate/refinement attribution; no precise speedup. |
| Performance | Does the method improve population solve count, time or PAR-2? | Sections 2–3 are mandatory. | Formal comparative performance. |

Do not label a run globally invalid merely because it lacks CPU isolation. It
remains usable for a correct, replicated verdict/refinement claim, with timing
explicitly excluded. Wrong verdicts, crashes/incomplete records and provenance
mismatches invalidate the affected semantic evidence.

## 2. CPU isolation (mandatory for Performance tier)

- Machine pool: three hosts with comparable P-cores:
  - `valkyrie` (i9-13900K, local), `athena`, `cthulhu` (i9-14900K-class).
  - On P-cores the two CPU models are treated as equivalent and may be
    mixed across runs.
- P-core topology: 8 physical P-cores = logical CPUs `0,2,4,6,8,10,12,14`
  (no SMT sibling, no E-core). E-cores (logical 16-31) must never carry
  CPAchecker/solver/harness measurement work.
- Every CPAchecker invocation must be pinned: `taskset -c 0,2,4,6,8,10,12,14`.
- Parallelism must not exceed the pinned pool (parallel ≤ 8 for one
  slot-style run; the previous formal baseline used two 4-core slots on
  the same 8 P-cores).

## 3. Pre-run load check (Performance tier)

Before a Performance-tier run starts:

1. Sample per-P-core utilization (mpstat, 1s window) on the P-core pool;
   any P-core ≥ 50% busy → **refuse** (foreign_p_core_contention).
2. Scan processes by PSR; concurrent non-trivial local processes on the
   pinned CPUs → **refuse**.
3. Record the check result as run evidence (e.g. `run_meta.json`
   `load_check: idle|busy:...` + `cpu_isolation` field).
4. The fleet availability monitor (`monitor.py`: valkyrie/athena/cthulhu,
   mpstat per P-core, `idle_ready` status) decides which machine to run
   on; pick a host with status `idle_ready`.

Runs with foreign load on the P-core pool are invalid for precise timing/PAR-2
claims. Correct replicated verdict-only and mechanism claims may still be
reported with the recorded load and an explicit timing exclusion.

`run_core_only.sh` remains the strict Performance-tier runner and may refuse a
busy host. Capability/mechanism work should use the task-specific harness; do
not weaken or bypass a formal runner and then present its output as formal timing.

## 4. Evidence

- `load-monitor.jsonl`-style records (schema `formal-p-core-load-monitor-v1`):
  host, boot id, per-P-core usage, busy set, high-CPU processes, cgroup
  delegation state.
- `run_meta.json` per run: commit, config/manifest hashes, limits,
  `cpu_isolation`, `load_check`.

## 5. This repository

- The clean implementation lives on `research/vguide-upstream-reimpl`
  (base = latest upstream CPAchecker main).
- The core-only evaluation harness (`run_core_only.sh`) implements §2–§3;
  the legacy fork keeps the historical implementation for reference.

## 6. Fleet build hygiene (learned 2026-08-12)

- NEVER trust incremental `ant build` after syncing code to a fleet machine:
  NFS mtime skew defeats ant's up-to-date checks, and stale `classes/`
  (built by a previous agent from different source) survives silently.
  Symptom: `NoSuchMethodError` at runtime (augmented arm crashed 167/224
  with `VGuideOptions.isShadowPredicateUtilityGateEnabled`).
- Always `ant clean` before `ant build` after a code sync; a full build is
  ~1m30s (anything much faster means nothing was recompiled).
- The launcher classpath is `~/cpachecker/classes` (not `build/classes`).
- Validate after a rebuild: run the 12-task smoke on the target machine and
  inspect per-task logs for real CPAchecker startup (a "instant completion"
  run with all-UNKNOWN verdicts is a red flag, not a pass).
