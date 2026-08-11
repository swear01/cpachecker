# Formal Experiment Protocol (CPU isolation & load management)

> Requirement for ALL formal measurement runs (baselines, the core-only
> 224-task evaluation, and any future timing-sensitive experiments).
> Derived from the previous agents' fleet operations (Codex records,
> `cap16_scheduler.py`, `monitor.py`, `dataset.py` — see the GitHub Wiki
> Baseline-Protocol).

## 1. CPU isolation (mandatory)

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

## 2. Pre-run load check (refuse, never run contaminated)

Before a formal run starts:

1. Sample per-P-core utilization (mpstat, 1s window) on the P-core pool;
   any P-core ≥ 50% busy → **refuse** (foreign_p_core_contention).
2. Scan processes by PSR; concurrent non-trivial local processes on the
   pinned CPUs → **refuse**.
3. Record the check result as run evidence (e.g. `run_meta.json`
   `load_check: idle|busy:...` + `cpu_isolation` field).
4. The fleet availability monitor (`monitor.py`: valkyrie/athena/cthulhu,
   mpstat per P-core, `idle_ready` status) decides which machine to run
   on; pick a host with status `idle_ready`.

Contaminated runs (any foreign load on the P-core pool during the
measurement window) are invalid for timing claims; verdict-only claims
may still be reported with an explicit caveat.

## 3. Evidence

- `load-monitor.jsonl`-style records (schema `formal-p-core-load-monitor-v1`):
  host, boot id, per-P-core usage, busy set, high-CPU processes, cgroup
  delegation state.
- `run_meta.json` per run: commit, config/manifest hashes, limits,
  `cpu_isolation`, `load_check`.

## 4. This repository

- The clean implementation lives on `research/vguide-upstream-reimpl`
  (base = latest upstream CPAchecker main).
- The core-only evaluation harness (`run_core_only.sh`) implements §1–§2;
  the legacy fork keeps the historical implementation for reference.
