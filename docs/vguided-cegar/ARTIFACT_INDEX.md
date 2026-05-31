# Artifact Index

## Scripts

| script | purpose | calls LLM? | cache/replay? |
|--------|---------|:---:|:---:|
| `bootstrap_build_prompt.py` | Build bootstrap prompt from source + assertion | no | — |
| `bootstrap_generate_candidates.py` | Call LLM, validate bootstrap predicates | yes | yes |
| `b5_build_prompt.py` | Build B5 repair prompt with CEGAR context + var table | no | — |
| `b5_repair_from_prompt.py` | Call LLM, parse, validate, dedup repair predicates | yes | yes |
| `b5_multi_round.sh` | Multi-round bootstrap+B5-MR pipeline | yes | — |
| `b5_validate_candidates.py` | Output contract validator (reject SSA/.def_/select/bvshl) | no | — |
| `classify_bootstrap_targets.py` | Static classifier for bootstrap candidate selection | no | — |
| `b5_context_summarizer.py` | Convert CEGAR dump JSON to compact Markdown | no | — |
| `test_b5_validate_candidates.py` | 18 unit tests for validator | no | — |
| `b5_stability_eval.sh` | K=3 repeated run stability evaluation | yes | — |

## Results (tracked summaries)

| file | content |
|------|---------|
| `docs/vguided-cegar/FINAL_TABLES_FOR_REPORT.md` | All result tables |
| `docs/vguided-cegar/ARRAY_PRESENT_SCALAR_LEVEL1_RESULTS.md` | Level 1 results |
| `docs/vguided-cegar/INTEGRATED_RESCUE_SYNTHESIS.md` | Complete synthesis |
| `docs/vguided-cegar/case_studies/*.md` | Individual case studies |
| `results/vguided-cegar/rescue_package/final_rescue_accounting.csv` | Frozen accounting |

## Raw results caveat

Most raw logs and per-run results under `results/vguided-cegar/` are gitignored. Tracked summaries and docs under `docs/vguided-cegar/` are the authoritative artifacts. For reproducing runs, use scripts in `scripts/vguided-cegar/` with the environment documented in `REPRODUCIBILITY_GUIDE.md`.
