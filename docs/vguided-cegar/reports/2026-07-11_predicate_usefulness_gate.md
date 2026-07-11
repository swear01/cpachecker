# Predicate usefulness gate（2026-07-11）

## Motivation

Final PDR/KI-PDR oracle matrix all-zero後，nonlinear candidate line停止。回到已觀察的可解瓶頸：
precision-only predicates不影響soundness，但可能把Boolean abstraction與all-sat query放大到
timeout。

## Frozen first-call rule

只使用注入前已知資訊：

```text
reject this precision batch and disable later LLM calls
iff loopHeadVisits <= 8
and at least 2 unique validated predicate formulas contain bvmul
```

這不是family/name router，也不看expected verdict或final runtime。Rejected formulas不進precision；
standard interpolation照常執行，verdict仍由PredicateCPA決定（Tier R）。

Gate為opt-in，`vguide.enablePredicateUsefulnessGate=false`是general default；paired experiment以
`vguide-experiment-usefulness-gate-{off,on}.properties`顯式控制。

## Offline preregistration

Rule只在`full764_pure_vguide_skip1_nopeel`上選定，之後threshold固定。Task-level replay使用
「reject→stock result、accept→VGuide result」作capacity upper bound：

| Arm | Original solved | Gate simulation | Original lost | Gate lost | Sacrificed wins |
|---|---:|---:|---:|---:|---:|
| old schedule | 253 | 255 | 6 | 3 | 1 (`bhmr2007`) |
| skip-#1, peel=0 | 252 | **259** | 7 | **0** | **0** |
| pinned peel=4 | 236 | 248 | 23 | 10 | 1 (`bhmr2007`) |

在selection arm，19 tasks被reject；7個全是stock-solved/VGuide-lost，沒有VGuide-only win被reject。
Simulated PAR-2由407.36降至402.08秒。Cross-schedule不是independent benchmark holdout，但固定rule
在另外兩個arms仍改善net solved，顯示signature不只重述單一task name。

Reproduce one arm：

```bash
python3 scripts/vguided-cegar/analyze_predicate_usefulness_gate.py \
  --stock-summary output/vguide/experiments/full764_pure_stock/loops_reachsafety_unreach_summary.csv \
  --vguide-summary output/vguide/experiments/full764_pure_vguide_skip1_nopeel/loops_reachsafety_unreach_summary.csv \
  --vguide-logs output/vguide/experiments/full764_pure_vguide_skip1_nopeel/logs \
  --timelimit 300
```

## TDD implementation

`PredicateUsefulnessGateTest`先建立RED cases：short peel + two multiplicative predicates必須reject；
duplicate formula只算一次；loop visits 9必須accept。Runtime bridge在validation後、precision injection
前做決策；reject後保留standard refinement並停止本analysis的後續LLM rounds。

## Fresh targeted confirmation

Frozen manifest：`benchmark_sets/predicate_usefulness_loss7.list`，包含selection arm的7個losses；
300秒、parallel4、fresh online responses、`every_n_or_interval`、peel=0。

結果：**7/7 TRUE，0 wrong，7/7 logs明確記錄 usefulness rejection，0 precision injection**。

| Task | Historical stock | Historical VGuide | Fresh gate | Gate wall |
|---|---:|---:|---:|---:|
| `divbin2_unwindbound5` | TRUE | UNKNOWN | TRUE | 37.728s |
| `divbin2_valuebound20` | TRUE | UNKNOWN | TRUE | 59.386s |
| `hard-u_valuebound2` | TRUE | UNKNOWN | TRUE | 8.394s |
| `hard-u_valuebound10` | TRUE | UNKNOWN | TRUE | 10.946s |
| `hard-u_valuebound20` | TRUE | UNKNOWN | TRUE | 11.574s |
| `hard-u_valuebound50` | TRUE | UNKNOWN | TRUE | 21.919s |
| `hard-u_valuebound100` | TRUE | UNKNOWN | TRUE | 49.608s |

這是fresh model response與runtime confirmation，不是單純CSV simulation。每題first-call response仍
產生2–4個unique multiplicative predicates，gate全部拒絕；standard interpolation恢復stock-like
convergence。接著以`bhmr2007`與`nested9`兩個VGuide-only wins作preservation control。

Preservation結果：**2/2 TRUE，0 wrong，兩題都未被gate拒絕且確實完成precision injection**。
`bhmr2007`在loopHeadVisits=10注入9個local predicates、17.690秒證明；`nested9`在visits=35
注入18個local predicates、33.191秒證明。Combined targeted result因此是：

> **7/7 historical losses recovered + 2/2 direct-win controls preserved，9/9 correct，0 wrong。**

這已達成「消除至少50%已知losses」的runtime gate，但仍不是held-out/full-portfolio證據。
Rule來自同一764-task corpus，下一步必須凍結rule後做family-held-out或完整764重跑，不能再調
visits=8／count=2 thresholds。

## Opt-in configuration and dump audit

Default-off patch後，以獨立configs在相同commit/environment做60秒live smoke：

| Arm | Config | Solved/7 | Wrong |
|---|---|---:|---:|
| Gate off | `vguide-experiment-usefulness-gate-off.properties` | 0 | 0 |
| Gate on | `vguide-experiment-usefulness-gate-on.properties` | **7** | 0 |

這兩個live arms沒有paired responses，所以只驗證wiring，不作causal full-set claim。Schema-v3 dump
確認gate-on每題的trigger row保存完整validated predicates、`precision_injected=[]`、canonical hashes、
SAFE/BUG profiles與rule version；後續refinements明確記錄
`llm_skip_reason=predicate_usefulness_gate`。Gate-off rows則`enabled=false`且正常注入。

Raw output：`output/vguide/experiments/predicate_usefulness_loss7_gate_current/`。
Control output：`output/vguide/experiments/predicate_usefulness_win2_gate_current/`。
Opt-in smoke outputs：

- `output/vguide/experiments/predicate_usefulness_loss7_gate_off_optin_smoke/`
- `output/vguide/experiments/predicate_usefulness_loss7_gate_on_optin_smoke/`
- `output/vguide/analysis_dumps/usefulness_gate_{off,on}_smoke_20260711/`
