"""Glossary copy + self-documentation rendering tests."""
import html.parser
import unittest
from pathlib import Path

from shipsignal import glossary, report, scanner
from shipsignal.impact import compute_impact

REPO = Path(__file__).resolve().parent.parent

# Every key a renderer looks up must exist in the glossary.
REQUIRED_KEYS = [
    "ai_adoption", "delivery_health", "readiness", "before_after", "trajectory",
    "change_size_discipline", "test_discipline", "knowledge_distribution",
    "entry_point", "agent_instructions", "module_coverage", "setup_tooling",
    "doc_integrity", "doc_freshness",
]


class TestGlossary(unittest.TestCase):
    def test_required_keys_present_and_nonempty(self):
        for k in REQUIRED_KEYS:
            self.assertIn(k, glossary.GLOSSARY, k)
            self.assertTrue(glossary.short(k).strip(), f"{k} short")
            self.assertTrue(glossary.tip(k).strip(), f"{k} tip")

    def test_howto_order_keys_valid(self):
        for _name, key in glossary.HOWTO_ORDER:
            self.assertIn(key, glossary.GLOSSARY, key)

    def test_missing_key_is_blank_not_error(self):
        self.assertEqual(glossary.short("nope"), "")
        self.assertEqual(glossary.tip("nope"), "")


class TestSelfDocumentingHtml(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.readiness = scanner.scan(REPO, repo_label="shipsignal")
        cls.impact = compute_impact(REPO, repo_label="shipsignal",
                                    readiness_score=cls.readiness["score"])

    def test_impact_html_has_tooltips_and_howto(self):
        h = report.render_impact_html(self.impact)
        html.parser.HTMLParser().feed(h)            # must parse
        self.assertIn("How to read this", h)        # layer 3
        self.assertIn("class='tip'", h)             # layer 2 tooltips present
        self.assertIn("title=", h)
        # a known tip string appears (escaped HTML still contains the words)
        self.assertIn("preserves co-authors", h)

    def test_unified_html_tooltips_on_readiness_categories(self):
        h = report.render_unified_html(self.impact, self.readiness)
        html.parser.HTMLParser().feed(h)
        self.assertIn("How to read this", h)
        # readiness category names are tooltip'd
        self.assertIn("entry_point", h)

    def test_markdown_has_how_to(self):
        md = report.render_impact_markdown(self.impact)
        self.assertIn("## How to read this", md)


if __name__ == "__main__":
    unittest.main()
