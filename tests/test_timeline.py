"""Trajectory / over-time bucketing tests (stdlib unittest)."""
import unittest
from datetime import date, timedelta

from shipsignal.impact import Commit
from shipsignal.timeline import (
    _choose_period_days,
    build_trajectory,
)


def _commit(d, ai=False, files=None, lines=20, email="dev@x"):
    trailers = ["Co-Authored-By: Claude <noreply@anthropic.com>"] if ai else []
    return Commit("h", d, email, "feat: x", trailers, files or ["src/a.py"], lines, 0)


class TestChoosePeriod(unittest.TestCase):
    def test_targets_reasonable_buckets(self):
        pd = _choose_period_days(360, 180)          # 180 commits / ~1 yr
        self.assertGreaterEqual(pd, 7)
        self.assertLessEqual(360 // pd, 14)          # not too many buckets

    def test_min_one_week(self):
        self.assertEqual(_choose_period_days(3, 200), 7)


class TestBuildTrajectory(unittest.TestCase):
    def test_insufficient_few_commits(self):
        commits = [_commit(date(2026, 1, 1) + timedelta(days=i)) for i in range(10)]
        self.assertEqual(build_trajectory(commits)["status"], "insufficient")

    def test_insufficient_short_span(self):
        # plenty of commits but all crammed into ~2 weeks
        commits = [_commit(date(2026, 1, 1) + timedelta(days=i % 14)) for i in range(50)]
        self.assertEqual(build_trajectory(commits)["status"], "insufficient")

    def test_ok_and_ramp_is_visible(self):
        # 120 commits over ~24 weeks; AI only in the second half
        commits = []
        start = date(2026, 1, 1)
        for i in range(120):
            d = start + timedelta(days=int(i * 1.4))   # spread over ~168 days
            commits.append(_commit(d, ai=(i >= 60)))
        t = build_trajectory(commits)
        self.assertEqual(t["status"], "ok")
        self.assertGreaterEqual(len(t["periods"]), 3)
        first = t["periods"][0]["adoption_pct"]
        last = t["periods"][-1]["adoption_pct"]
        self.assertLess(first, last)                  # adoption ramps up
        self.assertEqual(first, 0.0)
        self.assertEqual(last, 100.0)

    def test_quiet_stretch_is_a_gap_not_zero(self):
        # commits in the first ~5 weeks and last ~5 weeks, nothing in between
        commits = []
        for i in range(40):
            commits.append(_commit(date(2026, 1, 1) + timedelta(days=i % 35)))
        for i in range(40):
            commits.append(_commit(date(2026, 6, 1) + timedelta(days=i % 35)))
        t = build_trajectory(commits)
        self.assertEqual(t["status"], "ok")
        # at least one middle period should be an empty gap (adoption None)
        self.assertTrue(any(p["adoption_pct"] is None for p in t["periods"]))

    def test_thin_bucket_health_insufficient(self):
        # a sparse repo: enough total + span, but some buckets below the health floor
        commits = [_commit(date(2026, 1, 1) + timedelta(days=i * 4)) for i in range(45)]
        t = build_trajectory(commits)
        self.assertEqual(t["status"], "ok")
        # every period is scored or honestly marked insufficient (never a fake score)
        for p in t["periods"]:
            if p["health_score"] is None:
                self.assertEqual(p["health_status"], "insufficient")


class TestPerPeriodBreadth(unittest.TestCase):
    """Feature C: trajectory buckets carry per-period breadth_pct (or None
    when the bucket has too few contributors to compute it honestly)."""

    def test_solo_period_breadth_none(self):
        # 120 commits, all from one author — breadth must be None per period.
        commits = []
        start = date(2026, 1, 1)
        for i in range(120):
            commits.append(_commit(start + timedelta(days=int(i * 1.4)), ai=(i % 2 == 0)))
        t = build_trajectory(commits)
        self.assertEqual(t["status"], "ok")
        for p in t["periods"]:
            self.assertIsNone(p["breadth_pct"], f"single-author period leaked breadth: {p}")

    def test_multi_contributor_period_breadth(self):
        commits = []
        start = date(2026, 1, 1)
        # 4 contributors, AI usage growing across the window
        emails = ["a@x", "b@x", "c@x", "d@x"]
        for i in range(120):
            d = start + timedelta(days=int(i * 1.4))
            email = emails[i % 4]
            # First half — only "a" uses AI. Second half — a, b, c.
            if i < 60:
                ai = (email == "a@x")
            else:
                ai = email in ("a@x", "b@x", "c@x")
            commits.append(_commit(d, ai=ai, email=email))
        t = build_trajectory(commits)
        self.assertEqual(t["status"], "ok")
        # Some periods must have a computed breadth (≥3 contributors per bucket).
        scored = [p for p in t["periods"] if p["breadth_pct"] is not None]
        self.assertTrue(scored, "no period computed breadth despite 4 contributors")
        # Last period (everyone but d uses AI → 3 of 4 = 75%; allow some
        # variance based on bucketing).
        last_scored = scored[-1]["breadth_pct"]
        self.assertGreater(last_scored, 50.0)


if __name__ == "__main__":
    unittest.main()
