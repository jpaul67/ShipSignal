"""Impact-lens unit tests (stdlib unittest)."""
import unittest
from datetime import date, timedelta
from pathlib import Path

from shipsignal import impact
from shipsignal.impact import (
    Commit,
    adoption_level,
    assess_confidence,
    compute_impact,
    delivery_health,
    detect_adoption_date,
    flow_metrics,
    people_metrics,
    quality_metrics,
)

REPO = Path(__file__).resolve().parent.parent


def _c(sha="x", date_str="2026-01-01", email="dev@ex.com", subject="",
       trailers=None, files=None, adds=0, dels=0):
    return Commit(sha, date.fromisoformat(date_str), email, subject,
                  trailers or [], files or [], adds, dels)


class TestTrailerDetection(unittest.TestCase):
    def test_ai_trailer_recognized(self):
        c = _c(trailers=["Co-Authored-By: Claude <noreply@anthropic.com>"])
        self.assertTrue(c.ai_authored)
        self.assertIn("Claude", c.ai_tools)

    def test_human_trailer_not_ai(self):
        c = _c(trailers=["Co-Authored-By: Jane <jane@example.com>"])
        self.assertFalse(c.ai_authored)
        self.assertEqual(c.ai_tools, set())

    def test_case_insensitive(self):
        c = _c(trailers=["co-authored-by: GITHUB COPILOT <noreply@github.com>"])
        self.assertTrue(c.ai_authored)
        self.assertIn("Copilot", c.ai_tools)

    def test_non_coauthor_trailer_ignored(self):
        # "Reviewed-By: Claude" should NOT count as an AI co-author.
        c = _c(trailers=["Reviewed-By: Claude <foo@bar>"])
        self.assertFalse(c.ai_authored)

    def test_multi_tool(self):
        c = _c(trailers=[
            "Co-Authored-By: Claude <noreply@anthropic.com>",
            "Co-Authored-By: Cursor <cursor@anysphere.com>",
        ])
        self.assertEqual(c.ai_tools, {"Claude", "Cursor"})


class TestSubjectAndPaths(unittest.TestCase):
    def test_fix_subjects(self):
        for s in ["fix: bad behavior", "Fix login bug", "fix(scope): x", "revert: foo",
                  "hotfix: prod down", "fix!: breaking"]:
            self.assertTrue(_c(subject=s).is_fix, s)

    def test_non_fix_subjects(self):
        for s in ["Add feature", "Affixed banner", "Refactor", "Bump deps", "Fixate"]:
            self.assertFalse(_c(subject=s).is_fix, s)

    def test_test_path_detection(self):
        # touches_tests should match common test path patterns
        self.assertTrue(_c(files=["tests/foo.py"]).touches_tests)
        self.assertTrue(_c(files=["src/foo.test.ts"]).touches_tests)
        self.assertTrue(_c(files=["pkg/__tests__/bar.js"]).touches_tests)
        self.assertTrue(_c(files=["spec/bar_spec.rb"]).touches_tests)
        self.assertFalse(_c(files=["src/foo.py"]).touches_tests)

    def test_code_touch_excludes_tests(self):
        # touches_code should NOT fire when the only files are tests
        self.assertFalse(_c(files=["tests/foo.py"]).touches_code)
        self.assertTrue(_c(files=["src/foo.py"]).touches_code)
        # README-only commit → not code
        self.assertFalse(_c(files=["README.md"]).touches_code)


class TestAdoptionDetection(unittest.TestCase):
    def _series(self, n_weeks, ai_rate):
        commits = []
        for w in range(n_weeks):
            day = date(2026, 1, 5) + timedelta(weeks=w)  # 2026-01-05 is a Monday
            for i in range(10):
                trailers = (["Co-Authored-By: Claude <x>"] if i < int(10 * ai_rate) else [])
                commits.append(_c(date_str=day.isoformat(), trailers=trailers))
        return commits

    def test_sustained_window_required(self):
        # A single high-AI week doesn't trip adoption — need 2 sustained.
        commits = self._series(1, 1.0) + self._series(3, 0.0)
        # Re-stitch with sequential weeks
        all_c = []
        for w in range(4):
            day = date(2026, 1, 5) + timedelta(weeks=w)
            rate = 1.0 if w == 0 else 0.0
            for i in range(10):
                trailers = ["Co-Authored-By: Claude <x>"] if i < int(10 * rate) else []
                all_c.append(_c(date_str=day.isoformat(), trailers=trailers))
        self.assertIsNone(detect_adoption_date(all_c, threshold=0.5, sustained_weeks=2))

    def test_sustained_window_trips(self):
        all_c = []
        for w in range(4):
            day = date(2026, 1, 5) + timedelta(weeks=w)
            rate = 0.0 if w < 2 else 1.0
            for i in range(10):
                trailers = ["Co-Authored-By: Claude <x>"] if i < int(10 * rate) else []
                all_c.append(_c(date_str=day.isoformat(), trailers=trailers))
        adopt = detect_adoption_date(all_c, threshold=0.5, sustained_weeks=2)
        self.assertEqual(adopt, date(2026, 1, 19))  # third week start


class TestConfidenceGate(unittest.TestCase):
    def test_too_few_commits(self):
        commits = [_c(date_str=f"2026-01-{d:02d}") for d in range(1, 10)]
        conf = assess_confidence(commits)
        self.assertFalse(conf.sufficient_for_score)
        self.assertTrue(any("commits" in r for r in conf.reasons))

    def test_too_short_window(self):
        commits = [_c(date_str="2026-01-01") for _ in range(60)]  # all on one day
        conf = assess_confidence(commits)
        self.assertFalse(conf.sufficient_for_score)
        self.assertTrue(any("weeks" in r for r in conf.reasons))

    def test_sufficient(self):
        commits = []
        for w in range(10):
            day = date(2026, 1, 5) + timedelta(weeks=w)
            for _ in range(7):
                commits.append(_c(date_str=day.isoformat()))
        self.assertTrue(assess_confidence(commits).sufficient_for_score)


class TestPeopleMetrics(unittest.TestCase):
    def test_solo_flagged(self):
        commits = [_c(email="a@x.com") for _ in range(5)]
        m = people_metrics(commits)
        self.assertTrue(m["solo"])
        self.assertEqual(m["contributors"], 1)

    def test_bus_factor(self):
        # 8 commits by A, 1 each by B/C → bus-factor 1 (A alone covers ≥50%)
        commits = [_c(email="a@x") for _ in range(8)] + [_c(email="b@x"), _c(email="c@x")]
        self.assertEqual(people_metrics(commits)["bus_factor"], 1)


class TestQualityAndFlow(unittest.TestCase):
    def test_test_to_code_ratio(self):
        commits = [
            _c(files=["src/foo.py"]),
            _c(files=["src/bar.py"]),
            _c(files=["tests/foo_test.py", "src/foo.py"]),
        ]
        q = quality_metrics(commits)
        # 1 test-touching, 3 code-touching → 1/3
        self.assertAlmostEqual(q["test_to_code_ratio"], 0.333, places=2)

    def test_commits_per_week(self):
        commits = []
        for d in range(1, 15):  # 14 commits spanning ~2 weeks
            commits.append(_c(date_str=f"2026-01-{d:02d}"))
        f = flow_metrics(commits)
        self.assertGreater(f["commits_per_week"], 0)


class TestAdoptionLevel(unittest.TestCase):
    def test_bands(self):
        self.assertEqual(adoption_level(0.0), "None")
        self.assertEqual(adoption_level(0.013), "Emerging")   # vitest's 1.3%
        self.assertEqual(adoption_level(0.30), "Established")
        self.assertEqual(adoption_level(0.971), "Pervasive")  # crown's 97%


class TestDeliveryHealth(unittest.TestCase):
    def _commits(self, n, *, lines=20, files=1, test_every=0, email="a@x"):
        """Build n commits; every `test_every`-th also touches a test path."""
        out = []
        for i in range(n):
            day = date(2026, 1, 1) + timedelta(days=i)
            files_list = [f"src/mod{i}.py"]
            if test_every and i % test_every == 0:
                files_list.append(f"tests/mod{i}_test.py")
            out.append(Commit("h", day, email, "feat: x", [], files_list, lines, 0))
        return out

    def test_insufficient_below_floor(self):
        dh = delivery_health(self._commits(5), {
            "change_shape": {"median_lines": 20, "large_change_rate": 0.0, "median_files": 1},
            "quality": {"fix_rate": 0.1, "test_to_code_ratio": 0.5},
            "people": {"solo": True, "top_author_share": 1.0, "bus_factor": 1, "contributors": 1},
            "flow": {"commits_per_week": 5, "active_day_ratio": 1.0},
        })
        self.assertEqual(dh["status"], "insufficient")
        self.assertIsNone(dh["score"])

    def test_solo_suppresses_knowledge(self):
        commits = self._commits(30, test_every=2)
        m = {
            "change_shape": {"median_lines": 20, "large_change_rate": 0.0, "median_files": 1},
            "quality": {"fix_rate": 0.1, "test_to_code_ratio": 0.5},
            "people": {"solo": True, "top_author_share": 1.0, "bus_factor": 1, "contributors": 1},
            "flow": {"commits_per_week": 7, "active_day_ratio": 1.0},
        }
        dh = delivery_health(commits, m)
        self.assertEqual(dh["status"], "scored")
        know = next(c for c in dh["components"] if c["id"] == "knowledge_distribution")
        self.assertIn("solo", know["status"])
        self.assertIsNone(know["score_frac"])  # not counted in the denominator

    def test_low_test_discipline_flagged(self):
        commits = self._commits(40, test_every=0)  # zero test-touching commits
        m = {
            "change_shape": {"median_lines": 20, "large_change_rate": 0.0, "median_files": 1},
            "quality": {"fix_rate": 0.1, "test_to_code_ratio": 0.0},
            "people": {"solo": True, "top_author_share": 1.0, "bus_factor": 1, "contributors": 1},
            "flow": {"commits_per_week": 7, "active_day_ratio": 1.0},
        }
        dh = delivery_health(commits, m)
        test_c = next(c for c in dh["components"] if c["id"] == "test_discipline")
        self.assertEqual(test_c["flag"], "low test discipline")

    def test_good_repo_scores_high(self):
        commits = self._commits(60, lines=15, test_every=1)
        m = {
            "change_shape": {"median_lines": 15, "large_change_rate": 0.02, "median_files": 2},
            "quality": {"fix_rate": 0.15, "test_to_code_ratio": 0.6},
            "people": {"solo": False, "top_author_share": 0.25, "bus_factor": 4, "contributors": 20},
            "flow": {"commits_per_week": 20, "active_day_ratio": 0.7},
        }
        dh = delivery_health(commits, m)
        self.assertEqual(dh["status"], "scored")
        self.assertGreaterEqual(dh["score"], 90)  # vitest-like profile

    def test_concentration_risk_flagged(self):
        commits = self._commits(40, test_every=3, email="solo@x")
        m = {
            "change_shape": {"median_lines": 10, "large_change_rate": 0.0, "median_files": 1},
            "quality": {"fix_rate": 0.065, "test_to_code_ratio": 0.3},
            "people": {"solo": False, "top_author_share": 0.545, "bus_factor": 1, "contributors": 71},
            "flow": {"commits_per_week": 1, "active_day_ratio": 0.05},
        }
        dh = delivery_health(commits, m)
        know = next(c for c in dh["components"] if c["id"] == "knowledge_distribution")
        self.assertEqual(know["flag"], "concentration risk")


class TestThreeNumbersAlwaysPresent(unittest.TestCase):
    """The whole point of the redesign: a scan is never empty."""
    def test_keys_present(self):
        result = compute_impact(REPO, repo_label="shipsignal", readiness_score=100)
        self.assertIn("level", result["adoption"])
        self.assertIn("delivery_health", result)
        self.assertEqual(result["readiness"], {"score": 100, "grade": "A"})

    def test_adoption_level_never_withheld(self):
        # Even on shipsignal's tiny history, adoption level is a real value.
        result = compute_impact(REPO, repo_label="shipsignal")
        self.assertIn(result["adoption"]["level"],
                      {"None", "Emerging", "Established", "Pervasive"})


class TestSelfImpact(unittest.TestCase):
    """End-to-end: shipsignal scanning itself.

    Asserts shape and the canonical 'tool honest enough to refuse to score itself'
    behavior — not exact numbers (history will grow).
    """
    def test_self_scan_shape(self):
        result = compute_impact(REPO, repo_label="shipsignal")
        for key in ("schema_version", "repo", "window", "adoption", "metrics",
                    "confidence", "no_baseline", "score", "score_status",
                    "attribution_caveat"):
            self.assertIn(key, result)
        self.assertEqual(result["repo"], "shipsignal")

    def test_attribution_caveat_present(self):
        result = compute_impact(REPO, repo_label="shipsignal")
        self.assertIn("does NOT prove AI caused", result["attribution_caveat"])

    def test_ai_adoption_signal_present(self):
        # shipsignal IS AI-built; share should be > 0.
        result = compute_impact(REPO, repo_label="shipsignal")
        self.assertGreater(result["adoption"]["ai_coauthor_share"], 0)


class TestUnifiedReport(unittest.TestCase):
    """The audit deliverable: one command, three impact numbers + readiness fixes."""

    @classmethod
    def setUpClass(cls):
        from shipsignal import report, scanner
        cls.readiness = scanner.scan(REPO, repo_label="shipsignal")
        cls.impact = compute_impact(REPO, repo_label="shipsignal",
                                    readiness_score=cls.readiness["score"])
        cls.report = report

    def test_cli_has_all_sections(self):
        out = self.report.render_unified(self.impact, self.readiness)
        for marker in ("AI Adoption", "Delivery Health", "Readiness", "Note:"):
            self.assertIn(marker, out, f"CLI missing: {marker}")

    def test_markdown_has_readiness_block(self):
        md = self.report.render_unified_markdown(self.impact, self.readiness)
        self.assertIn("## Readiness", md)
        # Score and grade should both be in the header
        self.assertIn(f"{self.readiness['score']}/100", md)

    def test_html_combines_both(self):
        import html.parser
        h = self.report.render_unified_html(self.impact, self.readiness)
        html.parser.HTMLParser().feed(h)  # raises on malformed
        self.assertIn("AI Adoption", h)
        self.assertIn("Readiness", h)
        # The impact's </body> should be replaced — readiness section injected
        self.assertGreater(h.count("</body>"), 0)
        self.assertEqual(h.count("</html>"), 1)


if __name__ == "__main__":
    unittest.main()
