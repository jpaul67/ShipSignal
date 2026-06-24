"""Impact-lens unit tests (stdlib unittest)."""
import unittest
from datetime import date, timedelta
from pathlib import Path

from shipsignal import impact
from shipsignal.impact import (
    Commit,
    MIN_CONTRIBUTORS_FOR_BREADTH,
    _BREADTH_ALLOWED_KEYS,
    adoption_level,
    assess_confidence,
    baseline_gate,
    compute_breadth,
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


class TestBotDetection(unittest.TestCase):
    def test_maintenance_bots(self):
        for email in [
            "49699333+dependabot[bot]@users.noreply.github.com",
            "29139614+renovate[bot]@users.noreply.github.com",
            "github-actions[bot]@users.noreply.github.com",
            "snyk-bot@snyk.io",
        ]:
            c = _c(email=email)
            self.assertTrue(c.is_maintenance_bot, email)
            self.assertFalse(c.is_ai_agent, email)
            self.assertFalse(c.ai_authored, email)   # maintenance bots are NOT AI dev

    def test_ai_agent_bots_count_as_ai(self):
        for email, label in [
            ("159125892+gpt-engineer-app[bot]@users.noreply.github.com", "GPT-Engineer"),
            ("devin-ai-integration[bot]@users.noreply.github.com", "Devin"),
            ("copilot-swe-agent[bot]@users.noreply.github.com", "Copilot"),
        ]:
            c = _c(email=email)
            self.assertTrue(c.is_ai_agent, email)
            self.assertFalse(c.is_maintenance_bot, email)
            self.assertTrue(c.ai_authored, email)     # agent commits ARE AI dev
            self.assertEqual(c.ai_agent_label, label)
            self.assertIn(label, c.ai_tools)

    def test_humans_not_flagged(self):
        for email in [
            "jane@example.com",
            "abbott@example.com",            # 'abbott' must not match 'bot'
            "robotics-team@example.com",     # 'robot' must not match '[bot]'
            "claude.dupont@company.com",     # human named Claude, no [bot] -> not an agent
        ]:
            c = _c(email=email)
            self.assertFalse(c.is_maintenance_bot, email)
            self.assertFalse(c.is_ai_agent, email)


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


class TestBaselineGate(unittest.TestCase):
    """The before/after delta needs enough commits AND enough post-adoption TIME."""

    def test_too_few_commits(self):
        ok, reason = baseline_gate(n_baseline=5, n_current=30, current_weeks=12)
        self.assertFalse(ok)
        self.assertIn("need", reason)

    def test_short_post_adoption_window_withholds(self):
        # juglr's failure mode: plenty of commits, but a 3-week tail burst.
        ok, reason = baseline_gate(n_baseline=30, n_current=25, current_weeks=3.1)
        self.assertFalse(ok)
        self.assertIn("too short", reason)

    def test_earns_when_both_clear(self):
        ok, reason = baseline_gate(n_baseline=30, n_current=30, current_weeks=10)
        self.assertTrue(ok)
        self.assertIsNone(reason)

    def test_boundary_exactly_min_weeks(self):
        ok, _ = baseline_gate(n_baseline=20, n_current=20, current_weeks=6.0)
        self.assertTrue(ok)


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


# --- Feature C: team-level AI-adoption BREADTH (aggregate only) ------------


def _human(email: str, ai: bool = False, date_str: str = "2026-01-01") -> Commit:
    trailers = ["Co-Authored-By: Claude <c@anthropic.com>"] if ai else []
    return _c(email=email, date_str=date_str, trailers=trailers)


class TestBreadthStructuralGuarantee(unittest.TestCase):
    """The hard non-goal: breadth output structurally cannot leak per-person data."""

    def test_allowed_keys_only_when_scored(self):
        commits = [_human(f"dev{i}@ex.com", ai=(i % 2 == 0)) for i in range(4)]
        out = compute_breadth(commits)
        self.assertEqual(out["status"], "scored")
        # Every key in the output must be in the explicit allow-list — any
        # extra key risks leaking an identity field in a future refactor.
        extras = set(out.keys()) - _BREADTH_ALLOWED_KEYS
        self.assertEqual(extras, set(), f"unexpected keys in breadth: {extras}")

    def test_allowed_keys_only_when_na(self):
        out = compute_breadth([_human("solo@ex.com")])
        self.assertEqual(out["status"], "n/a")
        extras = set(out.keys()) - _BREADTH_ALLOWED_KEYS
        self.assertEqual(extras, set())

    def test_no_email_in_values(self):
        # Strings in the output must NOT contain author identifiers.
        commits = [_human("alice@ex.com", ai=True), _human("bob@ex.com"),
                   _human("carol@ex.com", ai=True), _human("dave@ex.com")]
        out = compute_breadth(commits)
        joined = " ".join(str(v) for v in out.values() if v is not None)
        for email in ("alice", "bob", "carol", "dave", "ex.com"):
            self.assertNotIn(email, joined, f"{email} appears in breadth output")


class TestBreadthComputation(unittest.TestCase):
    def test_na_below_threshold(self):
        # 2 contributors — too few.
        commits = [_human("a@x", ai=True), _human("b@x")]
        out = compute_breadth(commits)
        self.assertEqual(out["status"], "n/a")
        self.assertEqual(out["active_contributors"], 2)
        self.assertLess(out["active_contributors"], MIN_CONTRIBUTORS_FOR_BREADTH)
        self.assertIsNone(out["breadth_pct"])

    def test_aggregate_only(self):
        # 4 humans, 2 with AI: breadth 50%.
        commits = [
            _human("a@x", ai=True), _human("a@x", ai=True),  # one human, two commits
            _human("b@x", ai=True),
            _human("c@x"),
            _human("d@x"),
        ]
        out = compute_breadth(commits)
        self.assertEqual(out["status"], "scored")
        self.assertEqual(out["active_contributors"], 4)
        self.assertEqual(out["ai_contributors"], 2)
        self.assertEqual(out["breadth_pct"], 50.0)

    def test_ai_agent_bot_not_counted_as_contributor(self):
        # AI-agent bot commits shouldn't inflate either the active count or
        # the AI count (a bot is automation, not a human adopter).
        commits = [
            _c(email="gpt-engineer[bot]@users.noreply.github.com", date_str="2026-01-01"),
            _human("alice@x", ai=True),
            _human("bob@x"),
            _human("carol@x"),
        ]
        out = compute_breadth(commits)
        self.assertEqual(out["active_contributors"], 3)
        self.assertEqual(out["ai_contributors"], 1)

    def test_note_always_present(self):
        for commits in ([_human("a@x")],
                        [_human(f"d{i}@x", ai=(i == 0)) for i in range(3)]):
            out = compute_breadth(commits)
            self.assertIn("does not score individuals", out["note"])


class TestBreadthTrend(unittest.TestCase):
    def test_growing(self):
        # First half: 1 of 3 humans uses AI. Second half: 3 of 3.
        commits = (
            [_human("a@x", ai=True, date_str="2026-01-05"),
             _human("b@x", date_str="2026-01-06"),
             _human("c@x", date_str="2026-01-07")]
            + [_human("a@x", ai=True, date_str="2026-04-05"),
               _human("b@x", ai=True, date_str="2026-04-06"),
               _human("c@x", ai=True, date_str="2026-04-07")]
        )
        out = compute_breadth(commits)
        self.assertEqual(out["trend"], "growing")

    def test_flat(self):
        # Same breadth in both halves.
        commits = (
            [_human("a@x", ai=True, date_str="2026-01-05"),
             _human("b@x", date_str="2026-01-06"),
             _human("c@x", date_str="2026-01-07")]
            + [_human("a@x", ai=True, date_str="2026-04-05"),
               _human("b@x", date_str="2026-04-06"),
               _human("c@x", date_str="2026-04-07")]
        )
        out = compute_breadth(commits)
        self.assertEqual(out["trend"], "flat")

    def test_unknown_below_floor(self):
        # 2 contributors — trend can't be computed (below the floor).
        commits = [_human("a@x", ai=True, date_str="2026-01-05"),
                   _human("b@x", date_str="2026-04-05")]
        out = compute_breadth(commits)
        self.assertEqual(out["trend"], None)  # n/a path doesn't compute trend


class TestBreadthInResult(unittest.TestCase):
    def test_self_impact_includes_breadth(self):
        result = compute_impact(REPO, repo_label="shipsignal")
        self.assertIn("breadth", result.get("adoption", {}))
        br = result["adoption"]["breadth"]
        # Structural again — at every entry point.
        extras = set(br.keys()) - _BREADTH_ALLOWED_KEYS
        self.assertEqual(extras, set())


# --- Squash-merge detect-and-disclose ---------------------------------------


class TestSquashDetection(unittest.TestCase):
    """Detect a squash workflow that undercounts trailer-based adoption."""

    def _commits(self, n, squash_frac, ai=False):
        out = []
        n_squash = int(n * squash_frac)
        for i in range(n):
            subj = f"feat: thing (#{i})" if i < n_squash else f"feat: thing {i}"
            trailers = ["Co-Authored-By: Claude <c@anthropic.com>"] if ai else []
            out.append(_c(subject=subj, trailers=trailers))
        return out

    def test_squashy_low_adoption_is_suspected(self):
        out = impact._squash_workflow_suspected(self._commits(20, 0.8), level="None")
        self.assertTrue(out["suspected"])
        self.assertEqual(out["source"], "detected")
        self.assertGreaterEqual(out["subject_frac"], 0.30)

    def test_control_repo_not_suspected(self):
        out = impact._squash_workflow_suspected(self._commits(20, 0.0), level="None")
        self.assertFalse(out["suspected"])
        self.assertIsNone(out["source"])

    def test_below_floor_not_suspected(self):
        # 20% squash-style subjects is below the 0.30 floor.
        out = impact._squash_workflow_suspected(self._commits(20, 0.2), level="Emerging")
        self.assertFalse(out["suspected"])

    def test_pervasive_not_caveated(self):
        # A squashy repo that already reads Pervasive needs no caveat — the
        # measured number is already telling the true story.
        out = impact._squash_workflow_suspected(self._commits(20, 0.8), level="Pervasive")
        self.assertFalse(out["suspected"])

    def test_override_forces_flag_even_without_fingerprint(self):
        out = impact._squash_workflow_suspected(self._commits(20, 0.0),
                                                level="Established", override=True)
        self.assertTrue(out["suspected"])
        self.assertEqual(out["source"], "declared")


class TestSquashCaveatRender(unittest.TestCase):
    """The caveat is additive — it never changes the displayed number — and it
    surfaces in every render format. Uses the --squash override against the real
    repo (shipsignal's own subjects aren't squash-style, so it's a negative control)."""

    @classmethod
    def setUpClass(cls):
        from shipsignal import report
        cls.report = report
        cls.normal = compute_impact(REPO, repo_label="shipsignal")
        cls.forced = compute_impact(REPO, repo_label="shipsignal", squash_override=True)

    def test_override_is_additive_only(self):
        self.assertFalse(self.normal["adoption"]["squash_suspected"])  # negative control
        self.assertTrue(self.forced["adoption"]["squash_suspected"])
        # The measured signal is byte-for-byte identical with and without the flag.
        self.assertEqual(self.normal["adoption"]["ai_coauthor_share"],
                         self.forced["adoption"]["ai_coauthor_share"])
        self.assertEqual(self.normal["adoption"]["level"],
                         self.forced["adoption"]["level"])

    def test_caveat_in_cli(self):
        self.assertIn("squash", self.report.render_impact(self.forced).lower())
        self.assertNotIn("floor (squash)", self.report.render_impact(self.normal))

    def test_caveat_in_markdown(self):
        self.assertIn("squash-merge workflow",
                      self.report.render_impact_markdown(self.forced).lower())

    def test_caveat_in_html_wellformed(self):
        import html.parser
        h = self.report.render_impact_html(self.forced)
        html.parser.HTMLParser().feed(h)  # raises on malformed markup
        self.assertIn("squash", h.lower())


if __name__ == "__main__":
    unittest.main()
