"""Squash-attribution recovery tests (Package D): _recover_from_pr_data unit
cases + a compute_impact integration test proving the --pr-data param flows
through and the default (no-flag) path is unchanged.

The premise, calibrated against real repos: GitHub-native squash PRESERVES
co-authors, so the DROP case (recoverable) is specific to pipelines that bypass
that aggregation (jest/Meta-sync). These tests model both DROP and RETAIN.
"""
import argparse
import contextlib
import io
import os
import subprocess
import tempfile
import unittest
from datetime import date
from pathlib import Path

from shipsignal import cli, impact, report
from shipsignal.impact import Commit
from shipsignal.prdata import PRAuthor, PRData, PRRecord

FIXTURES = Path(__file__).resolve().parent / "fixtures"

CLAUDE = PRAuthor("Claude", "noreply@anthropic.com")
HUMAN = PRAuthor("Jane", "jane@example.com")


def _c(sha="x", subject="", trailers=None):
    return Commit(sha, date(2026, 1, 1), "dev@ex.com", subject, trailers or [], [], 0, 0)


def _pd(*records):
    return PRData(records=list(records))


class TestRecoverFromPRData(unittest.TestCase):
    def test_sha_match_recovers_dropped_trailer(self):
        # DROP: a squash commit with no local trailer, matched by merge SHA.
        commits = [_c("s1", "feat: a (#101)"), _c("s2", "chore: b")]
        pd = _pd(PRRecord(101, "s1", None, [CLAUDE]))
        rec = impact._recover_from_pr_data(commits, pd, measured_ai=0)
        self.assertEqual(rec["newly_attributed"], 1)
        self.assertEqual(rec["measured_ai_commits"], 0)
        self.assertEqual(rec["recovered_ai_commits"], 1)
        self.assertEqual(rec["recovered_tools"], ["Claude"])
        self.assertEqual(rec["squash_commits"], 1)
        self.assertEqual(rec["squash_matched"], 1)
        self.assertEqual(rec["coverage"], 1.0)
        self.assertGreater(rec["recovered_share"], rec["measured_share"])

    def test_subject_fallback_when_sha_differs(self):
        # rebase-merge / mirror SHA: merge_oid doesn't match, (#NNN) subject does.
        commits = [_c("localsha", "fix: y (#102)")]
        pd = _pd(PRRecord(102, "a-different-sha", None, [CLAUDE]))
        rec = impact._recover_from_pr_data(commits, pd, measured_ai=0)
        self.assertEqual(rec["newly_attributed"], 1)
        self.assertEqual(rec["recovered_tools"], ["Claude"])

    def test_retain_case_not_double_counted(self):
        # RETAIN: trailer already present locally -> measured, never re-added.
        commits = [_c("s3", "feat: z (#103)",
                      ["Co-authored-by: Claude <noreply@anthropic.com>"])]
        self.assertTrue(commits[0].ai_authored)
        pd = _pd(PRRecord(103, "s3", None, [CLAUDE]))
        rec = impact._recover_from_pr_data(commits, pd, measured_ai=1)
        self.assertEqual(rec["newly_attributed"], 0)
        self.assertEqual(rec["recovered_ai_commits"], 1)
        self.assertEqual(rec["measured_share"], rec["recovered_share"])

    def test_human_only_pr_not_recovered(self):
        commits = [_c("s4", "feat: h (#104)")]
        pd = _pd(PRRecord(104, "s4", None, [HUMAN]))
        rec = impact._recover_from_pr_data(commits, pd, measured_ai=0)
        self.assertEqual(rec["newly_attributed"], 0)
        self.assertEqual(rec["recovered_tools"], [])

    def test_partial_export_shows_low_coverage(self):
        # 4 squash commits at risk, export covers only 2 -> coverage 0.5, not a
        # falsely confident number.
        commits = [_c("a", "x (#1)"), _c("b", "y (#2)"),
                   _c("c", "z (#3)"), _c("d", "w (#4)")]
        pd = _pd(PRRecord(1, "a", None, [CLAUDE]), PRRecord(2, "b", None, [CLAUDE]))
        rec = impact._recover_from_pr_data(commits, pd, measured_ai=0)
        self.assertEqual(rec["squash_commits"], 4)
        self.assertEqual(rec["squash_matched"], 2)
        self.assertEqual(rec["coverage"], 0.5)
        self.assertEqual(rec["newly_attributed"], 2)

    def test_no_squash_commits_coverage_none(self):
        commits = [_c("a", "plain subject, no PR number")]
        rec = impact._recover_from_pr_data(commits, _pd(), measured_ai=0)
        self.assertIsNone(rec["coverage"])
        self.assertEqual(rec["squash_commits"], 0)
        self.assertEqual(rec["newly_attributed"], 0)


def _git(d, *args, env=None):
    subprocess.run(["git", *args], cwd=d, check=True, env=env,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class TestComputeImpactIntegration(unittest.TestCase):
    def _build_repo(self, td: Path) -> dict:
        d = "2026-01-01T00:00:00"
        env = {**os.environ,
               "GIT_AUTHOR_NAME": "Dev", "GIT_AUTHOR_EMAIL": "dev@ex.com",
               "GIT_COMMITTER_NAME": "Dev", "GIT_COMMITTER_EMAIL": "dev@ex.com",
               "GIT_AUTHOR_DATE": d, "GIT_COMMITTER_DATE": d}
        _git(td, "init", "-q", "-b", "main", env=env)
        _git(td, "config", "commit.gpgsign", "false", env=env)
        shas = {}
        # A DROP squash commit (no trailer) + plain commits — no local AI signal.
        for i, subj in enumerate(["feat: base", "feat: recovered work (#101)",
                                   "chore: tidy", "docs: notes"]):
            (td / f"f{i}.txt").write_text(str(i), encoding="utf-8")
            _git(td, "add", "-A", env=env)
            _git(td, "commit", "-q", "-m", subj, env=env)
            out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=td, check=True,
                                 capture_output=True, text=True, env=env)
            shas[subj] = out.stdout.strip()
        return shas

    def test_recovery_block_added_and_default_unchanged(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            shas = self._build_repo(root)
            squash_sha = shas["feat: recovered work (#101)"]
            pd = _pd(PRRecord(101, squash_sha, None, [CLAUDE]))

            with_pr = impact.compute_impact(root, pr_data=pd)
            without = impact.compute_impact(root)

            # Recovery present only with the flag; measured headline identical.
            self.assertIn("recovery", with_pr["adoption"])
            self.assertNotIn("recovery", without["adoption"])
            self.assertEqual(with_pr["adoption"]["ai_coauthor_share"],
                             without["adoption"]["ai_coauthor_share"])

            rec = with_pr["adoption"]["recovery"]
            self.assertEqual(rec["measured_ai_commits"], 0)  # nothing locally
            self.assertGreaterEqual(rec["newly_attributed"], 1)  # #101 recovered
            self.assertGreater(rec["recovered_share"], rec["measured_share"])
            self.assertEqual(rec["recovered_tools"], ["Claude"])

    def test_recovery_renders_in_all_formats(self):
        import html.parser
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            shas = self._build_repo(root)
            pd = _pd(PRRecord(101, shas["feat: recovered work (#101)"], None, [CLAUDE]))
            res = impact.compute_impact(root, pr_data=pd)

            cli_txt = report.render_impact(res)
            self.assertIn("recovered", cli_txt.lower())
            self.assertIn("coverage", cli_txt.lower())

            md = report.render_impact_markdown(res)
            self.assertIn("Recovery:", md)
            self.assertNotIn("%%", md)  # regression guard: r_pct already carries '%'

            h = report.render_impact_html(res)
            html.parser.HTMLParser().feed(h)  # must be well-formed
            self.assertIn("recovered", h.lower())

    def test_recipe_shown_when_squash_and_no_pr_data(self):
        # The self-advertising recipe is the discovery mechanism: squash suspected,
        # no --pr-data -> print the export + re-run lines, but claim no recovery.
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._build_repo(root)
            res = impact.compute_impact(root, squash_override=True)
            txt = report.render_impact(res)
            self.assertIn("gh pr list", txt)
            self.assertIn("--pr-data pr.json", txt)
            self.assertNotIn("recovered", txt.lower())


class TestPctFormatting(unittest.TestCase):
    def test_sub_one_percent_keeps_precision(self):
        # Regression (found calibrating jest): a real 0.2% recovered figure must
        # not round to a contradictory "0%" beside an above-None band.
        self.assertEqual(report._pct(0.002), "0.2%")
        self.assertEqual(report._pct(0.0), "0%")
        self.assertEqual(report._pct(0.38), "38%")
        self.assertEqual(report._pct(0.974), "97%")


class TestZeroNetwork(unittest.TestCase):
    """The absolute promise: ShipSignal makes zero network calls, even for squash
    recovery — the user runs the gh export, ShipSignal only reads the local file.
    Enforced by an import scan so a future edit can't quietly add a network dep."""

    NETWORK_MODULES = {"urllib", "http", "socket", "ssl", "ftplib", "smtplib",
                       "telnetlib", "requests", "httpx", "aiohttp"}

    def _imported_top_level_modules(self, module) -> set[str]:
        import ast
        src = Path(module.__file__).read_text(encoding="utf-8")
        mods: set[str] = set()
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Import):
                mods.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                mods.add(node.module.split(".")[0])
        return mods

    def test_prdata_imports_no_network(self):
        from shipsignal import prdata
        offenders = self._imported_top_level_modules(prdata) & self.NETWORK_MODULES
        self.assertEqual(offenders, set(),
                         f"prdata.py must not import network modules: {offenders}")

    def test_impact_imports_no_network(self):
        offenders = self._imported_top_level_modules(impact) & self.NETWORK_MODULES
        self.assertEqual(offenders, set(),
                         f"impact.py must not import network modules: {offenders}")


class TestCliLoadPRData(unittest.TestCase):
    def test_no_flag_returns_none_none(self):
        pd, err = cli._load_pr_data(argparse.Namespace(pr_data=None))
        self.assertIsNone(pd)
        self.assertIsNone(err)

    def test_valid_file_loads(self):
        pd, err = cli._load_pr_data(argparse.Namespace(pr_data=str(FIXTURES / "prdata_jest.json")))
        self.assertIsNone(err)
        self.assertEqual(len(pd.records), 3)

    def test_malformed_file_is_usage_error_exit_2(self):
        # The user explicitly passed the file, so a bad shape exits 2 with a
        # message — never a silent zero.
        with contextlib.redirect_stderr(io.StringIO()) as errbuf:
            pd, err = cli._load_pr_data(
                argparse.Namespace(pr_data=str(FIXTURES / "prdata_malformed.json")))
        self.assertIsNone(pd)
        self.assertEqual(err, 2)
        self.assertIn("gh pr list", errbuf.getvalue())


if __name__ == "__main__":
    unittest.main()
