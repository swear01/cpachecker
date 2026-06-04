# Local Development Environment

本機實驗環境：**資料在 `$HOME`**，不依賴 FMPA2。操作入口：`scripts/vguided-cegar/run.sh`（見 [RUN_EXPERIMENTS.md](RUN_EXPERIMENTS.md)）。

## Quick Start

```bash
cd /home/swear01/cpachecker
chmod +x scripts/vguided-cegar/run.sh

./scripts/vguided-cegar/run.sh bench-setup
./scripts/vguided-cegar/run.sh bench-reclassify   # 與官方 sv-benchmarks 對齊的 classifier + lists

export DEEPSEEK_API_KEY="..."
export JAVA="$HOME/jdk-21/bin/java"          # Java 21+，見下方
export PATH="$HOME/.local/ant/bin:$(dirname "$JAVA"):$PATH"
export SV_BENCHMARKS="$HOME/sv-benchmarks-vguide/c"

ant build-project
./scripts/vguided-cegar/run.sh cpa --set sample
```

## 目錄（`$HOME`）

| 項目 | 路徑 |
|------|------|
| SV-COMP benchmarks | **`~/sv-benchmarks-vguide/c/`** = `SV_BENCHMARKS`；sparse 非整庫 |
| 下載 profile | **`reachsafety`**：全部 `ReachSafety-*.set`（~2GB）；**`loops-full`**：ReachSafety-Loops + bitvector-loops |
| Apache Ant | `~/.local/ant/bin/ant`（**1.10.14**；apt 未安裝） |
| JDK 21（請自裝） | 建議 `~/jdk-21/`（Temurin 等）；或 `export JAVA=...` |
| CPA 輸出 | `cpachecker/output/vguide/` |

### Benchmark 安裝

```bash
./scripts/vguided-cegar/run.sh bench-setup      # sparse 下載 + 初步 list
./scripts/vguided-cegar/run.sh bench-reclassify  # 推薦：discover→classify→list（官方對齊）
```

Sparse 目錄（12 類）：`loop-acceleration`, `loop-invgen`, `loop-lit`, `loops`, `loop-crafted`, `loop-invariants`, `loop-new`, `loops-crafted-1`, `loop-industry-pattern`, `loop-simple`, `loop-zilu`, `loop-floats-scientific-comp`, `bitvector-loops`。  
**不含**整個 `c/array-*`、`c/heap-*` 等（VGuide scalar 主路徑不需要）。  
Manifest：`docs/vguided-cegar/benchmark_sets/*.list`。

## Java 21

CPAchecker 需 **Java 21+**。系統 `/usr/bin/java` 常為 OpenJDK 8，**不可用**。

安裝範例（擇一）：

- 解壓 Temurin 21 至 `~/jdk-21/`，`export JAVA=~/jdk-21/bin/java`
- `sudo apt install openjdk-21-jdk` 後 `export JAVA=/usr/lib/jvm/java-21-openjdk-amd64/bin/java`

驗證：`$JAVA -version` → 21.x；`bin/cpachecker --version`。

## Apache Ant

| 項目 | 值 |
|------|-----|
| 執行檔 | `~/.local/ant/bin/ant` |
| apt | **未安裝** |

```bash
export PATH="$HOME/.local/ant/bin:$PATH"
ant build-project
```

## API

| 項目 | 說明 |
|------|------|
| `DEEPSEEK_API_KEY` | VGuide / 離線品質必填 |
| Rate limit | **~500/min** → 批次預設平行，見 [RUN_EXPERIMENTS.md](RUN_EXPERIMENTS.md) |

## 平行度（預設）

| 命令 | 預設平行 |
|------|----------|
| `run.sh cpa` | `PARALLEL=8` |
| `run.sh llm-quality` | `16` |

`PARALLEL=1` 可改循序。

## 常見錯誤

**Java too old** → 設定 `JAVA` 為 21+。

**Benchmark not found** → `run.sh bench-setup` 或 `export SV_BENCHMARKS=$HOME/sv-benchmarks-vguide/c`。

**ant: command not found** → `PATH` 加上 `~/.local/ant/bin`。

## 相關文件

- [RUN_EXPERIMENTS.md](RUN_EXPERIMENTS.md)
- [STANDARD_BENCHMARK_SUITE.md](STANDARD_BENCHMARK_SUITE.md)
- [README.md](README.md)
