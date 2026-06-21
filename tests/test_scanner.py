"""Smoke + unit tests (stdlib unittest — no third-party dep)."""
import tempfile
import unittest
from pathlib import Path

from shipsignal import scanner
from shipsignal.modules import _parse_pnpm_packages, _code_dirs, AGENT_BASENAMES, is_agent_file
from shipsignal.detectors import _drifted, _skip_link, _agent_usefulness, _best_usefulness
from shipsignal.scoring import score_scan, grade_for
from shipsignal.setupcheck import _has_arch_doc, ARCH_MODULE_THRESHOLD, detect_setup

REPO = Path(__file__).resolve().parent.parent


class TestSelfScan(unittest.TestCase):
    def test_scans_self(self):
        result = scanner.scan(REPO, repo_label="shipsignal")
        self.assertIn("score", result)
        self.assertTrue(0 <= result["score"] <= 100)
        self.assertTrue(any(m["path"] == "." for m in result["modules"]))
        # the package dir should be detected as a module
        self.assertTrue(any(m["path"] == "shipsignal" for m in result["modules"]))


class TestPnpmParse(unittest.TestCase):
    def test_parse(self):
        text = "packages:\n  - 'packages/*'\n  - docs\n  - '!**/test/**'\nother: 1\n"
        self.assertEqual(_parse_pnpm_packages(text), ["packages/*", "docs", "!**/test/**"])


class TestDrift(unittest.TestCase):
    def test_module_doc_drift(self):
        self.assertTrue(_drifted("2026-01-01", "2026-08-01", gentle=False))   # >180d
        self.assertFalse(_drifted("2026-05-01", "2026-06-01", gentle=False))  # 31d

    def test_agent_files_are_gentle(self):
        # ~8 months stale: a problem for a module README, fine for an agent file
        self.assertTrue(_drifted("2026-01-01", "2026-09-01", gentle=False))
        self.assertFalse(_drifted("2026-01-01", "2026-09-01", gentle=True))


class TestSkipLink(unittest.TestCase):
    def test_guards(self):
        for s in ["https://x.com", "#anchor", "/abs/path", "C:\\Users\\x", "mailto:a@b.c"]:
            self.assertTrue(_skip_link(s), s)
        self.assertFalse(_skip_link("../src/foo.js"))


class TestScoring(unittest.TestCase):
    def test_small_repo_agent_is_na(self):
        m = dict(has_root_readme=True, root_readme_substantial=True, is_small_repo=True,
                 code_count=5, has_agent_file=False, has_root_agent_file=False,
                 modules_total=1, modules_covered=1, broken_links=0, drift_count=0,
                 is_git=True, mcp_present=False, setup_score_frac=1.0)
        score, grade, cats = score_scan(m)
        agent = next(c for c in cats if c.id == "agent_instructions")
        self.assertEqual(agent.status, "n/a")
        self.assertEqual(score, 100)  # not punished for missing agent file

    def test_grade_bands(self):
        self.assertEqual(grade_for(95), "A")
        self.assertEqual(grade_for(27), "F")


class TestSetup(unittest.TestCase):
    def test_setup_category_present(self):
        r = scanner.scan(REPO, repo_label="shipsignal")
        setup = next((c for c in r["categories"] if c["id"] == "setup_tooling"), None)
        self.assertIsNotNone(setup)
        self.assertEqual(setup["status"], "scored")

    def test_detect_setup_frac_range(self):
        from shipsignal import modules as mod
        from shipsignal.setupcheck import detect_setup
        files, _ = mod.list_files(REPO)
        _findings, m = detect_setup(REPO, files, mcp_present=False)
        self.assertTrue(0.0 <= m["setup_score_frac"] <= 1.0)


# --- Feature A: agent-context enrichment -----------------------------------


class TestAgentFileDetection(unittest.TestCase):
    """A1: broaden agent-file recognition."""

    def test_new_basenames_detected(self):
        # .clinerules is the one new prose-format added in A1.
        self.assertIn(".clinerules", AGENT_BASENAMES)
        self.assertTrue(is_agent_file(".clinerules"))
        self.assertTrue(is_agent_file("subdir/.clinerules"))

    def test_existing_set_preserved(self):
        for name in (
            "claude.md", "agents.md", "gemini.md", "copilot-instructions.md",
            ".cursorrules", ".windsurfrules",
        ):
            self.assertIn(name, AGENT_BASENAMES, name)

    def test_mcp_json_not_in_agent_set(self):
        # .mcp.json is intentionally excluded — covered by setupcheck.mcp_resolves
        # and would fail the prose-based usefulness heuristic confusingly.
        self.assertNotIn(".mcp.json", AGENT_BASENAMES)

    def test_nested_cursor_rules(self):
        self.assertTrue(is_agent_file(".cursor/rules/python.md"))
        self.assertTrue(is_agent_file("packages/foo/.cursor/rules/x.md"))


class TestAgentUsefulness(unittest.TestCase):
    """A2: usefulness heuristic — actionable / actionable_no_structure / thin."""

    def test_actionable_full(self):
        text = (
            "# Project\n\n## Commands\n\n```bash\npytest\nnpm test\n```\n\n"
            "## Architecture\n\nThings live in src/."
        )
        self.assertEqual(_agent_usefulness(text), "actionable")

    def test_actionable_via_token_only(self):
        # Plain prose mentioning concrete invocations + a doc link counts.
        text = "Run `pytest` for tests, `npm run build` to build. See [docs](docs/foo.md)."
        self.assertEqual(_agent_usefulness(text), "actionable")

    def test_actionable_no_structure(self):
        # Commands present, no structure pointer.
        text = "## Build\n\n```sh\ncargo test\ncargo build\n```\n"
        self.assertEqual(_agent_usefulness(text), "actionable_no_structure")

    def test_thin_no_commands(self):
        # Prose only — no command tokens, no commands heading-with-fence.
        text = (
            "# Agent Guide\n\nThis project is a library. Please be polite to the "
            "code and respect existing conventions when contributing."
        )
        self.assertEqual(_agent_usefulness(text), "thin")

    def test_thin_too_short(self):
        self.assertEqual(_agent_usefulness("hi"), "thin")
        self.assertEqual(_agent_usefulness(""), "thin")

    def test_false_positive_fenced_heading(self):
        # A "## Build" inside a fenced example shouldn't count as a heading
        # for the commands-heading heuristic. Without other signals it's thin.
        text = (
            "# Style guide\n\nUse h2 for sections, e.g.:\n\n"
            "```\n## Build\n```\n\nThat's all."
        )
        self.assertEqual(_agent_usefulness(text), "thin")

    def test_best_usefulness_ranking(self):
        self.assertEqual(
            _best_usefulness(["thin", "actionable", "actionable_no_structure"]),
            "actionable",
        )
        self.assertEqual(_best_usefulness(["thin", "thin"]), "thin")
        self.assertIsNone(_best_usefulness([]))


class TestAgentInstructionScoring(unittest.TestCase):
    """A2: scoring uses the usefulness grade within the existing 15 pts."""

    def _metrics(self, **kw):
        base = dict(
            has_root_readme=True, root_readme_substantial=True, is_small_repo=False,
            code_count=100, has_agent_file=True, has_root_agent_file=True,
            agent_usefulness_root="actionable", agent_usefulness_nested=None,
            modules_total=1, modules_covered=1, broken_links=0, drift_count=0,
            links_checked=10, docs_checked=1,
            is_git=True, mcp_present=False, setup_score_frac=1.0,
        )
        base.update(kw)
        return base

    def _agent_pts(self, **kw):
        _, _, cats = score_scan(self._metrics(**kw))
        return next(c for c in cats if c.id == "agent_instructions").points

    def test_root_actionable_full_credit(self):
        self.assertEqual(self._agent_pts(agent_usefulness_root="actionable"), 15.0)

    def test_root_thin_partial_credit(self):
        # Present at root but no commands — dinged within the 15-pt cap.
        self.assertEqual(self._agent_pts(agent_usefulness_root="thin"), 9.0)

    def test_root_no_structure_middle(self):
        self.assertEqual(
            self._agent_pts(agent_usefulness_root="actionable_no_structure"), 11.0
        )

    def test_nested_only_actionable_less_than_root_actionable(self):
        nested = self._agent_pts(
            has_root_agent_file=False, agent_usefulness_root=None,
            agent_usefulness_nested="actionable",
        )
        self.assertEqual(nested, 9.0)
        # Nested-only should never beat root-thin? Actually root-thin (9.0) ==
        # nested-actionable (9.0). Both signal real but partial context.
        self.assertEqual(nested, self._agent_pts(agent_usefulness_root="thin"))

    def test_absent_zero(self):
        self.assertEqual(
            self._agent_pts(has_agent_file=False, has_root_agent_file=False,
                            agent_usefulness_root=None, agent_usefulness_nested=None),
            0.0,
        )


# --- Feature A3: architecture-doc check ------------------------------------


class TestArchitectureDoc(unittest.TestCase):
    def _scratch_repo(self, files: dict[str, str]) -> Path:
        d = Path(tempfile.mkdtemp())
        for path, content in files.items():
            full = d / path
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(content, encoding="utf-8")
        return d

    def test_detects_root_architecture_md(self):
        d = self._scratch_repo({"ARCHITECTURE.md": "# Architecture\n\n..."})
        self.assertTrue(_has_arch_doc(d, {"architecture.md"}, ["ARCHITECTURE.md"]))

    def test_detects_docs_with_content(self):
        body = "# Overview\n\n" + ("Substantial content. " * 60)
        d = self._scratch_repo({"docs/overview.md": body})
        self.assertTrue(_has_arch_doc(d, set(), ["docs/overview.md"]))

    def test_ignores_thin_docs(self):
        d = self._scratch_repo({"docs/notes.md": "# Notes\n\nthin"})
        self.assertFalse(_has_arch_doc(d, set(), ["docs/notes.md"]))

    def test_detects_readme_architecture_section(self):
        body = (
            "# Project\n\nIntro.\n\n## Architecture\n\n"
            + ("Real architecture content explaining where modules live. " * 6)
            + "\n\n## License\n\nMIT.\n"
        )
        d = self._scratch_repo({"README.md": body})
        self.assertTrue(_has_arch_doc(d, {"readme.md"}, ["README.md"]))

    def test_ignores_readme_with_thin_section(self):
        body = "# Project\n\n## Architecture\n\nTBD.\n\n## License\n\nMIT.\n"
        d = self._scratch_repo({"README.md": body})
        self.assertFalse(_has_arch_doc(d, {"readme.md"}, ["README.md"]))

    def test_inapplicable_below_module_threshold(self):
        """The setup check should NOT include architecture_doc as a deficit on a
        small (< ARCH_MODULE_THRESHOLD) repo, so single-module utilities aren't
        nagged for an ARCHITECTURE.md."""
        d = self._scratch_repo({"main.py": "print('ok')\n"})
        findings, metrics = detect_setup(
            d, ["main.py"], mcp_present=False, modules_total=1
        )
        self.assertNotIn("architecture_doc", metrics["setup_missing"])
        self.assertNotIn("architecture_doc", metrics["setup_present"])

    def test_applicable_at_or_above_threshold(self):
        d = self._scratch_repo({"main.py": "print('ok')\n"})
        findings, metrics = detect_setup(
            d, ["main.py"], mcp_present=False,
            modules_total=ARCH_MODULE_THRESHOLD,
        )
        # No arch doc present — should appear in setup_missing.
        self.assertIn("architecture_doc", metrics["setup_missing"])


if __name__ == "__main__":
    unittest.main()
