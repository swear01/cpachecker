#!/usr/bin/env python3

# This file is part of CPAchecker,
# a tool for configurable software verification:
# https://cpachecker.sosy-lab.org
#
# SPDX-FileCopyrightText: 2026 SSU-WEI HUANG <https://github.com/swear01>
#
# SPDX-License-Identifier: Apache-2.0

import argparse
import hashlib
import re
import subprocess
import tempfile
from pathlib import Path


REQUIRED_PAGES = {
    "Home",
    "Architecture",
    "Soundness-and-Trust-Boundary",
    "Hard-Case-Dataset",
    "Baseline-Protocol",
    "Context-Schemas",
    "Predicate-Lifecycle",
    "Multi-Agent-Design",
    "Model-Comparison",
    "Experiment-Registry",
    "Results",
    "Decision-Records",
    "Reproduction",
    "Historical-and-Stopped-Directions",
}
WIKI_LINK = re.compile(r"\[[^]]+\]\(([^)]+)\)")


def check(wiki_dir):
  root = Path(wiki_dir).resolve()
  pages = {path.stem for path in root.glob("*.md")}
  missing = sorted(REQUIRED_PAGES - pages)
  if missing:
    raise ValueError("Missing required Wiki pages: " + ", ".join(missing))
  broken = []
  for page in sorted(root.glob("*.md")):
    for link in WIKI_LINK.findall(page.read_text(encoding="utf-8")):
      if "://" in link or link.startswith("#"):
        continue
      target = link.split("#", 1)[0].removesuffix(".md")
      if target and target not in pages:
        broken.append(f"{page.name}: {link}")
  if broken:
    raise ValueError("Broken local Wiki links:\n" + "\n".join(broken))
  print(f"Wiki check passed: {len(pages)} Markdown files")


def backup(url, output):
  output_path = Path(output).resolve()
  output_path.parent.mkdir(parents=True, exist_ok=True)
  with tempfile.TemporaryDirectory(prefix="vguide-wiki-") as temp:
    mirror = Path(temp) / "wiki.git"
    subprocess.run(["git", "clone", "--mirror", url, str(mirror)], check=True)
    subprocess.run(
        ["git", "-C", str(mirror), "bundle", "create", str(output_path), "--all"], check=True
    )
  digest = hashlib.sha256(output_path.read_bytes()).hexdigest()
  output_path.with_suffix(output_path.suffix + ".sha256").write_text(
      f"{digest}  {output_path.name}\n", encoding="utf-8"
  )
  print(digest)


def main():
  parser = argparse.ArgumentParser()
  subparsers = parser.add_subparsers(dest="command", required=True)
  check_parser = subparsers.add_parser("check")
  check_parser.add_argument("wiki_dir")
  backup_parser = subparsers.add_parser("backup")
  backup_parser.add_argument("wiki_url")
  backup_parser.add_argument("output")
  args = parser.parse_args()
  if args.command == "check":
    check(args.wiki_dir)
  else:
    backup(args.wiki_url, args.output)


if __name__ == "__main__":
  main()
