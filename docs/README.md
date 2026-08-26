# 研究文件（本 fork）

## AI agent 結構化入口（agent-rules）

專案層級文件，給 AI agent／新進者快速上手（規範見 [`../AGENTS.md`](../AGENTS.md)）：

| 文件 | 用途 |
|------|------|
| [overview.md](overview.md) | 專案是什麼、domain 術語、外部資源 |
| [structure.md](structure.md) | 目錄結構、模組邊界、搜尋排除規則 |
| [notes.md](notes.md) | Gotchas 與決策背景 |
| [plan.md](plan.md) | 現行計劃與里程碑 |
| [roadmap.md](roadmap.md) | 長期 backlog |

## VGuide 研究文件

研究設計的 source of truth 是 [GitHub Wiki](https://github.com/swear01/cpachecker/wiki)。
實驗 protocol、報告、log 與 artifact 在本機
`/home/swear01/cpachecker-experiments/`；本 repo 的 `docs/vguided-cegar/` 只保留
scripts/config 直接引用的 benchmark、predicate 與 evaluation 資料。

Benchmark 入口：[`vguided-cegar/evaluation/STANDARD_BENCHMARK_SUITE.md`](vguided-cegar/evaluation/STANDARD_BENCHMARK_SUITE.md)。

CPAchecker 官方文件：[`doc/`](../doc/)。
