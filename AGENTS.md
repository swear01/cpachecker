## 實驗與研究文件指路（所有 agent 必讀）

- **實驗輸出、log、研究文件、過往紀錄、論文**：不在本 repo。
  全部在 `/home/swear01/cpachecker-experiments/`（README 是總索引；
  遷移清單：GitHub Issue #55）。
- **研究設計與 decisions**：GitHub Wiki（source of truth）。
- **正式 run 的 CPU isolation 是強制要求**：taskset `0,2,4,6,8,10,12,14`
  （8 P-cores、無 SMT/E-core）、run 前 load check、三機 pool
  （valkyrie/athena/cthulhu）擇 `idle_ready`；完整 protocol：
  `/home/swear01/cpachecker-experiments/docs/vguided-cegar/EXPERIMENT_PROTOCOL.md`
  或新 branch `research/vguide-upstream-reimpl` 的 `docs/EXPERIMENT_PROTOCOL.md`。
- repo 的 `docs/vguided-cegar/` 只保留被 scripts/config 引用的資料
  （`benchmark_sets/`、`predicate_sets/`、`evaluation/`）；研究文件已搬走。
- 實驗紀錄摘要（2026-08-11 core-only 448-run、12 verdict disputes）：Issue #54/#55。

# BEGIN agents_rule-base
# Agent Rules

## Core Rules

- Default to autonomous execution: make and carry out the least-risky reasonable decisions for routine, reversible, in-scope work without asking.
- Own the requested outcome end to end. Do not stop after discovery, planning, partial implementation, or a progress update; continue through verification and safe in-scope fixes until complete or genuinely blocked.
- Necessary supporting changes to code, tests, fixtures, configuration, generated artifacts, and documentation are in scope. Unrelated refactors, cleanup, and features are not.
- Ask only for a concrete, material problem—missing input, a user-owned decision, or an unrequested destructive, irreversible, paid, or external action; never skip a required step for lack of approval—ask instead.
- Before asking, diagnose the issue and complete all safe, reversible, equivalent, in-scope work. If no concrete material problem exists, choose a reasonable default and continue.
- Do not ask merely because the work crosses files, functions, tests, fixtures, configuration, dependencies, or tools. Do not ask again for an action the user already explicitly requested or authorized.
- For substantive tasks, inspect relevant local files and instructions before modifying them; use authoritative docs or web sources when current or external facts matter. Explicit, trivial, unambiguous edits may proceed directly.
- If authoritative guidance is unavailable, use verified local evidence when sufficient; never invent code, paths, functions, APIs, behavior, or verification results.
- Equivalent tools and implementation methods may be substituted without asking when they preserve behavior, security, data safety, verification strength, target, and material cost. Otherwise report the issue and the decision needed.
- Never return dummy results, skip required verification, hide failures, or silently downgrade the requested scope.
- Retry an operation once when the failure appears transient; otherwise diagnose it and continue with safe, equivalent, in-scope alternatives when available.
- Match existing style, names, and patterns; keep changes minimal and add no dependencies or comments unless necessary for the requested result.
- Change requested behavior directly; do not add unrequested compatibility options.
- Before merging a PR, trigger a GitHub bot review with `github-pr-review-loop`; merge once it passes on the latest head. Local review is supplementary.

## Completion

- Run the smallest relevant verification that can prove the outcome, including live behavior when applicable; fix safe failures caused by the change.
- Never claim an unrun check passed. Report the concrete problem, safe alternatives tried, and exact decision needed when genuinely blocked.

## Memory and Documentation

- After substantive work, check for new durable, verified knowledge; use `shared-memory` only when there is useful knowledge to record.
- Update active docs only when durable behavior, API, CLI, or configuration changes; scan only affected documentation.
- Refresh and query-check QMD only when memory changes. Use `agents_rule archive` for intentional documentation archiving and `git mv` for tracked moves.
- Report files changed, documentation status, verification performed, and remaining risks or blockers.
# END agents_rule-base

## Project Docs

- Overview: [docs/overview.md](docs/overview.md)
- Structure: [docs/structure.md](docs/structure.md)
- Notes: [docs/notes.md](docs/notes.md)
- Plan: [docs/plan.md](docs/plan.md)
- Roadmap: [docs/roadmap.md](docs/roadmap.md)
