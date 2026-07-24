"""Guard: the package version must be declared identically in pyproject.toml and
shipsignal/__init__.py.

These are two separate, hand-maintained strings, and they have desynced before
(commit 21de140; and again at v0.11.0, where pyproject stayed 0.10.0 while
__init__ was bumped to 0.11.0 — which then failed the release workflow's
tag/version check and blocked the PyPI publish). release.yml catches this at tag
time; this test catches it at PR time, before a mismatched tag is ever cut."""
import tomllib
import unittest
from pathlib import Path

import shipsignal

_ROOT = Path(__file__).resolve().parents[1]


class VersionSyncTest(unittest.TestCase):
    def test_pyproject_matches_dunder_version(self):
        with (_ROOT / "pyproject.toml").open("rb") as f:
            pyproject_version = tomllib.load(f)["project"]["version"]
        self.assertEqual(
            pyproject_version,
            shipsignal.__version__,
            "pyproject.toml [project].version and shipsignal.__version__ have "
            "drifted; bump BOTH when releasing (see PLAN.md's version-bump rule).",
        )
