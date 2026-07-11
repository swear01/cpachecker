# VGuide-NLA Oracle-Capacity Smoke（2026-07-11）

**Harness status：COMPLETE。Capacity gate：BV backend RED；exact NIA/Z3 backend RED。**

**Scope clarification：**這份RED只適用 ordinary incremental k-induction consumer。後續final
matrix補測真正的 per-location `CandidateInvariantCombination`、KI-PDR與 direct PDR；見
[`2026-07-11_pdr_oracle_capacity_matrix.md`](2026-07-11_pdr_oracle_capacity_matrix.md)。

## 1. 問題

在修改 BMC core 或寫 LLM polynomial-basis hook 之前，先問：給 CPAchecker 從 benchmark
loop assertions 提取的 reference polynomial invariants，現有 bounded base check +
`KInductionProver` 能否證明原本 UNKNOWN 的 nonlinear tasks？

## 2. TDD implementation

新增 `scripts/vguided-cegar/oracle_capacity_harness.py` 與 10 個 `unittest`。測試先於
implementation 寫入，第一輪因 module 不存在而 RED；後續每個 converter-arity、result parsing、
candidate shape 與 infrastructure-failure case 都先加入 failing test 再實作。

Harness 提供：

- frozen JSON catalog + source/YAML SHA-256 validation；
- `atomic`、`supporting-first`、`conjunction` candidate shapes；
- integer-theory predicate map rendering；
- existing `bmc.kinduction.predicatePrecisionFile` import；
- exact-BV `INT2BV` conversion，或 CPAchecker nonlinear-integer encoding；
- stock/oracle sequential runs、per-task logs/CSV、comparison、binary/config/spec provenance；
- parse/config/solver/Java infrastructure failures 與 scientific UNKNOWN 分離；
- `run.sh nla-oracle` single entry point。

Catalog：`evaluation/nla_oracle_smoke_candidates.json`。Manifest：
`benchmark_sets/nla_oracle_smoke.list`。12 題涵蓋 cubic、nested/binary division、square root、
geometric series、multi-branch polynomial、GCD/LCM、product 與 finite difference；全部 expected
TRUE，既有 2026-06-12 predicate-stock batch皆為 UNKNOWN。Reference candidates直接來自各題
loop 中的 `__VERIFIER_assert` 關係，再轉成 converter-compatible binary SMT-LIB arithmetic。

## 3. Current-commit build

```text
CPAchecker 4.2.2-2125-g963c5743bf+
cpachecker.jar SHA-256:
c35183a7ee33c690298795a6f4c10fb3eae5231c51de61c0e1ed9d7c3b30b9da
```

Build command：

```bash
PATH="$HOME/.local/ant/bin:$PATH" ant -q build-project
```

## 4. Bit-vector/MathSAT capacity result

Command：

```bash
./scripts/vguided-cegar/run.sh nla-oracle run \
  --output output/vguide/experiments/nla_oracle_capacity_smoke_current \
  --arm both --timelimit 60
```

Result：

| Arm | Solved | UNKNOWN | Wrong |
|-----|-------:|--------:|------:|
| stock k-induction | 0/12 | 12 | 0 |
| oracle candidate | **0/12** | 12 | 0 |

All 12 predicate maps parsed and were imported（oracle `Number of invariants proposed` = 1–6,
depending on candidate count and number of loop heads）。11 oracle tasks spent essentially the full
budget or returned UNKNOWN；`knuth` returned fast UNKNOWN。No oracle direct win；gate target was ≥4/12。

The simplest single-invariant task `ps2-ll` was repeated at 300 s：

```bash
./scripts/vguided-cegar/run.sh nla-oracle run \
  --output output/vguide/experiments/nla_oracle_capacity_ps2_300_current \
  --arm oracle --timelimit 300 --task ps2-ll
```

It remained UNKNOWN：297.682 s total，the one reference invariant was imported，and nonlinear
bit-vector induction consumed the budget。This is strong evidence that the current exact-BV/MathSAT
proof backend—not candidate discovery—is the immediate bottleneck。

## 5. Candidate-dependency shapes

On `sqrt1-ll` at 60 s：

| Shape | Imported candidates | Result |
|-------|--------------------:|--------|
| `supporting-first` | 3 | UNKNOWN / timeout |
| `conjunction` | 1 | UNKNOWN / timeout |

Thus the observed failure is not explained merely by atomic candidate ordering/dependency。

## 6. Exact nonlinear-integer runtime repair

CPAchecker already has an exact integer-with-wraparound/range-constraints encoding：

```text
cpa.predicate.encodeBitvectorAs=INTEGER
cpa.predicate.useNonlinearArithmeticForIntAsBv=true
solver.nonLinearArithmetic=USE
cpa.predicate.addRangeConstraintsForNondet=true
solver.solver=Z3
```

The harness exposes it as `--encoding nia`. The bundled Z3 4.15.4 could not start on this
Ubuntu 22.04 / GLIBC 2.35 host：

```text
Invalid configuration: libz3.so requires GLIBC_2.38
```

The harness returned exit code 2 and marked `invalid_configuration`; it did **not** count this as a
scientific UNKNOWN or silently switch solvers。

The exact matching Z3 release was then built from the official `z3-4.15.4` tag at commit
`745087e237e669d709ae35694728a0c479e572b3` on this host, with Java bindings, and installed under：

```text
~/.local/opt/z3-4.15.4/
~/.local/bin/z3 -> ../opt/z3-4.15.4/bin/z3
```

CPAchecker's ignored runtime `libz3.so` and `libz3java.so` now point to the matching user-local
runtime。The CLI and JNI bridge were built from the official tag；the core `libz3.so` is the exact
4.15.4.0 `manylinux_2_17` wheel build because the host GCC 11 source build crashes in JNI string
conversion when several JavaSMT native solvers share one JVM。The incompatible originals are retained under
`~/.local/opt/z3-4.15.4/cpachecker-incompatible-runtime/`。The prior pip-wheel CLI is retained as
`~/.local/bin/z3-4.16.0-python-wheel`。

An Ivy dependency refresh (`ant build-project` / `ant tests`) replaces files under
`lib/java/runtime/` and can overwrite these ignored symlinks。After such a refresh, restore the
user-local links and confirm the CPAchecker log reports Z3 4.15.4.0 before an NIA run。

Verification：

```text
Z3 version 4.15.4 - 64 bit
Using predicate analysis with Z3 4.15.4.0.
```

Installed runtime SHA-256：

```text
z3              b6ae8336dd1be42b8c2a1641cb263f92fbe48aa8367524a227a8b29f3091eb9e
libz3.so         56d9977b9276bcb8cda9973a14058fcaa9f3bfee14ed57408b9faacd76d4d8f3
libz3java.so     0a8da2ebce50fb73b5719cf21680ed2f36c4dec73341fc598bd5cea958e12f0a
```

## 7. Exact nonlinear-integer/Z3 capacity result

The frozen gate was rerun unchanged except for selecting the planned `nia` encoding：

```bash
./scripts/vguided-cegar/run.sh nla-oracle run \
  --output output/vguide/experiments/nla_oracle_capacity_nia_z3_smoke_current \
  --arm both --timelimit 60 --encoding nia
```

| Arm | Solved | UNKNOWN | Wrong |
|-----|-------:|--------:|------:|
| stock k-induction | 0/12 | 12 | 0 |
| oracle candidate | **0/12** | 12 | 0 |

All oracle maps parsed and proposed 1–6 candidates。Eleven tasks in each arm exhausted essentially
the full budget；`knuth` returned fast UNKNOWN。No configuration、candidate parse、solver or Java
infrastructure failure was detected。

## 8. Verdict and breakpoint decision

- **第一部分（oracle-capacity harness）已完成。** TDD、catalog、three shapes、runner、provenance、
  comparison與實跑皆完成。
- **Current exact-BV backend fails the ≥4/12 gate：0/12。** 不應開始 dynamic BMC/LLM hook。
- **Exact nonlinear-integer/Z3 backend也 fails the gate：0/12。** ABI blocker已排除，結果不再是
  infrastructure uncertainty。
- **依預先註冊斷點 STOP ordinary k-induction VGuide-NLA。** 正確/reference polynomial
  candidates無法使該consumer產生direct win；不實作deterministic/LLM basis arms。後續只加入
  bounded、test-only PDR oracle loader完成final consumer gate，沒有加入LLM BMC hook。
- 現行 fallback改為 **convergence-aware predicate usefulness gating**。

## 9. Raw output

- `output/vguide/experiments/nla_oracle_capacity_smoke_current/`
- `output/vguide/experiments/nla_oracle_capacity_ps2_300_current/`
- `output/vguide/experiments/nla_oracle_capacity_shapes_current/`
- `output/vguide/experiments/nla_oracle_capacity_nia_z3_probe_current/`
- `output/vguide/experiments/nla_oracle_capacity_nia_z3_runtime_check_current/`
- `output/vguide/experiments/nla_oracle_capacity_nia_z3_smoke_current/`
