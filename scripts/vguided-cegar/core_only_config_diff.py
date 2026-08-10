#!/usr/bin/env python3
"""Config-diff validator for the core-only evaluation (Issue #2).

Resolves two CPAchecker config files (following ``#include``) into
normalized key=value dicts and fails on any difference outside the
augmentation allowlist. Exit 0 means the two arms differ only by the
allowed augmentation (vguide.* options and the useVocabularyGuide flag).

Usage:
  core_only_config_diff.py --stock-config config/predicateAnalysis.properties \
      --augmented-config config/predicateAnalysis-vguide.properties
"""

import argparse
import hashlib
import sys
from pathlib import Path

ALLOWED_PREFIXES = ("vguide.",)
ALLOWED_KEYS = {
    # passed via --option at runtime; listed explicitly so a config that
    # sets it inline is still accepted
    "cpa.predicate.refinement.useVocabularyGuide",
}


def resolve_config(path: Path) -> dict:
    """Parse a .properties file, expanding #include in document order (last wins).

    Include targets are resolved like CPAchecker does: relative to the
    including file's directory first, then relative to the top-level
    config's directory, then relative to the current working directory.
    """
    out = {}
    _parse_inline(path, path.resolve().parent, set(), out)
    return out


def _parse_inline(path: Path, top_dir: Path, seen: set, out: dict) -> None:
    p = path.resolve()
    if p in seen:
        return
    seen.add(p)
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#include"):
            inc = line[len("#include") :].strip()
            for base in (p.parent, top_dir, Path.cwd()):
                candidate = (base / inc).resolve()
                if candidate.is_file():
                    _parse_inline(candidate, top_dir, seen, out)
                    break
            continue
        if line.startswith("#") or line.startswith("!"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip()


def config_sha256(path: Path) -> str:
    """Hash of the top-level config file (provenance; not the include tree)."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def diff_configs(stock: Path, augmented: Path):
    """Return [(key, stock_value, augmented_value, allowed)] sorted by key."""
    a = resolve_config(stock)
    b = resolve_config(augmented)
    diffs = []
    for key in sorted(set(a) | set(b)):
        va, vb = a.get(key), b.get(key)
        if va != vb:
            allowed = key.startswith(ALLOWED_PREFIXES) or key in ALLOWED_KEYS
            diffs.append((key, va, vb, allowed))
    return diffs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stock-config", required=True, type=Path)
    ap.add_argument("--augmented-config", required=True, type=Path)
    args = ap.parse_args()

    diffs = diff_configs(args.stock_config, args.augmented_config)
    forbidden = [d for d in diffs if not d[3]]
    for key, va, vb, allowed in diffs:
        tag = "ALLOWED  " if allowed else "FORBIDDEN"
        print(f"{tag} {key}: {va!r} -> {vb!r}")
    if forbidden:
        print(
            "CONFIG DIFF REJECTED: differences outside the augmentation allowlist",
            file=sys.stderr,
        )
        return 1
    print("CONFIG DIFF OK: arms differ only by the augmentation")
    return 0


if __name__ == "__main__":
    sys.exit(main())
