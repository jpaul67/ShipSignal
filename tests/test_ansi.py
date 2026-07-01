"""ANSI color helper + CLI-renderer color plumbing (stdlib unittest)."""
import io
import os
import unittest
from pathlib import Path
from unittest import mock

from shipsignal import ansi, impact, report, scanner

REPO = Path(__file__).resolve().parent.parent


class _FakeTTY(io.StringIO):
    def isatty(self):
        return True


class TestResolveEnabled(unittest.TestCase):
    def test_no_color_flag_always_wins(self):
        with mock.patch.dict(os.environ, {"FORCE_COLOR": "1"}, clear=False):
            self.assertFalse(ansi.resolve_enabled(no_color_flag=True))

    def test_no_color_env_disables(self):
        with mock.patch.dict(os.environ, {"NO_COLOR": "1"}, clear=False):
            self.assertFalse(ansi.resolve_enabled(no_color_flag=False, stream=_FakeTTY()))

    def test_non_tty_disabled_by_default(self):
        env = {k: v for k, v in os.environ.items() if k not in ("FORCE_COLOR", "NO_COLOR", "TERM")}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertFalse(ansi.resolve_enabled(stream=io.StringIO()))

    def test_force_color_enables_without_tty(self):
        # FORCE_COLOR bypasses the isatty/VT probe entirely — it means "emit
        # codes regardless" (CI log capture, screenshot tooling).
        env = {k: v for k, v in os.environ.items() if k not in ("NO_COLOR", "TERM")}
        env["FORCE_COLOR"] = "1"
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertTrue(ansi.resolve_enabled(stream=io.StringIO()))

    def test_dumb_term_disables(self):
        env = {k: v for k, v in os.environ.items() if k not in ("NO_COLOR", "FORCE_COLOR")}
        env["TERM"] = "dumb"
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertFalse(ansi.resolve_enabled(stream=_FakeTTY()))

    def test_tty_enabled_by_default(self):
        # Isolates the decision logic (isatty/env) from whether Windows VT
        # processing actually succeeds on this machine's console — that's a
        # separate, environment-dependent concern (_win_vt_enabled).
        env = {k: v for k, v in os.environ.items() if k not in ("NO_COLOR", "FORCE_COLOR", "TERM")}
        with mock.patch.dict(os.environ, env, clear=True), \
             mock.patch.object(ansi, "_win_vt_enabled", return_value=True):
            self.assertTrue(ansi.resolve_enabled(stream=_FakeTTY()))

    def test_vt_enable_failure_disables_color_even_on_a_tty(self):
        with mock.patch.object(ansi, "_win_vt_enabled", return_value=False):
            self.assertFalse(ansi.resolve_enabled(stream=_FakeTTY()))


class TestPaintHelpers(unittest.TestCase):
    def test_disabled_returns_plain_text(self):
        self.assertEqual(ansi.bold("x", False), "x")
        self.assertEqual(ansi.grade("x", "A", False), "x")
        self.assertEqual(ansi.warn("x", False), "x")

    def test_enabled_wraps_and_strips_cleanly(self):
        colored = ansi.bold(ansi.grade("x", "F", True), True)
        self.assertNotEqual(colored, "x")
        self.assertEqual(ansi.strip(colored), "x")

    def test_unknown_grade_falls_back_to_plain(self):
        self.assertEqual(ansi.grade("x", "Z", True), "x")


class TestRendererColorPlumbing(unittest.TestCase):
    """Color is off by default; forcing it on must only ADD escape codes —
    stripping them must reproduce the plain-text output exactly."""

    def test_readiness_render_default_has_no_escapes(self):
        result = scanner.scan(REPO, repo_label="shipsignal")
        self.assertNotIn("\033[", report.render(result))

    def test_readiness_render_color_strips_back_to_plain(self):
        result = scanner.scan(REPO, repo_label="shipsignal")
        plain = report.render(result, color=False)
        colored = report.render(result, color=True)
        self.assertIn("\033[", colored)
        self.assertEqual(ansi.strip(colored), plain)

    def test_impact_render_default_has_no_escapes(self):
        result = impact.compute_impact(REPO, repo_label="shipsignal")
        self.assertNotIn("\033[", report.render_impact(result))

    def test_impact_render_color_strips_back_to_plain(self):
        result = impact.compute_impact(REPO, repo_label="shipsignal")
        plain = report.render_impact(result, color=False)
        colored = report.render_impact(result, color=True)
        self.assertIn("\033[", colored)
        self.assertEqual(ansi.strip(colored), plain)

    def test_unified_render_color_strips_back_to_plain(self):
        readiness = scanner.scan(REPO, repo_label="shipsignal")
        imp = impact.compute_impact(REPO, repo_label="shipsignal",
                                    readiness_score=readiness["score"])
        plain = report.render_unified(imp, readiness, color=False)
        colored = report.render_unified(imp, readiness, color=True)
        self.assertIn("\033[", colored)
        self.assertEqual(ansi.strip(colored), plain)


if __name__ == "__main__":
    unittest.main()
