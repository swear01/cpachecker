# VGuide — Reproduction Artifact (v2.0)

*From Predicates to Ranking Functions: LLM-Proposed, Engine-Validated Candidates for
CEGAR-Based Software Verification.* Ssu-Wei Huang, National Taiwan University.

VGuide augments CPAchecker with an LLM that acts as an **engine-validated candidate provider**:
the LLM proposes a candidate (a loop *predicate* for safety, or a *ranking function* with a
supporting invariant for termination); artifact-specific checks gate use; the verifier decides.
No unvalidated LLM output can change a verdict.

This bundle is **self-contained**: full source, prebuilt `classes/`, runtime `lib/`, termination
benchmark subset, recorded summaries, and scripts. Default offline reproduction needs **no network
and no API key**.

---

## 1. Claims and how to reproduce them

| # | Claim (report) | How | Deterministic? | Key? |
|---|----------------|-----|----------------|------|
| C1 | Termination: **80 → 84** (+4, 0 lost, 0 wrong) — Table 3 | `cpachecker/artifact/reproduce_termination.py` | yes | no |
| C2 | ReachSafety Table 2 summaries (764 tasks, 0 wrong) | `cpachecker/artifact/reproduce_reachsafety.py` | yes | no |
| C3 | Soundness core (14 unit tests) | `cpachecker/artifact/reproduce.sh` step 2 | yes | no |
| C4 | Tool runs on real tasks (FALSE + TRUE smoke) | `reproduce.sh` step 3 | yes | no |
| C5 | Four LLM ranking wins logged | `cpachecker/artifact/data/logs/vguide/*.log` | yes | no |
| C6 | Predicate oracle live re-run | `recorded-reports/` + `run.sh` | varies | yes |

---

## 2. Requirements

- **Docker** (recommended), or **JDK 21** + **Python 3**.
- ~2 GB disk unpacked; ~4 GB for Docker image build.
- Live LLM arm: `DEEPSEEK_API_KEY` (non-deterministic; sound).

---

## 3. Getting Started

**Docker:**
```bash
bash build_image.sh
docker run --rm vguide-artifact
```

**Native:**
```bash
export SV_BENCHMARKS="$PWD/sv-benchmarks/c"
bash cpachecker/artifact/reproduce.sh
```

---

## 4. Structure

```
README.md            this file
PROVENANCE.txt       commit hash, build date, SHA256
Dockerfile
build_image.sh
sv-benchmarks/c/     termination benchmark subset
cpachecker/
  artifact/          reproduce scripts, data/, recorded-reports/
  report/            main.pdf + LNCS sources
  classes/ lib/ config/ scripts/ src/ docs/
```

See `cpachecker/artifact/README.md` for per-table details.

---

## 5. Licence and provenance

- CPAchecker (Apache-2.0); VGuide extensions same licence.
- Zenodo: https://doi.org/10.5281/zenodo.20745141 (version 2.0.0).
- Development repository: https://github.com/swear01/cpachecker
