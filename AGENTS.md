<!--
This file is part of CPAchecker,
a tool for configurable software verification:
https://cpachecker.sosy-lab.org

SPDX-FileCopyrightText: 2026 SSU-WEI HUANG <https://github.com/swear01>

SPDX-License-Identifier: Apache-2.0
-->

# Repository agent guidance

- Search the local tree and authoritative upstream documentation before changing behavior.
- Keep CPAchecker behavior changes minimal and covered by tests; never add silent fallbacks.
- The GitHub Wiki is the single source of truth for VGuide research narrative, decisions, experiment registry and results.
- Keep only executable reproduction utilities, machine-readable schemas/pins, API/config documentation and developer-critical instructions in this repository.
- Update the Wiki in the same change as a research-design or result change, and record both code and Wiki commit IDs in formal experiment entries.
- Do not duplicate long-form active research documentation under repository `doc/` or `docs/`.
- Before publishing, run the smallest relevant tests, formatter/checkstyle, Wiki link check and a scoped stale-document scan.
