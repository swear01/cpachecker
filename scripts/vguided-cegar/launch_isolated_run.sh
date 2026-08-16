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
WORKTREE_ROOT="${VGUIDE_RUN_WORKTREES:-$HOME/cpachecker-runs}"

[[ $# -ge 2 ]] || { echo "usage: $0 <run-name> <commit> --arm ..." >&2; exit 1; }
RUN_NAME="$1"; shift
COMMIT="$1"; shift

WORKTREE="$WORKTREE_ROOT/$RUN_NAME"
if ! git -C "$WORKTREE" rev-parse --git-dir >/dev/null 2>&1; then
  echo "creating worktree $WORKTREE @ $COMMIT"
  git -C "$REPO_ROOT" worktree add --detach "$WORKTREE" -- "$COMMIT"
fi
cd "$WORKTREE"
# Defensive: refuse to wipe classes/ unless this is really a worktree of REPO_ROOT.
[[ "$(git rev-parse --show-toplevel)" == "$WORKTREE" ]] \
  || { echo "refusing to operate on non-worktree $WORKTREE" >&2; exit 1; }

if [[ ! -f classes/org/sosy_lab/cpachecker/cpa/predicate/vguide/PredicateProposalClient.class ]]; then
  echo "building $WORKTREE"
  rm -rf classes
  BUILD_LOG="$(mktemp /tmp/vguide-build-XXXXXX.log)"
  JAVA_HOME="${JAVA_HOME:-$HOME/jdk21}" PATH="$JAVA_HOME/bin:$PATH" ant build >"$BUILD_LOG" 2>&1 \
    || { echo "build failed; see $BUILD_LOG" >&2; exit 1; }
  rm -f "$BUILD_LOG"
fi

echo "launching $RUN_NAME from $WORKTREE (commit $(git rev-parse --short HEAD))"
RUN_LOG="$WORKTREE/run.log"
nohup bash "$WORKTREE/scripts/vguided-cegar/run_core_only.sh" "$@" >"$RUN_LOG" 2>&1 &
echo "pid $! — run log: $RUN_LOG; worktree: $WORKTREE"
