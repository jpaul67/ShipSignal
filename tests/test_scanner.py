"""Smoke + unit tests (stdlib unittest — no third-party dep)."""
import unittest
from pathlib import Path

from bellwether import scanner
from bellwether.modules import _parse_pnpm_packages, _code_dirs
from bellwether.detectors import _drifted, _skip_link
from bellwether.scoring import score_scan, grade_for

REPO = Path(__file__).resolve().parent.parent


class TestSelfScan(unittest.TestCase):
    def test_scans_self(self):
        result = scanner.scan(REPO, repo_label="bellwether")
        self.assertIn("score", result)
        self.assertTrue(0 <= result["score"] <= 100)
        self.assertTrue(any(m["path"] == "." for m in result["modules"]))
        # the package dir should be detected as a module
        self.assertTrue(any(m["path"] == "bellwether" for m in result["modules"]))


class TestPnpmParse(unittest.TestCase):
    def test_parse(self):
        text = "packages:\n  - 'packages/*'\n  - docs\n  - '!**/test/**'\nother: 1\n"
        self.assertEqual(_parse_pnpm_packages(text), ["packages/*", "docs", "!**/test/**"])


class TestDrift(unittest.TestCase):
    def test_module_doc_drift(self):
        self.assertTrue(_drifted("2026-01-01", "2026-08-01", gentle=False))   # >180d
        self.assertFalse(_drifted("2026-05-01", "2026-06-01", gentle=False))  # 31d

    def test_agent_files_are_gentle(self):
        # ~8 months stale: a problem for a module README, fine for an agent file
        self.assertTrue(_drifted("2026-01-01", "2026-09-01", gentle=False))
        self.assertFalse(_drifted("2026-01-01", "2026-09-01", gentle=True))


class TestSkipLink(unittest.TestCase):
    def test_guards(self):
        for s in ["https://x.com", "#anchor", "/abs/path", "C:\\Users\\x", "mailto:a@b.c"]:
            self.assertTrue(_skip_link(s), s)
        self.assertFalse(_skip_link("../src/foo.js"))


class TestScoring(unittest.TestCase):
    def test_small_repo_agent_is_na(self):
        m = dict(has_root_readme=True, root_readme_substantial=True, is_small_repo=True,
                 code_count=5, has_agent_file=False, has_root_agent_file=False,
                 modules_total=1, modules_covered=1, broken_links=0, drift_count=0,
                 is_git=True, mcp_present=False)
        score, grade, cats = score_scan(m)
        agent = next(c for c in cats if c.id == "agent_instructions")
        self.assertEqual(agent.status, "n/a")
        self.assertEqual(score, 100)  # not punished for missing agent file

    def test_grade_bands(self):
        self.assertEqual(grade_for(95), "A")
        self.assertEqual(grade_for(27), "F")


if __name__ == "__main__":
    unittest.main()
