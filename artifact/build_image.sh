#!/usr/bin/env bash
# Build (and optionally save) the reproduction Docker image, from the bundle root.
# Run this on a machine with a working Docker daemon. The bundle layout is:
#   <root>/Dockerfile  cpachecker/  sv-benchmarks/
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."   # bundle root (parent of cpachecker/)

docker build -t vguide-artifact -f cpachecker/artifact/Dockerfile .

echo
echo "Built image 'vguide-artifact'. Try:"
echo "  docker run --rm vguide-artifact"
echo "  docker run --rm -e DEEPSEEK_API_KEY=sk-... vguide-artifact full"
echo
echo "To export the image as a file (e.g. to attach to the Zenodo record):"
echo "  docker save vguide-artifact | gzip > vguide-artifact-image.tar.gz"
