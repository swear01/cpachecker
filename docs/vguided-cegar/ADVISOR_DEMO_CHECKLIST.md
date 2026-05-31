# Advisor Demo Checklist

## Before Meeting
- [ ] Confirmed commit hash
- [ ] Environment variables set (JAVA, DEEPSEEK_API_KEY, VGUIDE_LLM_REASONING_EFFORT)
- [ ] Dry-run all 3 modes: `bash run_advisor_demo.sh <mode> --dry-run`
- [ ] Real run array-level1: confirms TRUE at 1 ref
- [ ] Open `FINAL_TABLES_FOR_REPORT.md` for reference
- [ ] Open `FIGURE_PIPELINE_ASCII.md` for pipeline diagram

## Demo Order
1. **array-level1** (live, ~30s): TRUE, 1 ref, 0 select/store. Bootstrap-only rescue on array-present benchmark.
2. **context-unlock** (dry-run or live): Show bootstrap unlocks context even when not solved.
3. **scalar-up** (dry-run or tracked summary): Show full rescue pipeline with recorded 3/3 reproduction.

## If Live Demo Fails
- Show dry-run commands as script validation
- Show tracked result tables (`FINAL_TABLES_FOR_REPORT.md`)
- Show predicate set files (`predicate_sets/up.md` etc.)
- Explain LLM/API variance may cause different output
- Fall back to recorded evidence

## Soundness Talking Points
- LLM predicates enter precision only — not trusted as invariants
- CPAchecker proves TRUE/FALSE
- Validator rejects SSA names, .def_*, select/store
- Variable-name table prevents contamination

## Limitations to Mention
- 11 benchmarks total, targeted not general
- No select/store support (Level 1 only)
- No pointer/heap
- Pool exhausted — harder benchmarks needed
- string_concat-noarr needed fixed-predicate replay for stability
