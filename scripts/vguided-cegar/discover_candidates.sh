#!/usr/bin/env bash
# Discover existing loop benchmarks suitable for V-guided evaluation.
# Excludes arrays, heap, recursion, concurrency, floating-point.
# Usage: ./discover_candidates.sh > candidates.txt
set -euo pipefail

REPO="$(dirname "$0")/../.."
SV_COMP="${SV_COMP_ROOT:-/home/swear01/sv-benchmarks-vguided}"

echo "# Candidates from CPAchecker test programs"
find "$REPO/test/programs" -name "*.c" | grep -Ei "diamond|loop|invariant|crafted|mod|parity|linear|relation" | while read f; do
  name=$(basename "$f" .c)
  echo "test|$name|$f"
done

echo "# Candidates from SV-COMP"
for cat in loop-acceleration loop-invariants loop-crafted loops; do
  for f in "$SV_COMP/c/$cat"/*.{c,i}; do
    [ -f "$f" ] || continue
    name=$(basename "$f")
    echo "$cat|$name|$f"
  done
done
