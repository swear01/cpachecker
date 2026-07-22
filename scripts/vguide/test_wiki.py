#!/usr/bin/env python3

# This file is part of CPAchecker,
# a tool for configurable software verification:
# https://cpachecker.sosy-lab.org
#
# SPDX-FileCopyrightText: 2026 SSU-WEI HUANG <https://github.com/swear01>
#
# SPDX-License-Identifier: Apache-2.0

import importlib.util
import tempfile
import unittest
from pathlib import Path


SPEC = importlib.util.spec_from_file_location("wiki", Path(__file__).with_name("wiki.py"))
wiki = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(wiki)


class WikiTest(unittest.TestCase):

  def test_check_rejects_broken_link(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      for page in wiki.REQUIRED_PAGES:
        (root / f"{page}.md").write_text(f"# {page}\n", encoding="utf-8")
      (root / "Home.md").write_text("[missing](Does-Not-Exist)\n", encoding="utf-8")
      with self.assertRaisesRegex(ValueError, "Broken local Wiki links"):
        wiki.check(root)

  def test_check_accepts_required_pages(self):
    with tempfile.TemporaryDirectory() as temp:
      root = Path(temp)
      for page in wiki.REQUIRED_PAGES:
        (root / f"{page}.md").write_text(f"# {page}\n", encoding="utf-8")
      wiki.check(root)


if __name__ == "__main__":
  unittest.main()
