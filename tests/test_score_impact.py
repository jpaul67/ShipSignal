"""Points-at-stake / finding-enrichment tests (Feature #1 + #5, v0.6.2)."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from shipsignal import scanner, score_impact
from shipsignal.scoring import score_scan


def _base_metrics(**kw):
    """A fully-scored metrics dict; override fields per test."""
    m = dict(
        has_root_readme=True, root_readme_substantial=True, is_small_repo=False,
        code_count=100, has_agent_file=True, has_root_agent_file=True,
        agent_usefulness_root="actionable", agent_usefulness_nested=None,
        modules_total=4, modules_covered=4, broken_links=0, links_checked=10,
        drift_count=0, fresh_score_sum=4.0, docs_checked=4,
        is_git=True, mcp_present=False, setup_score_frac=1.0, setup_total_weight=16,
    )
    m.update(kw)
    return m


class TestPointsAtStake(unittest.TestCase):
    def test_module_readme_marginal(self):
        # 4 modules, 3 covered → resolving one missing README should raise the score.
        m = _base_metrics(modules_total=4, modules_covered=3)
        finding = {"detector": "module_readme", "path": "src", "severity": "warn"}
        pts = score_impact.points_at_stake(finding, m)
        self.assertGreater(pts, 0)

    def test_setup_check_uses_weight(self):
        # Missing CI (weight 3) out of total 16 → resolving adds 3/16 of the
        # setup category (20 pts) ≈ 3.75 → ~ +2–4 pts on the renormalized total.
        m = _base_metrics(setup_score_frac=13 / 16, setup_total_weight=16)
        finding = {"detector": "setup", "path": ".", "severity": "warn",
                   "resolution": {"setup_check": "ci_config", "setup_weight": 3,
                                  "setup_total_weight": 16}}
        pts = score_impact.points_at_stake(finding, m)
        self.assertGreater(pts, 0)

    def test_informational_findings_are_zero(self):
        m = _base_metrics()
        for det in ("doc_ref_missing", "doc_predates_modules", "doc_written_once"):
            finding = {"detector": det, "path": "README.md", "severity": "warn"}
            self.assertEqual(score_impact.points_at_stake(finding, m), 0.0, det)
            self.assertTrue(score_impact.is_informational(finding), det)

    def test_agent_instructions_big_when_absent(self):
        # No agent file on a non-small repo → resolving is worth the full slot.
        m = _base_metrics(has_agent_file=False, has_root_agent_file=False,
                          agent_usefulness_root=None)
        finding = {"detector": "agent_instructions", "path": ".", "severity": "warn"}
        pts = score_impact.points_at_stake(finding, m)
        self.assertGreater(pts, 5)  # this is the highest-leverage fix on such a repo

    def test_rounds_to_half_and_clamps(self):
        # A no-op resolution (already satisfied) yields 0, never negative.
        m = _base_metrics(modules_total=4, modules_covered=4)
        finding = {"detector": "module_readme", "path": "x", "severity": "warn"}
        self.assertEqual(score_impact.points_at_stake(finding, m), 0.0)

    def test_deltas_not_additive_caveat(self):
        """Renormalization means resolving two findings != sum of their
        individual marginals. This documents *why* the UI labels values ≈."""
        m = _base_metrics(modules_total=4, modules_covered=2)
        f1 = {"detector": "module_readme", "path": "a", "severity": "warn"}
        f2 = {"detector": "module_readme", "path": "b", "severity": "warn"}
        p1 = score_impact.points_at_stake(f1, m)
        # Resolve one, then measure the second from the new baseline.
        m2 = dict(m, modules_covered=3)
        p2_after = score_impact.points_at_stake(f2, m2)
        base, _, _ = score_scan(m)
        both, _, _ = score_scan(dict(m, modules_covered=4))
        # Sum of independent marginals need not equal the true combined delta.
        self.assertGreaterEqual((both - base) + 0.5, min(p1, p2_after))


def _git_init(d: Path):
    env = {"GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@t", "PATH": ""}
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=d, check=True, env=env)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=d, check=True, env=env)
    return env


def _git_commit(d: Path, env: dict, msg: str, date: str):
    e = {**env, "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date, "PATH": ""}
    subprocess.run(["git", "add", "-A"], cwd=d, check=True, env=e)
    subprocess.run(["git", "commit", "-q", "-m", msg], cwd=d, check=True, env=e)


class TestEnrichmentInScan(unittest.TestCase):
    def test_findings_carry_metadata_and_sorted(self):
        d = Path(tempfile.mkdtemp())
        env = _git_init(d)
        (d / "README.md").write_text("# r\n" * 30, encoding="utf-8")
        (d / "src").mkdir()
        (d / "src" / "a.py").write_text("x=1\n", encoding="utf-8")
        _git_commit(d, env, "init", "2026-05-01 12:00:00")
        result = scanner.scan(d, repo_label="t")
        warns = [f for f in result["findings"] if f["severity"] == "warn"]
        self.assertTrue(warns)
        for f in warns:
            self.assertIn("points_at_stake", f)
            self.assertIn("effort", f)
            self.assertIn("area", f)
            self.assertNotIn("resolution", f)  # internal hint stripped
        # Sorted by points-at-stake descending.
        pts = [f["points_at_stake"] for f in warns]
        self.assertEqual(pts, sorted(pts, reverse=True))


class TestLineNumbers(unittest.TestCase):
    def test_broken_link_reports_line(self):
        d = Path(tempfile.mkdtemp())
        env = _git_init(d)
        readme = (
            "# Title\n\nIntro line.\n\nSee [the missing doc](./does-not-exist.md) here.\n"
        )
        (d / "README.md").write_text(readme, encoding="utf-8")
        (d / "main.py").write_text("x=1\n", encoding="utf-8")
        _git_commit(d, env, "init", "2026-05-01 12:00:00")
        result = scanner.scan(d, repo_label="t")
        bl = next((f for f in result["findings"] if f["detector"] == "broken_link"), None)
        self.assertIsNotNone(bl)
        self.assertEqual(bl["line"], 5, "broken link is on line 5")


if __name__ == "__main__":
    unittest.main()
