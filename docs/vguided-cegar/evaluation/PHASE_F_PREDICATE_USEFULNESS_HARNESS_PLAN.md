# Phase F：Predicate Usefulness 與 Context-Budget Harness

Status: planned; tracked by GitHub issue [#104](https://github.com/swear01/cpachecker/issues/104).

Phase F is a diagnostic harness track. It does not change the official-label
Stock/Augmented estimand in #100 or the historical replay estimand in #102.
No Phase F artifact may be used to claim that an LLM helped without preserving
the frozen experiment provenance and failure taxonomy.

## 1. Questions

For every LLM call and candidate, the harness must answer:

1. What exact context did the model receive?
2. What source-level predicate did it return?
3. How was it translated, parsed, scoped, validated, and injected?
4. What changed in the next CEGAR refinement and counterexample?
5. Is the observed effect causal, merely novel, ineffective, harmful, or not
   attributable?
6. Was any important context omitted by slicing or a budget cap?

## 2. Work packages

### F0 — audit and freeze

Verify the findings in #105–#109 against the current commit and add a focused
regression test before changing behavior. Historical dumps are evidence for
triage, not proof of current behavior.

### F1 — prompt contract correctness

- one canonical source-variable grammar;
- array reads allowed only as source-level `a[i]` expressions;
- `select`, `store`, heap symbols, bare array identifiers, and SSA names remain
  forbidden in LLM output;
- scalar declarations, arrays, contract keys, and loop-head names are rendered
  without contradictory instructions;
- runtime CEGAR prompts use the SSA-derived contract as the sole variable
  authority; source declaration scanning is only the source-only fallback;
- SSA contract extraction accepts both quoted and unquoted formula-manager
  names and removes scope/version syntax before presenting source names;
- source hints currently cover simple `int` object declarators only: array
  declarators, pointers, function declarations, struct/union fields, comments,
  and string/character literals are excluded deterministically; the first
  declaration in a function body is covered;
- final-prompt tests, not only helper-method tests.

### F2 — structured context contract

The model-facing context is ordered by usefulness, not raw size:

1. target assertion and assertion variables (`__VERIFIER_assert` and `reach_error` must use the same extraction contract);
2. loop-head labels, source locations, guards, updates, and relevant variables;
3. source slice covering declarations, CE path, loop heads, and assertion;
4. source-level array access vocabulary and source-to-verifier mapping rules;
5. authoritative CE facts and loop-head relations;
6. read-only interpolants, native precision, history, and refinement outcomes;
7. explicit unavailable and truncated fields.

Full block formulas, interpolants, raw prompts, and raw responses remain in the
private audit dump. They are not automatically copied into the model prompt.

### F3 — context-size accounting

The request budget is a total budget, not only a source-character cap.

Every API-call row must contain:

- system, user, wrapper, and full-request character/UTF-8-byte counts;
- component counts that reconcile to the rendered request;
- source/CE/history/outcome/native blocks and their truncation metadata;
- prompt hash and response/request hashes;
- provider `usage` as the authoritative token measurement;
- completion-budget and system-prompt reservation;
- deterministic omission order and a list of omitted fields.

Character counts are diagnostics only. The implementation must not claim exact
tokens from a character heuristic. Every source/CE cap must emit retained and
omitted metadata; a file marker or fallback slice must not silently exceed the
remaining aggregate budget. Any provider context-limit response is an explicit
infrastructure result, never a silent truncation or a valid negative LM result.

### F4 — per-task evidence card

For each task with an LLM call, generate a machine-readable candidate table and
a human-readable card containing:

- task/source/config/commit hashes;
- exact prompt path/hash and compact “model saw” summary;
- source/CE/loop/array context retained and omitted;
- raw candidate, translated formula, loop head, role, and profile;
- rejection reason or validation/injection status;
- precision before/after and next CE fingerprint;
- refinement count, verdict, wall/CPU, and failure category.

Tasks without an LLM call receive a coverage card rather than an empty or
missing result.

### F5 — coverage semantics

Distinguish at least:

- `vguide_not_reached`;
- `no_spurious_ce`;
- `llm_not_scheduled`;
- `provider_failure`;
- `analysis_crash`;
- `dump_incomplete`;
- `complete`.

An unexplained missing dump remains a validation failure. A proven no-hook/no-CE
case is an explicit observation and is counted in coverage denominators.

### F6 — causal usefulness

Replay recorded responses with identical commit, config, prompt, request,
response, backend, resources, and task provenance. For selected calls compare:

- all candidates;
- no LLM candidates;
- candidate-group removal;
- remove-one for a small manually selected sample.

Record next-CE fingerprint, loop-head visits, refinement count, precision delta,
verdict, resource use, and failure category. Z3 `Novel`/`Redundant` remains a
semantic-overlap diagnostic, never a causal label.

### F7 — pilot and human review

Use a frozen diagnostic sample before any full prompt/context matrix. Review:

- a direct solve;
- an efficiency-only case;
- an unsolved case with injected candidates;
- an array task;
- a multi-loop task;
- a rejection-heavy task;
- a harmful/lost or infrastructure-contaminated case;
- a no-VGuide/no-spurious task.

The reviewer records one label and evidence for each candidate/batch:

`direct_new_solve`, `speedup_only`, `local_progress`, `injected_no_effect`,
`redundant`, `harmful`, `backend_ceiling`, `not_reached`, or
`infrastructure_failure`.

Causal labels require a clean paired or replay counterfactual. `Novel` alone
cannot receive a causal label.

## 3. Exit gates

- #105–#109 each has confirmed/rejected status based on current code and tests.
- Confirmed correctness/observability defects have regression tests and a
  reviewed PR.
- The context schema, size accounting, truncation policy, and dump schema are
  documented and hashable.
- The pilot produces complete cards and at least one replay counterfactual.
- #100/#102 formal claims remain separate and retain the official expected
  verdict as ground truth.
