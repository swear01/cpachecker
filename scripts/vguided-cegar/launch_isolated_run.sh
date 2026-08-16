#!/usr/bin/env bash
# Launch a core-only run in an isolated git worktree so the main repo stays
# editable during execution (NFS-shared classes/ corrupted running JVMs before;
# see docs/notes.md). Usage:
#
#   launch_isolated_run.sh <run-name> <commit> --arm stock|augmented \
#       --timelimit S --out <dir> [extra run_core_only args...]
#
# Env: SV_BENCHMARKS, DEEPSEEK_API_KEY, VGUIDE_LLM_API_URL, DEEPSEEK_MODEL,
#      VGUIDE_LLM_THINKING, VGUIDE_LLM_REASONING_EFFORT, VGUIDE_LLM_JSON_MODE...
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
WORKTREE_ROOT="${VGUIDE_RUN_WORKTREES:-/home/swear01/cpachecker-runs}"

[[ $# -ge 2 ]] || { echo "usage: $0 <run-name> <commit> --arm ..." >&2; exit 1; }
RUN_NAME="$1"; shift
COMMIT="$1"; shift

WORKTREE="$WORKTREE_ROOT/$RUN_NAME"
if [[ ! -d "$WORKTREE/.git" ]]; then
  echo "creating worktree $WORKTREE @ $COMMIT"
  git -C "$REPO_ROOT" worktree add --detach "$WORKTREE" "$COMMIT"
fi
cd "$WORKTREE"

if [[ ! -f classes/org/sosy_lab/cpachecker/cpa/predicate/vguide/PredicateProposalClient.class ]]; then
  echo "building $WORKTREE"
  rm -rf classes
  JAVA_HOME="${JAVA_HOME:-$HOME/jdk21}" PATH="$JAVA_HOME/bin:$PATH" ant build >/tmp/vguide-build-${RUN_NAME}.log 2>&1 \
    || { echo "build failed; see /tmp/vguide-build-${RUN_NAME}.log" >&2; exit 1; }
fi

echo "launching $RUN_NAME from $WORKTREE (commit $(git rev-parse --short HEAD))"
nohup bash "$WORKTREE/scripts/vguided-cegar/run_core_only.sh" "$@" >/dev/null 2>&1 &
echo "pid $! — logs under the --out dir; worktree: $WORKTREE"
