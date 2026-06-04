#!/usr/bin/env python3
"""List git sparse-checkout paths for SV-COMP benchmark profiles.

Profiles (from sosy-lab/sv-benchmarks c/*.set):
  loops-full     — ReachSafety-Loops.set + bitvector-loops (loop 相關完整)
  reachsafety    — all c/ReachSafety-*.set task directories (~80 dirs)
  p1             — NoOverflows-*.set + SoftwareSystems-uthash-ReachSafety (additive)
  recommended    — reachsafety ∪ p1（論文／實驗建議完整包）
"""
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path


def git_show_set(repo: Path, set_path: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), "show", f"HEAD:{set_path}"],
        text=True,
    )


def dirs_from_set_content(text: str) -> set[str]:
    dirs: set[str] = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "/" in line:
            dirs.add(line.split("/", 1)[0])
        elif line.endswith(".yml"):
            dirs.add("verifythis")
    return dirs


def reachsafety_dirs(repo: Path) -> set[str]:
    listing = subprocess.check_output(
        ["git", "-C", str(repo), "ls-tree", "--name-only", "HEAD", "c/"],
        text=True,
    )
    sets = [s for s in listing.splitlines() if s.startswith("c/ReachSafety-") and s.endswith(".set")]
    out: set[str] = set()
    for s in sets:
        out |= dirs_from_set_content(git_show_set(repo, s))
    return out


def loops_full_dirs(repo: Path) -> set[str]:
    """ReachSafety-Loops.set + bitvector-loops (SV-COMP loop 相關完整)."""
    out = dirs_from_set_content(git_show_set(repo, "c/ReachSafety-Loops.set"))
    out.add("bitvector-loops")
    return out


def p1_extra_dirs(repo: Path) -> set[str]:
    """P1 optional: integer overflow + small uthash reachability."""
    out: set[str] = set()
    for set_path in (
        "c/NoOverflows-BitVectors.set",
        "c/NoOverflows-Other.set",
        "c/SoftwareSystems-uthash-ReachSafety.set",
    ):
        out |= dirs_from_set_content(git_show_set(repo, set_path))
    return out


def profile_dirs(profile: str, repo: Path) -> set[str]:
    if profile == "loops-full":
        return loops_full_dirs(repo)
    if profile == "reachsafety":
        return reachsafety_dirs(repo)
    if profile == "p1":
        return p1_extra_dirs(repo)
    if profile == "recommended":
        return reachsafety_dirs(repo) | p1_extra_dirs(repo)
    raise SystemExit(f"unknown profile: {profile}")


def sparse_paths(profile: str, repo: Path) -> list[str]:
    dirs = profile_dirs(profile, repo)
    paths = ["c/properties"]
    for d in sorted(dirs):
        paths.append(f"c/{d}")
    listing = subprocess.check_output(
        ["git", "-C", str(repo), "ls-tree", "--name-only", "HEAD", "c/"],
        text=True,
    )
    for name in listing.splitlines():
        if not name.endswith(".set"):
            continue
        if profile == "loops-full":
            if "ReachSafety" in name or name == "c/Loops.set":
                paths.append(name)
        elif profile == "reachsafety":
            if "ReachSafety" in name:
                paths.append(name)
        elif profile == "p1":
            if "NoOverflows" in name or "uthash-ReachSafety" in name:
                paths.append(name)
        elif profile == "recommended":
            if (
                "ReachSafety" in name
                or "NoOverflows" in name
                or "uthash-ReachSafety" in name
                or name == "c/Loops.set"
            ):
                paths.append(name)
    if profile in ("loops-full", "recommended"):
        paths.append("c/ReachSafety-Loops.set")
        paths.append("c/ReachSafety-BitVectors.set")
        paths.append("c/Loops.set")
    if profile in ("p1", "recommended"):
        paths.append("c/NoOverflows-BitVectors.set")
        paths.append("c/NoOverflows-Other.set")
        paths.append("c/SoftwareSystems-uthash-ReachSafety.set")
    return sorted(set(paths))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--profile",
        choices=("loops-full", "reachsafety", "p1", "recommended"),
        required=True,
    )
    ap.add_argument(
        "--repo",
        type=Path,
        default=Path.home() / "sv-benchmarks",
    )
    ap.add_argument("--print-dirs-only", action="store_true")
    args = ap.parse_args()
    if not (args.repo / ".git").is_dir():
        raise SystemExit(f"Not a git repo: {args.repo}")

    if args.print_dirs_only:
        ds = profile_dirs(args.profile, args.repo)
        for d in sorted(ds):
            print(d)
        print(f"# {len(ds)} task directories", flush=True)
        return

    for p in sparse_paths(args.profile, args.repo):
        print(p)


if __name__ == "__main__":
    main()
