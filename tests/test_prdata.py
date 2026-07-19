"""PR-data loader tests (Package D): parsing + validation of the exported
`gh pr list ... --json number,mergeCommit,mergedAt,commits` payload.

Fixtures are real captured payloads (trimmed) plus synthetic edge cases:
  prdata_jest.json     — DROP repo (jest): squash dropped the trailer locally,
                         PRs #16237 (Claude) & #16182 (copilot-swe-agent) recoverable
  prdata_calcom.json   — RETAIN repo (cal.com): Claude co-authors present in PR data
  prdata_null_merge.json / _empty / _malformed / _wrong_shape — edge cases
"""
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from shipsignal import prdata
from shipsignal.prdata import PRAuthor, PRDataError, load_pr_data

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class TestLoadRealFixtures(unittest.TestCase):
    def test_jest_drop_fixture(self):
        data = load_pr_data(FIXTURES / "prdata_jest.json")
        self.assertEqual(len(data.records), 3)
        pr = data.by_number[16237]
        # SHA-join key: the exact single-parent squash commit whose local
        # message carries NO trailer (verified against jest main).
        self.assertEqual(pr.merge_oid, "1da1579e89650f539130aa2b471f5c99a87e9e25")
        self.assertEqual(pr.merged_at, date(2026, 6, 21))
        emails = {a.email for a in pr.authors}
        self.assertIn("noreply@anthropic.com", emails)  # Claude, recoverable

    def test_jest_copilot_bot_recoverable(self):
        # The bot marker lives in the *name* (`copilot-swe-agent[bot]`), not the
        # login (`Copilot`); either way the identity tokenizes to include
        # "copilot", so the task-2 matcher recovers it via the synthesized trailer.
        data = load_pr_data(FIXTURES / "prdata_jest.json")
        blobs = [(a.name + " " + a.email + " " + a.login).lower()
                 for a in data.by_number[16182].authors]
        self.assertTrue(any("copilot" in b for b in blobs))
        self.assertTrue(any(a.name == "copilot-swe-agent[bot]"
                            for a in data.by_number[16182].authors))

    def test_calcom_retain_fixture_has_claude(self):
        data = load_pr_data(FIXTURES / "prdata_calcom.json")
        anthropic = [a for r in data.records for a in r.authors
                     if "anthropic" in a.email.lower()]
        self.assertTrue(anthropic, "expected Claude co-authors in cal.com fixture")

    def test_by_merge_oid_indexes_only_non_null(self):
        data = load_pr_data(FIXTURES / "prdata_jest.json")
        self.assertTrue(all(oid for oid in data.by_merge_oid))
        self.assertEqual(len(data.by_merge_oid), 3)

    def test_authors_deduped_across_commits(self):
        # jest #16182 repeats the same authors across 10 commits; distinct set is small.
        data = load_pr_data(FIXTURES / "prdata_jest.json")
        authors = data.by_number[16182].authors
        keys = [a.login.lower() or a.email.lower() for a in authors]
        self.assertEqual(len(keys), len(set(keys)), "authors must be deduped")


class TestEdgeCases(unittest.TestCase):
    def test_null_merge_commit(self):
        data = load_pr_data(FIXTURES / "prdata_null_merge.json")
        pr = data.by_number[999]
        self.assertIsNone(pr.merge_oid)
        self.assertNotIn(None, data.by_merge_oid)  # excluded from the SHA index
        self.assertIn(999, data.by_number)  # still reachable by number (subject fallback)
        self.assertIn("noreply@anthropic.com", {a.email for a in pr.authors})

    def test_empty_list_is_valid(self):
        data = load_pr_data(FIXTURES / "prdata_empty.json")
        self.assertEqual(data.records, [])
        self.assertEqual(data.by_merge_oid, {})

    def test_malformed_json_raises_with_recipe_hint(self):
        with self.assertRaises(PRDataError) as ctx:
            load_pr_data(FIXTURES / "prdata_malformed.json")
        self.assertIn("gh pr list", str(ctx.exception))

    def test_wrong_shape_object_raises(self):
        with self.assertRaises(PRDataError) as ctx:
            load_pr_data(FIXTURES / "prdata_wrong_shape.json")
        self.assertIn("not an array", str(ctx.exception))

    def test_missing_file_raises(self):
        with self.assertRaises(PRDataError) as ctx:
            load_pr_data(FIXTURES / "does_not_exist.json")
        self.assertIn("not found", str(ctx.exception))

    def test_list_of_non_pr_items_raises(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bad.json"
            p.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
            with self.assertRaises(PRDataError):
                load_pr_data(p)

    def test_stray_non_pr_element_skipped_not_fatal(self):
        # A valid PR plus a junk element: keep the real record, drop the junk.
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "mixed.json"
            p.write_text(json.dumps([
                "junk",
                {"number": 7, "mergeCommit": {"oid": "deadbeef"}, "mergedAt": None,
                 "commits": [{"oid": "c1", "authors": [
                     {"name": "Claude", "email": "noreply@anthropic.com", "login": ""}]}]},
            ]), encoding="utf-8")
            data = load_pr_data(p)
            self.assertEqual([r.number for r in data.records], [7])

    def test_bad_merged_at_degrades_to_none(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "baddate.json"
            p.write_text(json.dumps([
                {"number": 1, "mergeCommit": None, "mergedAt": "not-a-date",
                 "commits": []},
            ]), encoding="utf-8")
            data = load_pr_data(p)
            self.assertIsNone(data.by_number[1].merged_at)


class TestPRAuthor(unittest.TestCase):
    def test_as_trailer_synthesizes_coauthor_form(self):
        a = PRAuthor(name="Claude", email="noreply@anthropic.com")
        self.assertEqual(a.as_trailer(),
                         "Co-authored-by: Claude <noreply@anthropic.com>")

    def test_export_command_constant_matches_recipe(self):
        self.assertIn("--json number,mergeCommit,mergedAt,commits",
                      prdata.EXPORT_COMMAND)


if __name__ == "__main__":
    unittest.main()
