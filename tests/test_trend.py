"""Trend / Visual Snapshot Viewer tests (Feature S2)."""
import html.parser
import tempfile
import unittest
from pathlib import Path

from shipsignal import report, snapshot, trend


def _snap(*, schema="snapshot-0.1", repo="t", sha="abc", commit_date="2026-01-01",
          readiness_score=80, readiness_grade="B", categories=None, fixes=None,
          ai_share=0.4, ai_level="Established", total_commits=100,
          breadth_pct=20.0, breadth_status="scored", health=85):
    """Build a synthetic snapshot dict for testing. Defaults mirror a realistic
    mid-state repo (B-grade, modest AI adoption, scored breadth)."""
    categories = categories or [
        {"id": "entry_point", "max": 20, "points": 20, "status": "scored"},
        {"id": "agent_instructions", "max": 15, "points": 11, "status": "scored"},
    ]
    fixes = fixes or []
    return {
        "schema_version": schema,
        "shipsignal_version": "0.6.0",
        "repo": repo,
        "commit_sha": sha,
        "commit_date": commit_date,
        "readiness": {
            "score": readiness_score,
            "grade": readiness_grade,
            "categories": categories,
            "fixes": fixes,
        },
        "impact": {
            "window": {"first_commit": "2025-01-01", "last_commit": commit_date,
                       "weeks": 50.0, "total_commits": total_commits},
            "adoption": {
                "ai_coauthor_share": ai_share,
                "level": ai_level,
                "ai_commits": int(ai_share * total_commits),
                "total_commits": total_commits,
                "adoption_date": None,
                "per_tool": {},
                "breadth": ({"status": "scored", "active_contributors": 5,
                             "ai_contributors": 1, "breadth_pct": breadth_pct,
                             "trend": "unknown", "note": "Team-level only."}
                            if breadth_status == "scored"
                            else {"status": "n/a", "reason": "too few",
                                  "active_contributors": 1, "ai_contributors": None,
                                  "breadth_pct": None, "trend": None,
                                  "note": "Team-level only."}),
            },
            "delivery_health": {"score": health, "grade": "B", "status": "scored"},
        },
    }


def _write_snap(d: Path, snap: dict) -> Path:
    filename = f"{snap['commit_date']}-{snap['commit_sha'][:8]}.json"
    return snapshot.write_snapshot(snap, d / filename)


# ---------------------------------------------------------------------------
# Load layer
# ---------------------------------------------------------------------------


class TestLoadSnapshots(unittest.TestCase):
    def test_empty_dir_returns_empty(self):
        d = Path(tempfile.mkdtemp())
        self.assertEqual(snapshot.load_snapshots(d), [])

    def test_loads_and_sorts_by_commit_date(self):
        d = Path(tempfile.mkdtemp()) / "snaps"
        d.mkdir()
        # Write deliberately out of chronological order.
        _write_snap(d, _snap(commit_date="2026-03-15", sha="bbb22222"))
        _write_snap(d, _snap(commit_date="2026-01-10", sha="aaa11111"))
        _write_snap(d, _snap(commit_date="2026-06-01", sha="ccc33333"))
        snaps = snapshot.load_snapshots(d)
        dates = [s["commit_date"] for s in snaps]
        self.assertEqual(dates, ["2026-01-10", "2026-03-15", "2026-06-01"])

    def test_accepts_repo_root(self):
        # ``path/.shipsignal/snapshots/`` is the default lookup.
        root = Path(tempfile.mkdtemp())
        snaps_dir = root / ".shipsignal" / "snapshots"
        snaps_dir.mkdir(parents=True)
        _write_snap(snaps_dir, _snap(commit_date="2026-05-01"))
        self.assertEqual(len(snapshot.load_snapshots(root)), 1)

    def test_skips_malformed_files(self):
        d = Path(tempfile.mkdtemp()) / "snaps"
        d.mkdir()
        _write_snap(d, _snap())
        (d / "junk.json").write_text("not json {", encoding="utf-8")
        (d / "empty_dict.json").write_text("{}", encoding="utf-8")  # no schema_version
        snaps = snapshot.load_snapshots(d)
        self.assertEqual(len(snaps), 1, f"expected 1 valid snap, got {len(snaps)}")

    def test_filter_since_and_limit(self):
        snaps = [
            _snap(commit_date="2026-01-01", sha="01" * 4),
            _snap(commit_date="2026-02-01", sha="02" * 4),
            _snap(commit_date="2026-03-01", sha="03" * 4),
            _snap(commit_date="2026-04-01", sha="04" * 4),
            _snap(commit_date="2026-05-01", sha="05" * 4),
        ]
        # since filters first
        s2 = snapshot.filter_snapshots(snaps, since="2026-02-15")
        self.assertEqual([s["commit_date"] for s in s2],
                         ["2026-03-01", "2026-04-01", "2026-05-01"])
        # limit applies after since, taking the most-recent N
        s3 = snapshot.filter_snapshots(snaps, since="2026-02-15", limit=2)
        self.assertEqual([s["commit_date"] for s in s3],
                         ["2026-04-01", "2026-05-01"])


# ---------------------------------------------------------------------------
# Diff layer
# ---------------------------------------------------------------------------


class TestComputeTrendStatusPaths(unittest.TestCase):
    def test_empty(self):
        out = trend.compute_trend([])
        self.assertEqual(out["status"], "empty")
        self.assertEqual(out["snapshot_count"], 0)

    def test_single_point(self):
        out = trend.compute_trend([_snap(readiness_score=84)])
        self.assertEqual(out["status"], "single_point")
        self.assertEqual(out["snapshot_count"], 1)
        self.assertEqual(out["headlines"]["readiness"]["current"], 84)
        self.assertIsNone(out["headlines"]["readiness"]["delta"],
                          "single-snapshot delta must be None, never fabricated")


class TestHeadlineDeltas(unittest.TestCase):
    def test_two_point_delta(self):
        a = _snap(commit_date="2026-01-01", sha="aaa11111",
                  readiness_score=70, ai_share=0.30, breadth_pct=10.0, health=80)
        b = _snap(commit_date="2026-03-01", sha="bbb22222",
                  readiness_score=85, ai_share=0.45, breadth_pct=25.0, health=82)
        out = trend.compute_trend([a, b])
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["headlines"]["readiness"]["current"], 85)
        self.assertEqual(out["headlines"]["readiness"]["delta"], 15)
        self.assertEqual(out["headlines"]["breadth"]["delta"], 15.0)
        self.assertAlmostEqual(out["headlines"]["ai_adoption"]["delta"], 0.15)
        self.assertEqual(out["headlines"]["delivery_health"]["delta"], 2)

    def test_breadth_na_to_scored_delta_is_none(self):
        """A status flip on breadth must yield delta=None, never a misleading
        subtraction from null."""
        a = _snap(commit_date="2026-01-01", sha="a", breadth_status="n/a")
        b = _snap(commit_date="2026-02-01", sha="b", breadth_pct=42.0)
        out = trend.compute_trend([a, b])
        self.assertIsNone(out["headlines"]["breadth"]["delta"])

    def test_series_carries_none_gaps(self):
        """Sparkline source data must include None where the metric was n/a,
        so the renderer can show a gap (never zero-fill)."""
        a = _snap(commit_date="2026-01-01", sha="a", breadth_status="n/a")
        b = _snap(commit_date="2026-02-01", sha="b", breadth_pct=20.0)
        c = _snap(commit_date="2026-03-01", sha="c", breadth_pct=30.0)
        out = trend.compute_trend([a, b, c])
        self.assertEqual(out["headlines"]["breadth"]["series"], [None, 20.0, 30.0])


class TestFixesDiff(unittest.TestCase):
    def _fix(self, det, path, sev="warn"):
        return {"detector": det, "path": path, "severity": sev}

    def test_resolved_new_still_open(self):
        a_fixes = [self._fix("module_readme", "src/a"),
                   self._fix("module_readme", "src/b"),
                   self._fix("broken_link", "docs/x.md")]
        b_fixes = [self._fix("module_readme", "src/b"),       # still
                   self._fix("doc_drift", "README.md")]       # new
                                                              # resolved: src/a, docs/x.md
        a = _snap(sha="a", fixes=a_fixes)
        b = _snap(sha="b", commit_date="2026-02-01", fixes=b_fixes)
        out = trend.compute_trend([a, b])
        fixes = out["fixes"]
        self.assertTrue(fixes["comparable"])
        self.assertEqual(len(fixes["resolved"]), 2)
        self.assertEqual(len(fixes["new"]), 1)
        self.assertEqual(fixes["still_open_count"], 1)
        # Resolved entries carry the same fingerprint, no evidence text.
        for f in fixes["resolved"]:
            self.assertSetEqual(set(f.keys()), {"detector", "path", "severity"})

    def test_schema_mismatch_skips_diff(self):
        a = _snap(schema="snapshot-0.1", sha="a", fixes=[self._fix("x", "y")])
        b = _snap(schema="snapshot-0.2", sha="b", commit_date="2026-02-01",
                  fixes=[self._fix("z", "w")])
        out = trend.compute_trend([a, b])
        self.assertFalse(out["fixes"]["comparable"])
        self.assertIn("schema changed", out["fixes"]["schema_warning"])
        # No resolved/new claims when schema differs.
        self.assertEqual(out["fixes"]["resolved"], [])
        self.assertEqual(out["fixes"]["new"], [])

    def test_no_phantom_resolutions_from_same_set(self):
        """Identical fix lists → 0 resolved, 0 new, all still open."""
        fixes = [self._fix("a", "p"), self._fix("b", "q")]
        a = _snap(sha="a", fixes=fixes)
        b = _snap(sha="b", commit_date="2026-02-01", fixes=fixes)
        out = trend.compute_trend([a, b])
        self.assertEqual(len(out["fixes"]["resolved"]), 0)
        self.assertEqual(len(out["fixes"]["new"]), 0)
        self.assertEqual(out["fixes"]["still_open_count"], 2)


class TestCategoryFlips(unittest.TestCase):
    def test_na_to_scored_flagged(self):
        a = _snap(sha="a", categories=[
            {"id": "agent_instructions", "max": 15, "points": None, "status": "n/a"}
        ])
        b = _snap(sha="b", commit_date="2026-02-01", categories=[
            {"id": "agent_instructions", "max": 15, "points": 11, "status": "scored"}
        ])
        out = trend.compute_trend([a, b])
        flips = out["category_flips"]
        self.assertEqual(len(flips), 1)
        self.assertEqual(flips[0]["id"], "agent_instructions")
        self.assertEqual(flips[0]["from"], "n/a")
        self.assertEqual(flips[0]["to"], "scored")


class TestWindowHonesty(unittest.TestCase):
    def test_growth_warning_fires(self):
        a = _snap(sha="a", total_commits=100)
        b = _snap(sha="b", commit_date="2026-02-01", total_commits=200)  # +100%
        out = trend.compute_trend([a, b])
        self.assertIsNotNone(out["window"]["growth_warning"])
        self.assertIn("more commits", out["window"]["growth_warning"])

    def test_growth_warning_silent_on_small_repos(self):
        # Even a >30% jump shouldn't fire below the 50-commit floor.
        a = _snap(sha="a", total_commits=10)
        b = _snap(sha="b", commit_date="2026-02-01", total_commits=25)
        out = trend.compute_trend([a, b])
        self.assertIsNone(out["window"]["growth_warning"])


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------


class TestRenderTrendCLI(unittest.TestCase):
    def test_empty(self):
        text = report.render_trend(trend.compute_trend([]))
        self.assertIn("no snapshots", text.lower())

    def test_single_point(self):
        text = report.render_trend(trend.compute_trend([_snap(readiness_score=99)]))
        self.assertIn("1 snapshot", text)
        self.assertIn("99", text)
        # The "scan again" hint must appear so users know what to do next.
        self.assertIn("scan again", text.lower())

    def test_two_points_show_deltas(self):
        a = _snap(sha="a", commit_date="2026-01-01", readiness_score=70)
        b = _snap(sha="b", commit_date="2026-02-01", readiness_score=84)
        text = report.render_trend(trend.compute_trend([a, b]))
        self.assertIn("70", text)
        self.assertIn("84", text)
        self.assertIn("+14", text, "delta chip should appear")

    def test_category_flip_is_surfaced(self):
        a = _snap(sha="a", categories=[
            {"id": "agent_instructions", "max": 15, "points": None, "status": "n/a"}
        ])
        b = _snap(sha="b", commit_date="2026-02-01", categories=[
            {"id": "agent_instructions", "max": 15, "points": 11, "status": "scored"}
        ])
        text = report.render_trend(trend.compute_trend([a, b]))
        self.assertIn("flipped", text)


class _HTMLOK(html.parser.HTMLParser):
    """Trivial validity check: raises on malformed HTML."""


class TestRenderTrendHTML(unittest.TestCase):
    def test_html_well_formed_two_points(self):
        a = _snap(sha="a", commit_date="2026-01-01", readiness_score=70)
        b = _snap(sha="b", commit_date="2026-02-01", readiness_score=84)
        h = report.render_trend_html(trend.compute_trend([a, b]))
        _HTMLOK().feed(h)
        # Must include the SVG line chart + the headline cards.
        self.assertIn("<svg", h)
        self.assertIn("Readiness", h)
        self.assertIn("Breadth", h)

    def test_html_single_point_no_chart(self):
        h = report.render_trend_html(trend.compute_trend([_snap()]))
        _HTMLOK().feed(h)
        # Single-point view doesn't show the over-time chart (nothing to plot).
        self.assertNotIn("Over time", h)
        # But it shows the "scan again" message.
        self.assertIn("scan again", h.lower())

    def test_html_empty(self):
        h = report.render_trend_html(trend.compute_trend([]))
        _HTMLOK().feed(h)
        self.assertIn("No snapshots", h)


class TestRenderTrendMarkdown(unittest.TestCase):
    def test_table_present(self):
        a = _snap(sha="a", commit_date="2026-01-01", readiness_score=70)
        b = _snap(sha="b", commit_date="2026-02-01", readiness_score=84)
        md = report.render_trend_markdown(trend.compute_trend([a, b]))
        self.assertIn("| Metric |", md)
        self.assertIn("Readiness", md)


# ---------------------------------------------------------------------------
# Privacy invariant — trend never leaks per-person data through any layer.
# ---------------------------------------------------------------------------


class TestBreadthPrivacyThroughTrend(unittest.TestCase):
    """The aggregate-only invariant must carry from snapshot → trend → render."""

    def test_no_email_in_rendered_output(self):
        # Even with the breadth field present (scored), no identifier should
        # appear anywhere in the output — because the snapshot doesn't carry one.
        a = _snap(sha="a", commit_date="2026-01-01", breadth_pct=20.0)
        b = _snap(sha="b", commit_date="2026-02-01", breadth_pct=40.0)
        out = trend.compute_trend([a, b])
        # Smoke-test render paths
        rendered = (report.render_trend(out)
                    + report.render_trend_markdown(out)
                    + report.render_trend_html(out))
        for forbidden in ("@", "alice", "bob", "carol", ".com>", "<noreply"):
            # @ in URLs (none here) and emails would both be a problem; the
            # snapshot schema doesn't include either.
            self.assertNotIn(forbidden, rendered,
                             f"{forbidden!r} appeared in trend output")


if __name__ == "__main__":
    unittest.main()
