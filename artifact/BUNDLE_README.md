# VGuide — Reproduction Artifact

*From Predicates to Ranking Functions: LLM-Proposed, SMT-Certified Candidates for
CEGAR-Based Software Verification.* Ssu-Wei Huang, National Taiwan University.

VGuide augments CPAchecker with an LLM that acts as a **verified-candidate provider**: the
LLM proposes a candidate (a loop *predicate* for safety, or a *ranking function* with a
supporting invariant for termination), a sound SMT check certifies it, and only then is it
used. No unvalidated LLM output can change a verdict. This artifact lets you reproduce the
results in the report and inspect/rebuild/run the tool.

This bundle is **self-contained**: it ships the full source, the prebuilt classes, all
runtime solver jars, the benchmark subset, recorded experiment outputs, and scripts. The
default reproduction needs **no network and no API key**.

---

## 1. Claims and how to reproduce them

| # | Claim (report) | How | Deterministic? | Key? |
|---|----------------|-----|----------------|------|
| C1 | **Termination ranking oracle: 80 → 84 (+4, 0 lost, 0 wrong)** — Table 3 | `reproduce.sh` step 0 regenerates it from recorded per-task verdicts | yes | no |
| C2 | Soundness core: the 4-check verifier and parser are correct (14 tests) | `reproduce.sh` step 2 (JUnit) | yes | no |
| C3 | The tool really runs and is sound on FALSE tasks | `reproduce.sh` step 3 runs CPAchecker on a non-terminating + a terminating task → FALSE + TRUE | yes | no |
| C4 | Predicate oracle: Loops +37/+7, combined +19, 0 wrong (Tables 1–2) | recorded in `cpachecker/artifact/recorded-reports/`; re-run live per §4 | runs vary | yes |
| C5 | The +4 wins are LLM-proposed, SMT-certified ranking functions | `cpachecker/artifact/data/logs/vguide/*.log` contain four `verified LLM ranking function ...` lines | yes | no |

## 2. Requirements

- **Docker** (recommended), or a host with **JDK 21** and **Python 3**.
- ~2 GB disk for the unpacked bundle; ~4 GB if you build the Docker image.
- The **live VGuide arm only** (C4 and the optional step 4) needs `DEEPSEEK_API_KEY` and
  network access; it is **non-deterministic** (model sampling), though every verdict it
  produces is SMT-certified and therefore sound.

## 3. Getting Started (smoke test, ~2–5 min)

**With Docker:**
```bash
bash build_image.sh                 # docker build -t vguide-artifact ...
docker run --rm vguide-artifact     # runs reproduce.sh: C1 + C2 + C3
```

**Native (no Docker):**
```bash
export SV_BENCHMARKS="$PWD/sv-benchmarks/c"
bash cpachecker/artifact/reproduce.sh
```

Either way you should see: Table 3 regenerated (`Matches report Table 3 ... YES`),
`OK (14 tests)`, and a real CPAchecker run returning `FALSE` then `TRUE`.

## 4. Step-by-Step (full reproduction)

- **C1 (Table 3), C2, C3, C5** are produced by `reproduce.sh` (steps 0/2/3) above; C5 is
  visible in `cpachecker/artifact/data/logs/vguide/`.
- **Live VGuide termination arm** (re-derive C1 from scratch instead of from records):
  ```bash
  docker run --rm -e DEEPSEEK_API_KEY=sk-... vguide-artifact full
  # or native: DEEPSEEK_API_KEY=sk-... bash cpachecker/artifact/reproduce.sh full
  ```
  This re-runs `termination_scalar` (146 tasks, 300 s) with the LLM oracle; compare the
  produced summary CSV against `cpachecker/artifact/data/termination_scalar_300_vguide.csv`.
  Counts may differ by ±1–2 (LLM non-determinism); verdicts remain sound.
- **C4 (predicate results)** are documented in `cpachecker/artifact/recorded-reports/` with
  the exact configurations; re-run with the reachability/overflow sets and the
  `predicateAnalysis`/`svcomp26` VGuide configurations.

## 5. Determinism and the LLM dependency (please read)

The headline **offline reproduction (C1–C3, C5) is fully deterministic and needs no API
key**: it regenerates the reported numbers from recorded per-task outputs and re-runs the
LLM-free stock baseline and unit tests. The **live LLM arm** (C4 and step 4) calls an
external API, needs a key, and is non-deterministic; we therefore ship the recorded LLM-arm
outputs and per-task logs (including the four `verified LLM ranking function` lines) as the
evidence for the claims. A network-isolated competition tool would need a local/distilled
model or a pre-computed candidate cache (discussed in the report).

## 6. Structure

```
README.md            this file
Dockerfile           self-contained image (prebuilt classes + jars; no build/network needed)
build_image.sh       docker build + (optional) docker save
cpachecker/          the VGuide CPAchecker fork
  artifact/          reproduce.sh, reproduce_termination.py, data/ (CSVs + per-task logs),
                     recorded-reports/, detailed README.md, zenodo_upload.py
  report/            LNCS report sources + main.pdf
  src/ lib/ classes/ config/ scripts/ docs/    source, runtime jars, prebuilt classes, configs
sv-benchmarks/c/     the termination benchmark subset (crafted / crafted-lit / numeric)
```
See `cpachecker/artifact/README.md` for the detailed per-table reproduction notes.

## 7. Licence and provenance

- Base tool: CPAchecker (Apache-2.0); VGuide extensions follow the same licence.
- Built on CPAchecker commit recorded in `cpachecker/artifact/COMMIT_BASE.txt`.
- **Note:** the Docker *image* was not built in the preparation environment (no Docker
  daemon there); the underlying build, unit tests, and reproduction were all verified
  natively, and the Dockerfile mirrors that verified build.
