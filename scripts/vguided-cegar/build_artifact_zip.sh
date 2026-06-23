#!/usr/bin/env bash
# Build Zenodo artifact zip (v2 layout). Run from repository root.
#
#   SV_BENCHMARKS=~/sv-benchmarks/c bash scripts/vguided-cegar/build_artifact_zip.sh
#
# Output: vguide-artifact-v2.zip and vguide-artifact-v2.zip.sha256 at repo root.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO"

BENCH="${SV_BENCHMARKS:-$HOME/sv-benchmarks/c}"
ZIP_NAME="${1:-vguide-artifact-v2.zip}"
STAGING="${TMPDIR:-/tmp}/vguide-artifact-staging-$$"
ROOT="$STAGING/vguide-artifact-v2"
CPA="$ROOT/cpachecker"

cleanup() { rm -rf "$STAGING"; }
trap cleanup EXIT

if [[ ! -d "$BENCH" ]]; then
  echo "error: SV_BENCHMARKS not found at $BENCH" >&2
  exit 1
fi

echo "==> Compile report PDF"
(
  cd report
  pdflatex -interaction=nonstopmode main.tex >/dev/null
  bibtex main >/dev/null 2>&1 || true
  pdflatex -interaction=nonstopmode main.tex >/dev/null
  pdflatex -interaction=nonstopmode main.tex >/dev/null
)
[[ -f report/main.pdf ]] || { echo "error: report/main.pdf missing" >&2; exit 1; }

echo "==> Stage cpachecker tree (git archive)"
mkdir -p "$CPA"
git archive HEAD | tar -x -C "$CPA"

echo "==> Overlay prebuilt binaries, report PDF, and artifact bundle (v2)"
cp -a classes lib "$CPA/"
cp report/main.pdf "$CPA/report/"
rsync -a --delete artifact/ "$CPA/artifact/"

echo "==> Prune non-essential paths from archive"
rm -rf "$CPA/output" "$CPA/archive" "$CPA/slides" "$CPA/.git"
find "$CPA/report" -maxdepth 1 -type f \( -name '*.aux' -o -name '*.log' -o -name '*.out' -o -name '*.blg' -o -name '*.bbl' \) -delete

copy_benchmarks_from_list() {
  local list="$1"
  local dest="$2"
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%%#*}"
    line="$(echo "$line" | xargs)"
    [[ -z "$line" ]] && continue
    rel="${line%% *}"
    dir="$(dirname "$rel")"
    base="$(basename "$rel")"
    stem="${base%.*}"
    mkdir -p "$dest/$dir"
    for ext in c i yml; do
      src="$BENCH/$dir/$stem.$ext"
      if [[ -f "$src" ]]; then
        cp "$src" "$dest/$dir/"
      fi
    done
    if [[ -f "$BENCH/$rel" ]]; then
      cp "$BENCH/$rel" "$dest/$dir/"
    fi
  done < "$list"
}

echo "==> Copy termination benchmark subset"
mkdir -p "$ROOT/sv-benchmarks/c"
copy_benchmarks_from_list "$CPA/docs/vguided-cegar/benchmark_sets/termination_scalar.list" "$ROOT/sv-benchmarks/c"
copy_benchmarks_from_list "$CPA/docs/vguided-cegar/benchmark_sets/termination_smoke_2.list" "$ROOT/sv-benchmarks/c"

echo "==> Bundle root files"
cp "$CPA/artifact/Dockerfile" "$ROOT/Dockerfile"
cp "$CPA/artifact/BUNDLE_README.md" "$ROOT/README.md"

COMMIT="$(git rev-parse HEAD)"
DATE="$(date -u +%Y-%m-%d)"
cat > "$ROOT/PROVENANCE.txt" <<EOF
VGuide reproduction artifact v2.0.0
Built: ${DATE} UTC
Repository: https://github.com/swear01/cpachecker
Commit: ${COMMIT}
Zenodo: https://doi.org/10.5281/zenodo.20745141
Report: cpachecker/report/main.pdf (LNCS)
Benchmarks subset: termination_scalar + termination_smoke_2 from \${SV_BENCHMARKS:-~/sv-benchmarks/c}
EOF

cat > "$ROOT/build_image.sh" <<'EOS'
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
docker build -t vguide-artifact -f Dockerfile .
echo "Built image 'vguide-artifact'. Try: docker run --rm vguide-artifact"
EOS
chmod +x "$ROOT/build_image.sh"

echo "==> Zip (this may take several minutes)"
rm -f "$REPO/$ZIP_NAME"
(
  cd "$STAGING"
  zip -r -q "$REPO/$ZIP_NAME" vguide-artifact-v2
)

(
  cd "$REPO"
  sha256sum "$ZIP_NAME" > "${ZIP_NAME}.sha256"
  echo "${COMMIT}" >> "${ZIP_NAME}.sha256"
)

BYTES="$(wc -c < "$REPO/$ZIP_NAME")"
echo "==> Wrote $REPO/$ZIP_NAME ($BYTES bytes)"
cat "$REPO/${ZIP_NAME}.sha256"

echo "==> Quick verify (unzip + offline reproduce)"
VERIFY="$STAGING/verify"
mkdir -p "$VERIFY"
unzip -q "$REPO/$ZIP_NAME" -d "$VERIFY"
(cd "$VERIFY/vguide-artifact-v2/cpachecker/artifact" && python3 reproduce_termination.py && python3 reproduce_reachsafety.py)

echo "==> Done"
