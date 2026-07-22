"""Rendering tests for the AI line-survival section (Package L, slice 4).

The section is gated on ``result["survival"]`` (attached only with --survival, slice
3): absent by default, present when a survival block is attached. These tests build a
real impact result and inject a synthetic survival block so both the scored and the
withheld render paths are exercised without needing a repo that clears the floors.
"""
import copy
import html.parser
import unittest
from pathlib import Path

from shipsignal import report
from shipsignal.impact import compute_impact

REPO = Path(__file__).resolve().parent.parent

_SCORED = {
    "status": "scored", "ai_survival": 0.62, "other_survival": 0.47,
    "buckets": [{"month": "2025-03", "ai_survival": 0.62, "other_survival": 0.47,
                 "ai_lines": 1200, "other_lines": 900}],
    "age_floor_days": 90,
    "coverage": {"ai_commits": 41, "other_commits": 33,
                 "ai_lines": 6100, "other_lines": 4800},
    "sampled": True, "files_blamed": 36, "files_total": 40,
}
_WITHHELD = {"status": "withheld", "reason": "no matched months (test)",
             "coverage": {"ai_commits": 0, "other_commits": 0,
                          "ai_lines": 0, "other_lines": 0},
             "sampled": False, "files_blamed": 5, "files_total": 5}
# The third survival shape (slice 3): requested but no adoption date to age-match
# against — a withheld dict with NO "coverage" key. The renderers must tolerate it.
_WITHHELD_NO_COVERAGE = {"status": "withheld", "reason": "no adoption date detected",
                         "sampled": False, "files_blamed": 0, "files_total": 0}
# A withheld result carrying the calibration UX hint (impact adds this when the repo
# has AI commits but auto-detection found no measurable window).
_WITHHELD_HINTED = {"status": "withheld",
                    "reason": "no matched months (no month has both AI and other "
                              "eligible commits)",
                    "hint": "this repo has AI commits but no measurable survival window "
                            "was found automatically — pass --adoption-date YYYY-MM-DD "
                            "to measure survival from a known adoption point",
                    "sampled": False, "files_blamed": 0, "files_total": 900}


class TestSurvivalRender(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # No survival= here, so the base result carries no survival block.
        cls.base = compute_impact(REPO, repo_label="shipsignal")

    def _with(self, sv):
        r = copy.deepcopy(self.base)
        r["survival"] = sv
        return r

    def _all_formats(self, result):
        return (report.render_impact(result),
                report.render_impact_markdown(result),
                report.render_impact_html(result))

    def test_default_has_no_survival_section(self):
        for out in self._all_formats(self.base):
            self.assertNotIn("line survival", out.lower())

    def test_scored_renders_both_rates(self):
        for out in self._all_formats(self._with(_SCORED)):
            self.assertIn("line survival", out.lower())
            self.assertIn("62", out)
            self.assertIn("47", out)

    def test_withheld_renders_reason(self):
        for out in self._all_formats(self._with(_WITHHELD)):
            self.assertIn("line survival", out.lower())
            self.assertIn("no matched months", out.lower())

    def test_withheld_without_coverage_key_does_not_crash(self):
        # The no-adoption-date shape has no "coverage" — must render, not KeyError.
        for out in self._all_formats(self._with(_WITHHELD_NO_COVERAGE)):
            self.assertIn("line survival", out.lower())
            self.assertIn("no adoption date", out.lower())

    def test_withheld_hint_renders_in_all_formats(self):
        for out in self._all_formats(self._with(_WITHHELD_HINTED)):
            self.assertIn("line survival", out.lower())
            self.assertIn("--adoption-date", out)

    def test_html_parses_all_states(self):
        for sv in (_SCORED, _WITHHELD, _WITHHELD_NO_COVERAGE, _WITHHELD_HINTED):
            html.parser.HTMLParser().feed(report.render_impact_html(self._with(sv)))


if __name__ == "__main__":
    unittest.main()
