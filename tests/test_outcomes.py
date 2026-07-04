"""Outcomes tests (Package J): revert pairs, time-to-correction, change-failure proxy."""
import os
import subprocess
import tempfile
import unittest
from datetime import date
from pathlib import Path

from shipsignal import impact, report
from shipsignal.impact import (
    MIN_REVERT_PAIRS_FOR_MEDIAN,
    Commit,
    compute_outcomes,
    quality_metrics,
)


def _c(sha="x", date_str="2026-01-01", email="dev@ex.com", subject="",
       trailers=None, files=None, adds=0, dels=0, body=""):
    return Commit(sha, date.fromisoformat(date_str), email, subject,
                  trailers or [], files or [], adds, dels, body)


class TestRevertTargetParsing(unittest.TestCase):
    """Commit.revert_target_sha — git's own revert body vs explicit trailers."""

    def test_git_revert_body_format(self):
        c = _c(subject='Revert "Add widget"',
               body='Revert "Add widget"\n\n'
                    'This reverts commit abc1234def5678901234567890123456789abcd.\n')
        self.assertEqual(c.revert_target_sha, "abc1234def5678901234567890123456789abcd")

    def test_fixes_trailer(self):
        c = _c(subject="Patch up widget", trailers=["Fixes: abc1234"])
        self.assertEqual(c.revert_target_sha, "abc1234")

    def test_reverts_trailer_case_insensitive(self):
        c = _c(subject="undo bad change", trailers=["REVERTS: ABC1234"])
        self.assertEqual(c.revert_target_sha, "abc1234")

    def test_no_target_returns_none(self):
        c = _c(subject="Add a feature", body="Just a normal commit body.\n")
        self.assertIsNone(c.revert_target_sha)

    def test_body_takes_precedence_over_unrelated_trailer(self):
        # A real `git revert` commit that also happens to carry a Co-Authored-By
        # trailer should still resolve its target from the body.
        c = _c(subject='Revert "Add widget"',
               body="This reverts commit 1111111.\n",
               trailers=["Co-Authored-By: Claude <c@anthropic.com>"])
        self.assertEqual(c.revert_target_sha, "1111111")


class TestComputeOutcomes(unittest.TestCase):
    def test_happy_path_median(self):
        commits = [
            _c(sha="aaa0001", date_str="2026-01-01", subject="Feature 1"),
            _c(sha="aaa0002", date_str="2026-01-01", subject="Feature 2"),
            _c(sha="aaa0003", date_str="2026-01-01", subject="Feature 3"),
            _c(sha="bbb0001", date_str="2026-01-06", subject='Revert "Feature 1"',
               body="This reverts commit aaa0001.\n"),
            _c(sha="bbb0002", date_str="2026-01-09", subject='Revert "Feature 2"',
               body="This reverts commit aaa0002.\n"),
            _c(sha="bbb0003", date_str="2026-01-12", subject='Revert "Feature 3"',
               body="This reverts commit aaa0003.\n"),
        ]
        oc = compute_outcomes(commits, quality_metrics(commits))
        rp = oc["revert_pairs"]
        self.assertEqual(rp["status"], "scored")
        self.assertEqual(rp["flagged"], 3)
        self.assertEqual(rp["matched"], 3)
        self.assertEqual(rp["unmatched"], 0)
        self.assertEqual(rp["median_days"], 8.0)  # deltas [5, 8, 11] -> median 8

    def test_below_floor_is_na(self):
        commits = [
            _c(sha="aaa0001", date_str="2026-01-01", subject="Feature 1"),
            _c(sha="aaa0002", date_str="2026-01-01", subject="Feature 2"),
            _c(sha="bbb0001", date_str="2026-01-06", subject='Revert "Feature 1"',
               body="This reverts commit aaa0001.\n"),
            _c(sha="bbb0002", date_str="2026-01-09", subject='Revert "Feature 2"',
               body="This reverts commit aaa0002.\n"),
        ]
        oc = compute_outcomes(commits, quality_metrics(commits))
        rp = oc["revert_pairs"]
        self.assertEqual(rp["status"], "n/a")
        self.assertEqual(rp["matched"], 2)
        self.assertIn(f"need {MIN_REVERT_PAIRS_FOR_MEDIAN}", rp["reason"])
        self.assertIsNone(rp["median_days"])

    def test_target_outside_window_is_unmatched(self):
        commits = [
            _c(sha="bbb0001", date_str="2026-01-05", subject='Revert "Something"',
               body="This reverts commit deadbeef1234567890123456789012345678.\n"),
        ]
        oc = compute_outcomes(commits, quality_metrics(commits))
        rp = oc["revert_pairs"]
        self.assertEqual(rp["flagged"], 1)
        self.assertEqual(rp["matched"], 0)
        self.assertEqual(rp["unmatched"], 1)

    def test_revert_of_a_revert_both_pairs_counted(self):
        commits = [
            _c(sha="aaa0001", date_str="2026-01-01", subject="Add widget"),
            _c(sha="bbb0002", date_str="2026-01-05", subject='Revert "Add widget"',
               body="This reverts commit aaa0001.\n"),
            _c(sha="ccc0003", date_str="2026-01-10",
               subject='Revert "Revert "Add widget""',
               body="This reverts commit bbb0002.\n"),
        ]
        oc = compute_outcomes(commits, quality_metrics(commits))
        rp = oc["revert_pairs"]
        self.assertEqual(rp["flagged"], 2)
        self.assertEqual(rp["matched"], 2)
        self.assertEqual(rp["unmatched"], 0)

    def test_short_sha_trailer_prefix_matches_full_sha(self):
        full_sha = "abc1234def5678901234567890123456789abcd"
        commits = [
            _c(sha=full_sha, date_str="2026-01-01", subject="Feature X"),
            _c(sha="rev0001", date_str="2026-01-05", subject="Patch feature X",
               trailers=["Fixes: abc1234"]),
        ]
        oc = compute_outcomes(commits, quality_metrics(commits))
        rp = oc["revert_pairs"]
        self.assertEqual(rp["matched"], 1)
        self.assertEqual(rp["unmatched"], 0)

    def test_change_failure_proxy_passthrough(self):
        commits = [_c(sha="s1", subject="fix: bug"), _c(sha="s2", subject="Add feature")]
        q = quality_metrics(commits)
        oc = compute_outcomes(commits, q)
        self.assertEqual(oc["change_failure_rate"], q["fix_rate"])
        self.assertEqual(oc["change_failure_commits"], q["fix_commits"])


# --- End-to-end: real `git revert` commits, parsed via the real git-log walk ---

def _git_init(d: Path) -> dict:
    env = {**os.environ, "GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@t"}
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=d, check=True, env=env)
    for key, val in (("commit.gpgsign", "false"), ("gc.auto", "0"),
                     ("maintenance.auto", "false")):
        subprocess.run(["git", "config", key, val], cwd=d, check=True, env=env)
    return env


def _commit(d: Path, env: dict, msg: str, date_str: str, fname: str, content: str) -> str:
    (d / fname).write_text(content)
    e = {**env, "GIT_AUTHOR_DATE": date_str, "GIT_COMMITTER_DATE": date_str}
    subprocess.run(["git", "add", "-A"], cwd=d, check=True, env=e)
    subprocess.run(["git", "commit", "-q", "-m", msg], cwd=d, check=True, env=e)
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=d, check=True, env=e,
                          capture_output=True, text=True).stdout.strip()


def _revert(d: Path, env: dict, target_sha: str, date_str: str) -> None:
    e = {**env, "GIT_AUTHOR_DATE": date_str, "GIT_COMMITTER_DATE": date_str}
    subprocess.run(["git", "revert", "--no-edit", target_sha], cwd=d, check=True, env=e)


class TestOutcomesEndToEnd(unittest.TestCase):
    """Real `git revert` commits, parsed by the real git-log walk — validates the
    body/numstat boundary parsing (see walk_history) against actual git output,
    not just our own assumption of the format."""

    def test_real_git_revert_pairs_render(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            env = _git_init(d)
            shas = [
                _commit(d, env, f"Add feature {i}", f"2026-01-0{i} 12:00:00",
                        f"feature{i}.txt", f"feature {i}\n")
                for i in range(1, 4)
            ]
            for i, sha in enumerate(shas, start=1):
                _revert(d, env, sha, f"2026-01-{5 + i:02d} 12:00:00")

            result = impact.compute_impact(d, repo_label="outcomes-fixture")
            rp = result["outcomes"]["revert_pairs"]
            self.assertEqual(rp["status"], "scored")
            self.assertEqual(rp["matched"], 3)
            self.assertEqual(rp["unmatched"], 0)

            cli = report.render_impact(result)
            self.assertIn("Outcomes", cli)
            self.assertIn("revert pairs 3", cli)
            self.assertIn("change-failure proxy", cli)

            md = report.render_impact_markdown(result)
            self.assertIn("## Outcomes", md)
            self.assertIn("Revert pairs:** 3", md)

            html = report.render_impact_html(result)
            self.assertIn("Outcomes", html)
            self.assertIn("Revert pairs", html)


if __name__ == "__main__":
    unittest.main()
