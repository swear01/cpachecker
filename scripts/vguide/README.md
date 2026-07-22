<!--
This file is part of CPAchecker,
a tool for configurable software verification:
https://cpachecker.sosy-lab.org

SPDX-FileCopyrightText: 2026 SSU-WEI HUANG <https://github.com/swear01>

SPDX-License-Identifier: Apache-2.0
-->

# VGuide execution utilities

The active research design, decisions and results live in the [GitHub Wiki](https://github.com/swear01/cpachecker/wiki). This directory contains only executable reproduction utilities and pinned machine-readable inputs.

## Stock Stage A baseline

```bash
env -u VGUIDE_LLM -u DEEPSEEK_API_KEY -u OPENAI_API_KEY \
  JAVA_HOME=/path/to/jdk-21 \
  scripts/vguide/run-stock-baseline.sh \
  /path/to/cpachecker-stock /path/to/sv-benchmarks \
  /path/to/benchmark-definitions /path/to/benchexec /path/to/output
```

The runner refuses revision drift, a dirty stock checkout, LLM-related environment variables, an unexpected P-core topology, or VGuide in the stock configuration closure.

`config/predicateAnalysis-vguide.properties` keeps augmentation disabled unless a run explicitly supplies `vguide.enable=true`, `vguide.endpoint`, and `vguide.model`.

## Result manifests

```bash
scripts/vguide/baseline.py summarize \
  --result /path/to/result.xml.bz2 \
  --output-dir /path/to/summary
```

## Wiki integrity

```bash
scripts/vguide/wiki.py check /path/to/cpachecker.wiki
scripts/vguide/wiki.py backup \
  https://github.com/swear01/cpachecker.wiki.git cpachecker-wiki.bundle
```
