"""Smoke + unit tests (stdlib unittest — no third-party dep)."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from shipsignal import scanner
from shipsignal.modules import _parse_pnpm_packages, _code_dirs, AGENT_BASENAMES, is_agent_file
from shipsignal.detectors import (
    _drifted, _drift_grade, _skip_link, _agent_usefulness, _best_usefulness, _ref_paths,
)
from shipsignal.scoring import score_scan, grade_for
from shipsignal.setupcheck import _has_arch_doc, ARCH_MODULE_THRESHOLD, detect_setup
from shipsignal import gitinfo

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


# --- Feature B: doc tech-debt depth ----------------------------------------


class TestDriftGrade(unittest.TestCase):
    """B4: graded drift — score reflects *how far* behind, not yes/no."""

    def test_fresh_full_credit(self):
        # 31 days lag, threshold 180 → past <= 0 → 1.0
        self.assertEqual(_drift_grade("2026-05-01", "2026-06-01", gentle=False), 1.0)

    def test_indeterminate_dates_full_credit(self):
        # Unparseable dates should not punish — preserves legacy behavior.
        self.assertEqual(_drift_grade("bad", "2026-06-01", gentle=False), 1.0)
        self.assertEqual(_drift_grade("2026-05-01", "", gentle=False), 1.0)

    def test_small_drift_small_ding(self):
        # ~1 month past 180d threshold → 0.85
        self.assertAlmostEqual(_drift_grade("2026-01-01", "2026-08-01", gentle=False), 0.85)

    def test_increasing_lag_drops_grade(self):
        g_small = _drift_grade("2025-01-01", "2025-08-15", gentle=False)  # ~6mo past
        g_big = _drift_grade("2024-01-01", "2026-01-01", gentle=False)    # >12mo past
        self.assertGreater(g_small, g_big)
        self.assertEqual(g_big, 0.0)

    def test_gentle_preserves_for_agent_files(self):
        # 8mo lag: not gentle = drifted; gentle = still fresh
        self.assertLess(_drift_grade("2026-01-01", "2026-09-01", gentle=False), 1.0)
        self.assertEqual(_drift_grade("2026-01-01", "2026-09-01", gentle=True), 1.0)


class TestRefPathsHeuristic(unittest.TestCase):
    """B1: referenced-but-missing — what counts as a checkable path token."""

    def test_path_with_separator_picked_up(self):
        refs = _ref_paths("see `src/legacy/foo.py` for details")
        self.assertIn("src/legacy/foo.py", refs)

    def test_directory_ref_picked_up(self):
        refs = _ref_paths("the [old code](packages/legacy/) used to live here")
        self.assertIn("packages/legacy/", refs)

    def test_bare_filename_ignored(self):
        # Bare names too noisy — output examples, informal mentions, etc.
        refs = _ref_paths("the tool produces `readiness.json` and `impact.json`")
        self.assertEqual(refs, set())

    def test_url_and_anchor_skipped(self):
        refs = _ref_paths("see `https://example.com/x` and `#section`")
        self.assertEqual(refs, set())

    def test_agent_class_pattern_skipped(self):
        # ".cursor/rules" is conventionally a class description, not a path.
        refs = _ref_paths("we detect `.cursor/rules` and `.github/copilot-instructions.md`")
        # Both are class refs — should be skipped to avoid false positives in
        # README/tool-overview docs that describe what's detected.
        self.assertEqual(refs, set())

    def test_prose_with_spaces_skipped(self):
        # PATHLIKE regex already excludes anything with spaces.
        refs = _ref_paths("see `(this is not a path)`")
        self.assertEqual(refs, set())


def _git_init_repo(d: Path):
    """Initialize a tiny git repo with deterministic identity. Returns the dir."""
    env = {"GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@t"}
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=d, check=True, env={**env, "PATH": ""})
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=d, check=True, env={**env, "PATH": ""})
    return env


def _git_commit(d: Path, env: dict, message: str, date: str):
    """Commit all changes with a fixed author + commit date (YYYY-MM-DD)."""
    e = {**env, "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date, "PATH": ""}
    subprocess.run(["git", "add", "-A"], cwd=d, check=True, env=e)
    subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", message], cwd=d, check=True, env=e)


class TestGitInfoHelpers(unittest.TestCase):
    """B helpers: commit_count_for_path, first_commit_date_for_path."""

    def test_commit_count_and_first_date(self):
        d = Path(tempfile.mkdtemp())
        env = _git_init_repo(d)
        (d / "README.md").write_text("v1", encoding="utf-8")
        _git_commit(d, env, "init", "2025-01-15 12:00:00")
        # touch again
        (d / "README.md").write_text("v2", encoding="utf-8")
        _git_commit(d, env, "update", "2026-05-10 12:00:00")

        self.assertEqual(gitinfo.commit_count_for_path(d, "README.md"), 2)
        self.assertEqual(gitinfo.first_commit_date_for_path(d, "README.md"), "2025-01-15")
        # New file added later — first date should be the addition commit.
        (d / "extra.md").write_text("new", encoding="utf-8")
        _git_commit(d, env, "add extra", "2026-06-01 12:00:00")
        self.assertEqual(gitinfo.first_commit_date_for_path(d, "extra.md"), "2026-06-01")
        self.assertGreaterEqual(gitinfo.total_commit_count(d), 3)


class TestDocTechDebtFindings(unittest.TestCase):
    """B1/B2/B3 emit findings without changing the doc_freshness category math."""

    def _build_repo(self) -> tuple[Path, dict]:
        d = Path(tempfile.mkdtemp())
        env = _git_init_repo(d)
        return d, env

    def test_b1_referenced_but_missing(self):
        d, env = self._build_repo()
        (d / "README.md").write_text(
            "# Repo\n\nSee `src/legacy/old.py` for the old impl.\n", encoding="utf-8"
        )
        (d / "main.py").write_text("print('ok')\n", encoding="utf-8")
        _git_commit(d, env, "init", "2026-05-01 12:00:00")
        result = scanner.scan(d, repo_label="t")
        kinds = [f["detector"] for f in result["findings"]]
        self.assertIn("doc_ref_missing", kinds)
        evidences = [f["evidence"] for f in result["findings"]
                     if f["detector"] == "doc_ref_missing"]
        self.assertTrue(any("src/legacy/old.py" in e for e in evidences))

    def test_b1_existing_path_not_flagged(self):
        d, env = self._build_repo()
        (d / "README.md").write_text(
            "# Repo\n\nMain is `src/main.py`.\n", encoding="utf-8"
        )
        (d / "src").mkdir()
        (d / "src" / "main.py").write_text("print('ok')\n", encoding="utf-8")
        _git_commit(d, env, "init", "2026-05-01 12:00:00")
        result = scanner.scan(d, repo_label="t")
        kinds = [f["detector"] for f in result["findings"]]
        self.assertNotIn("doc_ref_missing", kinds)

    def test_b2_predates_modules(self):
        d, env = self._build_repo()
        # CLAUDE.md committed first; then two modules added later.
        (d / "README.md").write_text("# repo\n" * 20, encoding="utf-8")
        (d / "CLAUDE.md").write_text("# Agent\n\nRun `npm test`.\n", encoding="utf-8")
        _git_commit(d, env, "init agent", "2025-06-01 12:00:00")
        for sub in ("alpha", "beta"):
            (d / sub).mkdir()
            (d / sub / "main.py").write_text("print('ok')\n", encoding="utf-8")
        _git_commit(d, env, "add modules", "2026-05-01 12:00:00")
        result = scanner.scan(d, repo_label="t")
        kinds = [f["detector"] for f in result["findings"]]
        self.assertIn("doc_predates_modules", kinds)
        ev = next(f["evidence"] for f in result["findings"]
                  if f["detector"] == "doc_predates_modules")
        self.assertIn("2025-06-01", ev)

    def test_b3_written_once_needs_churn(self):
        """B3 stays quiet below 100 commits — small repos don't get nagged."""
        d, env = self._build_repo()
        (d / "README.md").write_text("# repo\n" * 20, encoding="utf-8")
        _git_commit(d, env, "init", "2025-01-15 12:00:00")
        # A few more commits — well under the 100-commit churn threshold.
        for i in range(5):
            (d / f"file{i}.py").write_text(f"# {i}\n", encoding="utf-8")
            _git_commit(d, env, f"f{i}", "2026-05-01 12:00:00")
        result = scanner.scan(d, repo_label="t")
        kinds = [f["detector"] for f in result["findings"]]
        self.assertNotIn("doc_written_once", kinds)

    def test_b4_graded_drift_in_freshness_metric(self):
        """The score uses fresh_score_sum, not the legacy binary drift_count."""
        d, env = self._build_repo()
        (d / "README.md").write_text("# old\n" * 20, encoding="utf-8")
        _git_commit(d, env, "old doc", "2024-01-01 12:00:00")
        (d / "src").mkdir()
        (d / "src" / "main.py").write_text("print('ok')\n", encoding="utf-8")
        # ~2.4 years past 180d threshold → grade 0.0 ("very stale").
        _git_commit(d, env, "recent code", "2026-05-01 12:00:00")
        result = scanner.scan(d, repo_label="t")
        self.assertEqual(result["metrics"]["docs_checked"] >= 1, True)
        self.assertAlmostEqual(result["metrics"]["fresh_score_sum"], 0.0, places=1)
        fresh = next(c for c in result["categories"] if c["id"] == "doc_freshness")
        # 12 * (0.0 / 1) = 0
        self.assertEqual(fresh["points"], 0.0)


if __name__ == "__main__":
    unittest.main()
