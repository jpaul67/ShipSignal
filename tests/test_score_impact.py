"""Points-at-stake / finding-enrichment tests (Feature #1 + #5, v0.6.2)
+ cross-detector specificity, snippets, and grouped renderer (v0.6.3)."""
import html.parser
import subprocess
import tempfile
import unittest
from pathlib import Path

from shipsignal import report, scanner, score_impact, snippets
from shipsignal.scoring import score_scan


def _base_metrics(**kw):
    """A fully-scored metrics dict; override fields per test."""
    m = dict(
        has_root_readme=True, root_readme_substantial=True, is_small_repo=False,
        code_count=100, has_agent_file=True, has_root_agent_file=True,
        agent_usefulness_root="actionable", agent_usefulness_nested=None,
        modules_total=4, modules_covered=4, broken_links=0, links_checked=10,
        drift_count=0, fresh_score_sum=4.0, docs_checked=4,
        is_git=True, mcp_present=False, setup_score_frac=1.0, setup_total_weight=16,
    )
    m.update(kw)
    return m


class TestPointsAtStake(unittest.TestCase):
    def test_module_readme_marginal(self):
        # 4 modules, 3 covered → resolving one missing README should raise the score.
        m = _base_metrics(modules_total=4, modules_covered=3)
        finding = {"detector": "module_readme", "path": "src", "severity": "warn"}
        pts = score_impact.points_at_stake(finding, m)
        self.assertGreater(pts, 0)

    def test_setup_check_uses_weight(self):
        # Missing CI (weight 3) out of total 16 → resolving adds 3/16 of the
        # setup category (20 pts) ≈ 3.75 → ~ +2–4 pts on the renormalized total.
        m = _base_metrics(setup_score_frac=13 / 16, setup_total_weight=16)
        finding = {"detector": "setup", "path": ".", "severity": "warn",
                   "resolution": {"setup_check": "ci_config", "setup_weight": 3,
                                  "setup_total_weight": 16}}
        pts = score_impact.points_at_stake(finding, m)
        self.assertGreater(pts, 0)

    def test_informational_findings_are_zero(self):
        m = _base_metrics()
        for det in ("doc_ref_missing", "doc_predates_modules", "doc_written_once"):
            finding = {"detector": det, "path": "README.md", "severity": "warn"}
            self.assertEqual(score_impact.points_at_stake(finding, m), 0.0, det)
            self.assertTrue(score_impact.is_informational(finding), det)

    def test_agent_instructions_big_when_absent(self):
        # No agent file on a non-small repo → resolving is worth the full slot.
        m = _base_metrics(has_agent_file=False, has_root_agent_file=False,
                          agent_usefulness_root=None)
        finding = {"detector": "agent_instructions", "path": ".", "severity": "warn"}
        pts = score_impact.points_at_stake(finding, m)
        self.assertGreater(pts, 5)  # this is the highest-leverage fix on such a repo

    def test_rounds_to_half_and_clamps(self):
        # A no-op resolution (already satisfied) yields 0, never negative.
        m = _base_metrics(modules_total=4, modules_covered=4)
        finding = {"detector": "module_readme", "path": "x", "severity": "warn"}
        self.assertEqual(score_impact.points_at_stake(finding, m), 0.0)

    def test_deltas_not_additive_caveat(self):
        """Renormalization means resolving two findings != sum of their
        individual marginals. This documents *why* the UI labels values ≈."""
        m = _base_metrics(modules_total=4, modules_covered=2)
        f1 = {"detector": "module_readme", "path": "a", "severity": "warn"}
        f2 = {"detector": "module_readme", "path": "b", "severity": "warn"}
        p1 = score_impact.points_at_stake(f1, m)
        # Resolve one, then measure the second from the new baseline.
        m2 = dict(m, modules_covered=3)
        p2_after = score_impact.points_at_stake(f2, m2)
        base, _, _ = score_scan(m)
        both, _, _ = score_scan(dict(m, modules_covered=4))
        # Sum of independent marginals need not equal the true combined delta.
        self.assertGreaterEqual((both - base) + 0.5, min(p1, p2_after))


def _git_init(d: Path):
    env = {"GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@t", "PATH": ""}
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=d, check=True, env=env)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=d, check=True, env=env)
    return env


def _git_commit(d: Path, env: dict, msg: str, date: str):
    e = {**env, "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date, "PATH": ""}
    subprocess.run(["git", "add", "-A"], cwd=d, check=True, env=e)
    subprocess.run(["git", "commit", "-q", "-m", msg], cwd=d, check=True, env=e)


class TestEnrichmentInScan(unittest.TestCase):
    def test_findings_carry_metadata_and_sorted(self):
        d = Path(tempfile.mkdtemp())
        env = _git_init(d)
        (d / "README.md").write_text("# r\n" * 30, encoding="utf-8")
        (d / "src").mkdir()
        (d / "src" / "a.py").write_text("x=1\n", encoding="utf-8")
        _git_commit(d, env, "init", "2026-05-01 12:00:00")
        result = scanner.scan(d, repo_label="t")
        warns = [f for f in result["findings"] if f["severity"] == "warn"]
        self.assertTrue(warns)
        for f in warns:
            self.assertIn("points_at_stake", f)
            self.assertIn("effort", f)
            self.assertIn("area", f)
            self.assertNotIn("resolution", f)  # internal hint stripped
        # Sorted by points-at-stake descending.
        pts = [f["points_at_stake"] for f in warns]
        self.assertEqual(pts, sorted(pts, reverse=True))


class TestLineNumbers(unittest.TestCase):
    def test_broken_link_reports_line(self):
        d = Path(tempfile.mkdtemp())
        env = _git_init(d)
        readme = (
            "# Title\n\nIntro line.\n\nSee [the missing doc](./does-not-exist.md) here.\n"
        )
        (d / "README.md").write_text(readme, encoding="utf-8")
        (d / "main.py").write_text("x=1\n", encoding="utf-8")
        _git_commit(d, env, "init", "2026-05-01 12:00:00")
        result = scanner.scan(d, repo_label="t")
        bl = next((f for f in result["findings"] if f["detector"] == "broken_link"), None)
        self.assertIsNotNone(bl)
        self.assertEqual(bl["line"], 5, "broken link is on line 5")


# --- v0.6.3 #2: cross-detector specificity --------------------------------


class TestEcosystemAndCommandCapture(unittest.TestCase):
    def test_npm_test_command_captured(self):
        from shipsignal.setupcheck import detect_setup
        d = Path(tempfile.mkdtemp())
        (d / "package.json").write_text(
            '{"scripts": {"test": "vitest run", "build": "tsc"}}', encoding="utf-8"
        )
        files = ["package.json"]
        _findings, m = detect_setup(d, files, mcp_present=False, modules_total=0)
        self.assertEqual(m["detected_test_cmd"], "npm test")
        self.assertEqual(m["detected_build_cmd"], "npm run build")
        self.assertEqual(m["ecosystem"], "npm")

    def test_python_pytest_captured(self):
        from shipsignal.setupcheck import detect_setup
        d = Path(tempfile.mkdtemp())
        (d / "pyproject.toml").write_text(
            '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n', encoding="utf-8"
        )
        files = ["pyproject.toml"]
        _findings, m = detect_setup(d, files, mcp_present=False, modules_total=0)
        self.assertEqual(m["detected_test_cmd"], "pytest")
        self.assertEqual(m["ecosystem"], "python")

    def test_no_commands_no_fabrication(self):
        from shipsignal.setupcheck import detect_setup
        d = Path(tempfile.mkdtemp())
        _findings, m = detect_setup(d, [], mcp_present=False, modules_total=0)
        self.assertIsNone(m.get("detected_test_cmd"))
        self.assertIsNone(m.get("detected_build_cmd"))


class TestSpecializeFix(unittest.TestCase):
    """When the setup pass found `npm test`, agent_instructions fix names it.
    When no command was found, fall back to generic (never fabricate)."""

    def test_agent_fix_names_detected_command(self):
        d = Path(tempfile.mkdtemp())
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=d, check=True,
                       env={"GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@t",
                            "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@t",
                            "PATH": ""})
        # README is substantial; package.json has a test script; no agent file.
        # Lots of code files so the small-repo n/a path doesn't fire.
        (d / "README.md").write_text("# r\n" * 30, encoding="utf-8")
        (d / "package.json").write_text(
            '{"scripts": {"test": "vitest run", "build": "vite build"}}',
            encoding="utf-8")
        for i in range(30):
            (d / f"a{i}.js").write_text(f"// {i}\n", encoding="utf-8")
        env = {"GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@t",
               "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@t",
               "GIT_AUTHOR_DATE": "2026-05-01 12:00:00",
               "GIT_COMMITTER_DATE": "2026-05-01 12:00:00", "PATH": ""}
        subprocess.run(["git", "add", "-A"], cwd=d, check=True, env=env)
        subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=d, check=True, env=env)
        result = scanner.scan(d, repo_label="t")
        agent_f = next((f for f in result["findings"]
                        if f["detector"] == "agent_instructions"), None)
        self.assertIsNotNone(agent_f)
        # The fix should reference the actual detected commands.
        self.assertIn("npm test", agent_f["fix"])
        self.assertIn("npm run build", agent_f["fix"])


# --- v0.6.3 #3: starter snippets ------------------------------------------


class TestSnippets(unittest.TestCase):
    def test_agent_snippet_uses_detected_commands(self):
        finding = {"detector": "agent_instructions", "path": ".", "severity": "warn"}
        metrics = {"detected_test_cmd": "pytest", "detected_build_cmd": None,
                   "ecosystem": "python"}
        snip = snippets.snippet_for(finding, metrics)
        self.assertIn("pytest", snip)
        self.assertIn("python", snip)
        # Honest framing: the placeholder syntax must be visible somewhere.
        self.assertIn("<", snip)

    def test_module_snippet_pulls_from_evidence(self):
        finding = {
            "detector": "module_readme", "path": "scripts", "severity": "warn",
            "evidence": "Module 'scripts' (dir) has no README (2 .js files: build.js, pack.js)",
        }
        snip = snippets.snippet_for(finding, {})
        self.assertIn("build.js", snip)
        self.assertIn("pack.js", snip)

    def test_test_command_snippet_only_when_ecosystem_known(self):
        # Test_command setup finding without an ecosystem → no fabricated snippet.
        finding = {"detector": "setup", "path": ".", "severity": "warn",
                   "evidence": "Missing discoverable test command",
                   "fix": "Add a test script/target"}
        self.assertIsNone(snippets.snippet_for(finding, {}))
        # With npm ecosystem → a package.json starter is returned.
        snip = snippets.snippet_for(finding, {"ecosystem": "npm"})
        self.assertIsNotNone(snip)
        self.assertIn("package.json", snip)


# --- v0.6.3 #4: grouped + collapsed renderer ------------------------------


class TestGroupedRenderer(unittest.TestCase):
    def _make_findings(self):
        return [
            {"detector": "agent_instructions", "path": ".", "severity": "warn",
             "evidence": "No agent file", "fix": "Add AGENTS.md",
             "area": "Agent context", "points_at_stake": 15.0, "effort": "moderate"},
            {"detector": "module_readme", "path": "src", "severity": "warn",
             "evidence": "Module 'src' (dir) has no README (2 .js files: a.js, b.js)",
             "fix": "Add src/README.md", "area": "Module docs",
             "points_at_stake": 3.0, "effort": "moderate"},
            # 4 setup info findings → should collapse
            {"detector": "setup", "path": ".", "severity": "info",
             "evidence": "Missing .editorconfig", "fix": "Add .editorconfig",
             "area": "Setup", "points_at_stake": 0.5, "effort": "quick"},
            {"detector": "setup", "path": ".", "severity": "info",
             "evidence": "Missing CONTRIBUTING", "fix": "Add CONTRIBUTING",
             "area": "Setup", "points_at_stake": 0.5, "effort": "quick"},
            {"detector": "setup", "path": ".", "severity": "info",
             "evidence": "Missing LICENSE", "fix": "Add LICENSE",
             "area": "Setup", "points_at_stake": 0.5, "effort": "quick"},
            {"detector": "setup", "path": ".", "severity": "info",
             "evidence": "Missing formatter config", "fix": "Add prettier",
             "area": "Setup", "points_at_stake": 0.5, "effort": "quick"},
            # one warn-level setup item: not collapsed
            {"detector": "setup", "path": ".", "severity": "warn",
             "evidence": "Missing CI configuration", "fix": "Add .github/workflows",
             "area": "Setup", "points_at_stake": 4.0, "effort": "moderate"},
        ]

    def test_blocks_in_fixed_area_order(self):
        blocks = report._group_fixes(self._make_findings())
        areas = [b["area"] for b in blocks]
        # Order must follow AREA_ORDER even though findings came in mixed order.
        from shipsignal.detectors import AREA_ORDER
        for actual, expected in zip(areas, AREA_ORDER):
            if actual == expected:
                continue
            self.fail(f"blocks not in fixed order: got {areas}")

    def test_setup_info_collapses_when_3_plus(self):
        blocks = report._group_fixes(self._make_findings())
        setup_block = next(b for b in blocks if b["area"] == "Setup")
        collapsed = [it for it in setup_block["items"] if it.get("_collapsed")]
        self.assertEqual(len(collapsed), 1,
                         "4 setup info items should collapse into one bundle")
        bundle = collapsed[0]
        self.assertIn("4 convention items", bundle["evidence"])
        # And the warn-level CI item is preserved separately.
        warns = [it for it in setup_block["items"]
                 if it.get("severity") == "warn"]
        self.assertEqual(len(warns), 1)
        self.assertIn("CI", warns[0]["evidence"])

    def test_html_renders_grouped_and_well_formed(self):
        findings = self._make_findings()
        body = report._render_grouped_fixes_html(findings)
        self.assertIn("Agent context", body)
        self.assertIn("Module docs", body)
        self.assertIn("Setup", body)
        self.assertIn("4 convention items", body)
        # Snippet would only appear if attached; here we didn't set one.
        html.parser.HTMLParser().feed(body)  # raises on malformed

    def test_cli_top_3_snippet_rule(self):
        findings = self._make_findings()
        # Attach snippets to all 3 highest-payoff warn items.
        for f in findings:
            if f.get("severity") == "warn":
                f["snippet"] = "SNIP-" + f["detector"]
        top_ids = report._top_n_payoff_ids(findings, n=3)
        # The 15-pt agent_instructions, 4-pt CI, and 3-pt module_readme.
        warns_sorted = sorted(
            [f for f in findings if f.get("severity") == "warn"],
            key=lambda f: -f.get("points_at_stake", 0),
        )
        self.assertEqual({id(f) for f in warns_sorted[:3]}, top_ids)


# --- broken-link collapse (2a) -------------------------------------------


def _bl(path: str, target: str, line: int = 1) -> dict:
    return {"detector": "broken_link", "path": path, "severity": "warn",
            "evidence": f"Link to '{target}' does not resolve",
            "fix": f"Fix or remove the link in {path}",
            "area": "Integrity", "points_at_stake": 0.0, "effort": "quick",
            "link_target": target, "line": line}


class TestBrokenLinkCollapse(unittest.TestCase):
    def test_collapses_when_3_plus_share_target(self):
        findings = [_bl(f"docs/{lang}/help.md", "../release-notes.md", 9)
                    for lang in ("de", "es", "fr", "ja")]
        blocks = report._group_fixes(findings)
        integrity = next(b for b in blocks if b["area"] == "Integrity")
        collapsed = [it for it in integrity["items"] if it.get("_collapsed")]
        self.assertEqual(len(collapsed), 1)
        bundle = collapsed[0]
        self.assertEqual(bundle["count"], 4)
        self.assertIn("release-notes.md", bundle["evidence"])
        self.assertIn("4 files", bundle["evidence"])
        self.assertIsInstance(bundle["files"], list)
        self.assertEqual(len(bundle["files"]), 4)

    def test_below_threshold_stays_individual(self):
        findings = [_bl(f"docs/{lang}/help.md", "../release-notes.md", 9)
                    for lang in ("de", "es")]  # 2 < threshold of 3
        blocks = report._group_fixes(findings)
        integrity = next(b for b in blocks if b["area"] == "Integrity")
        collapsed = [it for it in integrity["items"] if it.get("_collapsed")]
        self.assertEqual(len(collapsed), 0)
        self.assertEqual(len(integrity["items"]), 2)

    def test_different_targets_stay_separate(self):
        findings = [
            _bl("docs/de/help.md", "../release-notes.md"),
            _bl("docs/es/help.md", "../release-notes.md"),
            _bl("docs/fr/help.md", "../release-notes.md"),
            _bl("docs/de/deploy.md", "../versions.md"),  # different target
        ]
        blocks = report._group_fixes(findings)
        integrity = next(b for b in blocks if b["area"] == "Integrity")
        collapsed = [it for it in integrity["items"] if it.get("_collapsed")]
        individual = [it for it in integrity["items"] if not it.get("_collapsed")]
        self.assertEqual(len(collapsed), 1, "only the 3-hit target collapses")
        self.assertEqual(len(individual), 1, "../versions.md stays individual")

    def test_html_collapsed_bundle_has_files_expander(self):
        findings = [_bl(f"docs/{lang}/help.md", "../release-notes.md", 9)
                    for lang in ("de", "es", "fr")]
        body = report._render_grouped_fixes_html(findings)
        html.parser.HTMLParser().feed(body)  # well-formed
        self.assertIn("release-notes.md", body)
        self.assertIn("3 files", body)
        self.assertIn("All affected files", body)  # the <details> summary


# --- Adaptive sparkline (Option C: width-fitting + downsample) -----------


class TestAdaptiveSparkline(unittest.TestCase):
    def test_downsample_returns_input_when_already_short(self):
        self.assertEqual(report._downsample([1, 2, 3], 10), [1, 2, 3])

    def test_downsample_averages_buckets(self):
        # 6 values → 3 cells: buckets of 2 each, averaged.
        out = report._downsample([0.0, 1.0, 0.5, 0.5, 0.8, 0.2], 3)
        self.assertEqual(out, [0.5, 0.5, 0.5])

    def test_downsample_skips_none_within_bucket(self):
        # Mixed [v, None] bucket averages just v.
        out = report._downsample([1.0, None, 0.0, None], 2)
        self.assertEqual(out, [1.0, 0.0])

    def test_downsample_preserves_all_none_bucket_as_none(self):
        # An all-None bucket stays None so the gap renders as a blank.
        out = report._downsample([None, None, 1.0, 1.0], 2)
        self.assertEqual(out, [None, 1.0])

    def test_fit_spark_width_clamps(self):
        # Even on absurdly narrow chrome, never exceeds hi.
        n = report._fit_spark_width(chrome=0, hi=60, lo=20)
        self.assertLessEqual(n, 60)
        self.assertGreaterEqual(n, 20)
        # Massive chrome can't push below lo.
        self.assertEqual(report._fit_spark_width(chrome=1000, lo=20), 20)

    def test_adaptive_spark_length_matches_fitted_width(self):
        # 200 values must downsample to whatever _fit_spark_width returns.
        vals = [i / 200 for i in range(200)]
        out = report._adaptive_spark(vals, chrome=28, max_val=1.0)
        self.assertEqual(len(out), report._fit_spark_width(chrome=28))

    def test_rate_week_line_fits_80_cols(self):
        """Regression: the exact rate/week shape must fit in 80 cols on the
        default terminal width. This is the line that motivated Option C."""
        # The construction mirrors render_impact's rate/week block.
        for nweeks in (60, 130, 400):
            window = [w / nweeks for w in range(1, nweeks + 1)][-60:]
            spark = report._adaptive_spark(window, chrome=28, max_val=1.0)
            line = f"   rate/week {spark}  {len(window)}w · 0–100%"
            self.assertLessEqual(
                len(line), 80,
                f"rate/week line is {len(line)} cols at nweeks={nweeks}: {line!r}"
            )
            self.assertIn("w · 0–100%", line)
            # Spark width must match what the fitter says it should be.
            self.assertEqual(len(spark), report._fit_spark_width(chrome=28))


class TestTestDataDirSkip(unittest.TestCase):
    """Broken links inside test-data dirs should not fire (Change 1)."""

    def test_fixture_markdown_not_link_checked(self):
        d = Path(tempfile.mkdtemp())
        env = _git_init(d)
        # A fixture file with a broken link — should NOT appear in findings.
        (d / "tests").mkdir()
        (d / "tests" / "fixture.md").write_text(
            "# Test fixture\n[broken](./does-not-exist.md)\n", encoding="utf-8"
        )
        # A real README with a good link so the scanner has something to check.
        (d / "README.md").write_text("# Root\n\nNo broken links here.\n" * 10,
                                     encoding="utf-8")
        (d / "main.py").write_text("x=1\n", encoding="utf-8")
        _git_commit(d, env, "init", "2026-05-01 12:00:00")
        result = scanner.scan(d, repo_label="t")
        bl = [f for f in result["findings"] if f["detector"] == "broken_link"]
        self.assertEqual(bl, [], "no broken_link findings from test-fixture markdown")

    def test_real_doc_broken_link_still_fires(self):
        d = Path(tempfile.mkdtemp())
        env = _git_init(d)
        (d / "README.md").write_text(
            "# Root\n\n" + "padding\n" * 10 +
            "[missing](./does-not-exist.md)\n",
            encoding="utf-8"
        )
        (d / "main.py").write_text("x=1\n", encoding="utf-8")
        _git_commit(d, env, "init", "2026-05-01 12:00:00")
        result = scanner.scan(d, repo_label="t")
        bl = [f for f in result["findings"] if f["detector"] == "broken_link"]
        self.assertTrue(bl, "broken link in real README must still fire")

    def test_examples_dir_still_link_checked(self):
        d = Path(tempfile.mkdtemp())
        env = _git_init(d)
        (d / "README.md").write_text("# Root\n" * 10, encoding="utf-8")
        (d / "examples").mkdir()
        (d / "examples" / "guide.md").write_text(
            "# Guide\n[broken](./missing.md)\n", encoding="utf-8"
        )
        (d / "main.py").write_text("x=1\n", encoding="utf-8")
        _git_commit(d, env, "init", "2026-05-01 12:00:00")
        result = scanner.scan(d, repo_label="t")
        bl = [f for f in result["findings"] if f["detector"] == "broken_link"]
        self.assertTrue(bl, "broken links in examples/ should still be checked")


if __name__ == "__main__":
    unittest.main()
