# Artifact: From Predicates to Ranking Functions — LLM-Proposed, Engine-Validated Candidates for CEGAR-Based Verification

This artifact accompanies the report *"From Predicates to Ranking Functions: LLM-Proposed,
Engine-Validated Candidates for CEGAR-Based Software Verification."* It contains the source
code (VGuide, a CPAchecker fork), configurations, benchmark lists, recorded experiment
outputs, evaluation scripts, and the report sources, so that every number in the report can
be **checked offline** or **re-run live**.

VGuide augments CPAchecker with an LLM that acts as an *engine-validated candidate provider*:
the LLM proposes a candidate artifact (a loop **predicate** for safety, or a **ranking function**
with a supporting invariant for termination); artifact-specific checks gate use; the verifier
decides. No unvalidated LLM output can change a verdict.

---

## 1. Quick claims this artifact supports

| Report table | Claim | Reproduction |
|---|---|---|
| Table 2 track (i) | Predicate oracle in isolation: `224 -> 253` (+29), peel default `236` (+12), 0 wrong | `python3 reproduce_reachsafety.py` + `recorded-reports/2026-06-22_pure_predicate_decomposition.md` |
| Table 2 track (ii) | svcomp26 portfolio: `486 -> 505` (+19) stock-first; peel `505` at same count, 0 wrong | `python3 reproduce_reachsafety.py` + `recorded-reports/2026-06-23_svcomp26_portfolio_deployment.md` |
| Table 3 (generalisation) | Termination: `80 -> 84` (+4, 0 lost, 0 wrong); NoOverflow +4 | **`python3 reproduce_termination.py`**; overflow in `recorded-reports/` |
| Ablation | source-prior = stock (224), CE context necessary | `recorded-reports/2026-06-17_source_prior_ablation.md` |

Table 3 (termination) reproduces **deterministically and offline** from recorded per-task CSVs.
Table 2 reachability numbers are checked offline from summary CSVs; full per-task re-runs are
documented in `recorded-reports/` (§3.2).

---

## 2. Getting Started (offline, ~10 seconds, no build, no API key)

Requirement: Python 3.8+ only.

```bash
cd artifact
python3 reproduce_termination.py
python3 reproduce_reachsafety.py
```

Expected: both end with `Matches report Table ... YES`.

---

## 3. Step-by-Step (full live re-run)

### 3.1 Requirements
- JDK 21, Apache Ant.
- SMT solvers in `lib/` (bundled in the Zenodo archive).
- SV-COMP benchmarks at `~/sv-benchmarks/c` (`export SV_BENCHMARKS=~/sv-benchmarks/c`), or the
  bundled `sv-benchmarks/c` termination subset for smoke/termination-only runs.
- For the **VGuide (LLM-on) arm**: `export DEEPSEEK_API_KEY=...` (non-deterministic; sound).

### 3.2 Build and run

```bash
ant build-project   # skip if classes/ prebuilt

# Termination Table 3 (lasso route, 300 s)
./scripts/vguided-cegar/run.sh cpa --set termination_scalar --mode termination-stock   --timelimit 300 --parallel 6
./scripts/vguided-cegar/run.sh cpa --set termination_scalar --mode termination-vguide  --timelimit 300 --parallel 6

# ReachSafety Table 2 (see recorded-reports for exact configs)
# Track (i): predicateAnalysis in isolation — docs in 2026-06-22_pure_predicate_decomposition.md
# Track (ii): svcomp26 portfolio ladder — docs in 2026-06-23_svcomp26_portfolio_deployment.md
```

Or run the bundled smoke script (termination offline check + unit tests + 2-task smoke):

```bash
bash artifact/reproduce.sh
```

---

## 4. Structure

```
artifact/
  README.md
  reproduce.sh
  reproduce_termination.py
  reproduce_reachsafety.py
  data/
    termination_scalar*.csv / .list
    reachsafety_*_summary.csv
    logs/{stock,vguide}/*.log
  recorded-reports/
report/          # LNCS sources + main.pdf
```

---

## 5. Provenance, licence, and DOI

- Base tool: CPAchecker (Apache-2.0). VGuide extensions follow the same licence.
- Pin commit: see `PROVENANCE.txt` at the bundle root (Zenodo v2.0.0).
- DOI: https://doi.org/10.5281/zenodo.20745141
- All reported runs: **0 wrong verdicts**.
