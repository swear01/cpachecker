# Artifact: From Predicates to Ranking Functions — LLM-Proposed, SMT-Certified Candidates for CEGAR-Based Verification

This artifact accompanies the report *"From Predicates to Ranking Functions: LLM-Proposed,
SMT-Certified Candidates for CEGAR-Based Software Verification."* It contains the source
code (VGuide, a CPAchecker fork), configurations, benchmark lists, recorded experiment
outputs, evaluation scripts, and the report sources, so that every number in the report can
be **regenerated offline** and the experiments can be **re-run live**.

VGuide augments CPAchecker with an LLM that acts as a *verified-candidate provider*: the LLM
proposes a candidate artifact (a loop **predicate** for safety, or a **ranking function**
with a supporting invariant for termination), a sound SMT check certifies it, and only then
is it used. No unvalidated LLM output can change a verdict.

---

## 1. Quick claims this artifact supports

| Report table | Claim | Reproduction |
|---|---|---|
| Table 2 (top) | Predicate oracle: Loops ReachSafety `225 -> 262` (+37), svcomp26 `486 -> 493` (+7), 0 wrong | recorded in `recorded-reports/` (see §4); live re-run §3.2 |
| Table 2 (bottom) | Combined competition-grade: ReachSafety +15, NoOverflow +4 (+19), 0 wrong | `recorded-reports/2026-06-16_combined_300s_classA.md`; live re-run §3.2 |
| Ablation | source-prior = stock (225), CE context necessary | `recorded-reports/2026-06-17_source_prior_ablation.md` |
| **Table 3** | **Ranking oracle: termination `80 -> 84` (+4), 0 lost, 0 wrong** | **`python3 reproduce_termination.py` (offline, <10 s)** |

The termination result (the report's new contribution, Table 3) reproduces **deterministically
and offline** from recorded outputs. The predicate results (Tables 1–2) were produced earlier;
their recorded run reports are bundled, and they can be re-run live (§3.2).

---

## 2. Getting Started (offline, ~10 seconds, no build, no API key)

Requirement: Python 3.8+ only.

```bash
cd artifact
python3 reproduce_termination.py
```

Expected output (regenerated from the recorded 300 s runs in `data/`):

```
termination_scalar: 146 tasks (125 terminating / 21 non-terminating)
  lasso analysis (stock)           solved= 80  TRUE= 69  FALSE= 11  wrong=0
    + VGuide ranking oracle        solved= 84  TRUE= 73  FALSE= 11  wrong=0
  NET +4   new wins=4   lost=0   wrong=0
    +WIN  AliasDarteFeautrierGonnord-SAS2010-speedpldi4 ...
Matches report Table 3 (stock 80 -> VGuide 84, +4, 0 lost, 0 wrong): YES
```

This re-derives Table 3 directly from the recorded per-task verdicts; no network, solver, or
CPAchecker invocation is involved.

---

## 3. Step-by-Step (full live re-run)

### 3.1 Requirements
- JDK 21, Apache Ant (the build needs `ant`; if not installed, a standalone install works:
  `apache-ant-1.10.x/bin/ant`).
- SMT solvers bundled with CPAchecker (SMTInterpol, MathSAT5, Z3) — included in `lib/`.
- The SV-COMP benchmark repository at `~/sv-benchmarks/c` (`export SV_BENCHMARKS=~/sv-benchmarks/c`).
- For the **VGuide (LLM-on) arm only**: `export DEEPSEEK_API_KEY=...` (live external API).
  The LLM arm is **non-deterministic** (model sampling, network), so exact counts may vary by
  ±1–2; the verdicts it produces are always SMT-certified, hence sound.

### 3.2 Build and run

```bash
# build (classes/ is ahead of cpachecker.jar on the classpath, so no `ant jar` needed)
ANT_HOME=/path/to/apache-ant PATH=$ANT_HOME/bin:$PATH ant build-project

# unit tests for the soundness core (verifier + parser), no API key needed
#   -> "OK (14 tests)"
#   (see report §3; classes/ + lib/{,java/runtime,java/test}/*.jar on the classpath)

# Termination (Table 3): stock vs VGuide, lasso route in isolation, 300 s
export SV_BENCHMARKS=~/sv-benchmarks/c
./scripts/vguided-cegar/run.sh cpa --set termination_scalar --mode termination-stock   --timelimit 300 --parallel 6
export DEEPSEEK_API_KEY=...   # only for the VGuide arm
./scripts/vguided-cegar/run.sh cpa --set termination_scalar --mode termination-vguide  --timelimit 300 --parallel 6

# compare (same logic as reproduce_termination.py, against the freshly produced CSVs)
python3 artifact/reproduce_termination.py    # after copying the new summary CSVs into data/
```

The predicate results (Tables 1–2) are reproduced analogously with the reachability/overflow
benchmark sets and the `svcomp26`/`predicateAnalysis` VGuide configurations; see
`recorded-reports/` for the exact configurations and the recorded numbers.

---

## 4. Structure

```
artifact/
  README.md                      # this file
  reproduce_termination.py       # offline regeneration of Table 3
  data/
    termination_scalar.list      # the 146-task benchmark set (paths + expected verdicts)
    termination_scalar_300_stock.csv   # recorded stock run (per-task verdict + wall time)
    termination_scalar_300_vguide.csv  # recorded VGuide run
    logs/{stock,vguide}/*.log    # per-task CPAchecker output (evidence). The four VGuide
                                 #   wins each log a "verified LLM ranking function ..." line,
                                 #   i.e. the SMT-certified ranking function the LLM proposed.
  recorded-reports/              # recorded run reports for all tables (copied from docs/)
report/                          # the LNCS report sources (main.tex, references.bib, llncs.cls) + main.pdf
src/.../termination/lasso_analysis/vguide/   # ranking-function oracle (Java source + unit tests)
src/.../cpa/predicate/vguide/                # predicate oracle (Java source)
config/                          # VGuide configurations (incl. config/vguide-experiment-termination.properties)
scripts/vguided-cegar/           # run.sh, compare scripts
docs/vguided-cegar/              # design docs (TERMINATION_RANKING_HOOK_PLAN.md, reports/)
```

Key source files (report §3):
- Ranking-function oracle: `RankingFunctionVerifier.java` (4-condition SMT check),
  `RankingTermParser.java`, `RankingRelationFactory.java`, `LlmRankingFunctionProvider.java`,
  plus the fallback wiring in `LassoAnalysis.java`. Unit tests: `RankingFunctionVerifierTest`,
  `RankingTermParserTest` (14 tests).
- Predicate oracle: `cpa/predicate/vguide/` (context pack, three-tier validation, client).

---

## 5. Provenance, licence, and DOI

- Base tool: CPAchecker (Apache-2.0). VGuide extensions follow the same licence.
- Pin the exact commit you submit (e.g., `git rev-parse HEAD`) in the report and below:
  `commit: <fill in the submitted commit hash>`.
- Soundness note: VGuide is strictly *Tier S* — the LLM only proposes; an SMT check certifies;
  the verifier decides. All reported runs have **0 wrong verdicts**.

### Packaging for a DOI (final submission step)
1. From the repository root, create a clean snapshot, e.g.
   `git archive --format=zip -o vguide-artifact.zip HEAD` and add `artifact/data/`,
   `report/main.pdf`, and (optionally) the larger raw logs.
2. Upload the archive to **Zenodo** (or Figshare); it mints a **DOI**.
3. Put the DOI in the report and submit the DOI as the artifact deliverable.
