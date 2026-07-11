# PDR／KI-PDR oracle-capacity matrix（2026-07-11）

## Scope

Ordinary `PredicateToKInductionInvariantConverter`提出的 individual candidates在 frozen
12-task exact-BV gate為0/12。這份 final gate只排除尚未測過的 consumer差異：

1. 同一loop head的 reference predicates以
   `CandidateInvariantCombination.singleLocationConjunction(...)`整組驗證；
2. property-directed KI-PDR；
3. direct `PdrAlgorithm`的root candidates與 location-scoped predicate abstraction vocabulary。

Matrix不呼叫LLM。Reference predicates不會被直接假設為真：root必須由PDR確認；vocabulary只供
`PredicateAbstractionManager.computeAbstraction(...)`使用。

## Implementation

- `bmc.kinduction.reuse.pred.conjunction=true`：converter依location合併候選；
- `pdr.oraclePredicatePrecisionFile`：direct PDR test-only oracle input；
- `pdr.oracleMode=ROOT|CONJUNCTIVE_ROOT|ABSTRACTION|BOTH`；
- abstraction mode若未啟用 `ALLSAT_BASED_PREDICATE_ABSTRACTION`會以invalid configuration
  fail closed；
- PDR statistics記錄seed數、confirmed oracle roots，以及target是否在oracle root確認後成立；
- harness記錄consumer、mode、config hash與per-task attribution columns。

## Frozen matrix

Primary semantics：native C bit-vector、MathSAT、60秒、每process一個analysis；catalog、source/YAML
hash與predicate maps沿用 ordinary gate。

| Arm | Consumer | Oracle consumption | Solved/12 | Oracle delta | Wrong |
|---|---|---|---:|---:|---:|
| K0 | ordinary k-induction | none | 0 | — | 0 |
| K1 | ordinary k-induction | separate | 0 | 0 | 0 |
| K2 | ordinary k-induction | per-location conjunction | 0 | 0 | 0 |
| KP0 | property-directed KI-PDR | none | 0 | — | 0 |
| KP1 | property-directed KI-PDR | separate | 0 | 0 | 0 |
| KP2 | property-directed KI-PDR | conjunction | 0 | 0 | 0 |
| KL0/KL1 | late KI-PDR | none/conjunction | 0 / 0 | 0 | 0 |
| P0 | direct PDR defaults | none | 0 | — | 0 |
| P1 | direct PDR + abstraction lifting | none | 0 | — | 0 |
| P2 | P1 | conjunctive root | 0 | 0 | 0 |
| P3 | P1 | abstraction vocabulary | 0 | 0 | 0 |
| P4 | P1 | conjunctive root + vocabulary | 0 | 0 | 0 |

All matrix arms returned0/12 solved,0 wrong。P3/P4 statistics confirm that every oracle map seeded
its1–6 reference predicates into PDR abstraction, but no oracle root was confirmed and no target was
proved。This is not a loader/config failure：the vocabulary was consumed, yet it produced no target delta。

## Verdict

**STOP A.** Per-location conjunction、property-directed KI-PDR、late KI-PDR、direct PDR roots與
direct PDR abstraction all have zero oracle-attributed target wins。The current CPAchecker nonlinear
consumer line is therefore falsified on this frozen gate；do not implement CTI-local LLM helpers。

PDR stock P0/P1 also solved0/12, so there is no evidence for deterministic PDR routing on this target
set。The next bounded direction is predicate usefulness gating：reject candidate batches whose local
resource-risk signature predicts abstraction pollution, while keeping verdict authority in stock CEGAR。

## Decision rule

- GO CTI helper only with at least2/12 oracle-attributed target wins at60秒（或1個60秒加另一個300秒）、
  0 wrong、controls clean與proof dependency；
- PDR stock wins但oracle無delta：只考慮deterministic routing；
- all oracle delta 0：停止 current-consumer nonlinear candidate line，轉
  convergence-aware shadow refinement。

## Raw output

- `output/vguide/experiments/nla_oracle_matrix_k2_bv_60s/`
- `output/vguide/experiments/nla_oracle_matrix_kp2_bv_60s/`
- `output/vguide/experiments/nla_oracle_matrix_kp1_bv_60s/`
- `output/vguide/experiments/nla_oracle_matrix_kl1_bv_60s/`
- `output/vguide/experiments/nla_oracle_matrix_p0_bv_60s/`
- `output/vguide/experiments/nla_oracle_matrix_p1_bv_60s/`
- `output/vguide/experiments/nla_oracle_matrix_p2_bv_60s/`
- `output/vguide/experiments/nla_oracle_matrix_p3_bv_60s/`
- `output/vguide/experiments/nla_oracle_matrix_p4_bv_60s/`
