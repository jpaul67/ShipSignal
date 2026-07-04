"""Config file tests (Package G): load/merge/precedence/typo handling."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from shipsignal import config, impact, modules, report

REPO = Path(__file__).resolve().parent.parent


def _git_init(d: Path):
    import os
    env = {**os.environ, "GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@t"}
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=d, check=True, env=env)
    for key, val in (("commit.gpgsign", "false"), ("gc.auto", "0"),
                     ("maintenance.auto", "false")):
        subprocess.run(["git", "config", key, val], cwd=d, check=True, env=env)
    return env


def _git_commit(d: Path, env: dict, msg: str, date: str):
    e = {**env, "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}
    subprocess.run(["git", "add", "-A"], cwd=d, check=True, env=e)
    subprocess.run(["git", "commit", "-q", "-m", msg], cwd=d, check=True, env=e)


class TestLoadConfig(unittest.TestCase):
    def test_missing_file_returns_defaults_no_warnings(self):
        with tempfile.TemporaryDirectory() as td:
            cfg, warnings = config.load_config(Path(td))
            self.assertEqual(warnings, [])
            self.assertEqual(cfg.impact.extra_ai_aliases, {})
            self.assertIsNone(cfg.impact.squash)
            self.assertIsNone(cfg.impact.release_tag_pattern)
            self.assertIsNone(cfg.readiness.fail_under)
            self.assertEqual(cfg.readiness.exclude_modules, [])
            self.assertIsNone(cfg.report.badge_label)

    def test_valid_full_config(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / config.CONFIG_FILENAME).write_text(
                '[impact]\n'
                'extra_ai_aliases = { "acmebot" = "Acme internal" }\n'
                'squash = true\n'
                r'release_tag_pattern = "^pkg@\\d+\\.\\d+\\.\\d+$"' "\n"
                '[readiness]\n'
                'fail_under = 80\n'
                'exclude_modules = ["vendor/legacy"]\n'
                '[report]\n'
                'badge_label = "custom"\n',
                encoding="utf-8",
            )
            cfg, warnings = config.load_config(Path(td))
            self.assertEqual(warnings, [])
            self.assertEqual(cfg.impact.extra_ai_aliases, {"acmebot": "Acme internal"})
            self.assertTrue(cfg.impact.squash)
            self.assertEqual(cfg.impact.release_tag_pattern, r"^pkg@\d+\.\d+\.\d+$")
            self.assertEqual(cfg.readiness.fail_under, 80)
            self.assertEqual(cfg.readiness.exclude_modules, ["vendor/legacy"])
            self.assertEqual(cfg.report.badge_label, "custom")

    def test_unknown_section_warns_and_is_ignored(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / config.CONFIG_FILENAME).write_text(
                '[bogus]\nx = 1\n[readiness]\nfail_under = 50\n', encoding="utf-8",
            )
            cfg, warnings = config.load_config(Path(td))
            self.assertEqual(cfg.readiness.fail_under, 50)
            self.assertTrue(any("bogus" in w for w in warnings), warnings)

    def test_unknown_key_warns_and_is_ignored(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / config.CONFIG_FILENAME).write_text(
                '[readiness]\nfail_under = 50\ntypo_key = "x"\n', encoding="utf-8",
            )
            cfg, warnings = config.load_config(Path(td))
            self.assertEqual(cfg.readiness.fail_under, 50)
            self.assertTrue(any("readiness.typo_key" in w for w in warnings), warnings)

    def test_wrong_type_warns_names_the_key_and_keeps_default(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / config.CONFIG_FILENAME).write_text(
                '[readiness]\nfail_under = "eighty"\n', encoding="utf-8",
            )
            cfg, warnings = config.load_config(Path(td))
            self.assertIsNone(cfg.readiness.fail_under)  # default kept, not crashed
            self.assertTrue(any("readiness.fail_under" in w for w in warnings), warnings)

    def test_bool_rejected_for_int_field(self):
        # bool is a subclass of int in Python — must not silently pass as fail_under.
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / config.CONFIG_FILENAME).write_text(
                '[readiness]\nfail_under = true\n', encoding="utf-8",
            )
            cfg, warnings = config.load_config(Path(td))
            self.assertIsNone(cfg.readiness.fail_under)
            self.assertTrue(warnings)

    def test_malformed_toml_degrades_to_defaults(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / config.CONFIG_FILENAME).write_text(
                '[readiness\nfail_under = 50\n', encoding="utf-8",  # missing ]
            )
            cfg, warnings = config.load_config(Path(td))
            self.assertIsNone(cfg.readiness.fail_under)
            self.assertEqual(len(warnings), 1)
            self.assertIn(config.CONFIG_FILENAME, warnings[0])

    def test_extra_ai_aliases_hyphenated_key_warns_and_is_dropped(self):
        # matching is exact-token, so a hyphenated key could never match anything.
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / config.CONFIG_FILENAME).write_text(
                '[impact]\nextra_ai_aliases = { "acme-bot" = "Acme internal" }\n',
                encoding="utf-8",
            )
            cfg, warnings = config.load_config(Path(td))
            self.assertEqual(cfg.impact.extra_ai_aliases, {})
            self.assertTrue(any("acme-bot" in w for w in warnings), warnings)

    def test_extra_ai_aliases_wrong_shape_warns(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / config.CONFIG_FILENAME).write_text(
                '[impact]\nextra_ai_aliases = ["not", "a", "table"]\n', encoding="utf-8",
            )
            cfg, warnings = config.load_config(Path(td))
            self.assertEqual(cfg.impact.extra_ai_aliases, {})
            self.assertTrue(any("impact.extra_ai_aliases" in w for w in warnings), warnings)

    def test_release_tag_pattern_invalid_regex_warns_and_falls_back(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / config.CONFIG_FILENAME).write_text(
                '[impact]\nrelease_tag_pattern = "["\n', encoding="utf-8",
            )
            cfg, warnings = config.load_config(Path(td))
            self.assertIsNone(cfg.impact.release_tag_pattern)
            self.assertTrue(any("impact.release_tag_pattern" in w for w in warnings), warnings)

    def test_release_tag_pattern_wrong_type_warns(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / config.CONFIG_FILENAME).write_text(
                "[impact]\nrelease_tag_pattern = 42\n", encoding="utf-8",
            )
            cfg, warnings = config.load_config(Path(td))
            self.assertIsNone(cfg.impact.release_tag_pattern)
            self.assertTrue(any("impact.release_tag_pattern" in w for w in warnings), warnings)


class TestExtraAliasesContextManager(unittest.TestCase):
    def test_merge_and_restore(self):
        self.assertNotIn("acmebot", impact._AI_ALIAS_KEYS)
        with impact.extra_aliases({"acmebot": "Acme internal"}):
            self.assertEqual(impact._AI_ALIAS_KEYS.get("acmebot"), "Acme internal")
            c = impact.Commit("x", __import__("datetime").date(2026, 1, 1), "dev@ex.com", "s",
                              trailers=["Co-Authored-By: Acmebot <bot@acme.example>"])
            self.assertTrue(c.ai_authored)
        self.assertNotIn("acmebot", impact._AI_ALIAS_KEYS)

    def test_override_of_builtin_key_restores_original_on_exit(self):
        original = impact._AI_ALIAS_KEYS["claude"]
        with impact.extra_aliases({"claude": "Not Actually Claude"}):
            self.assertEqual(impact._AI_ALIAS_KEYS["claude"], "Not Actually Claude")
        self.assertEqual(impact._AI_ALIAS_KEYS["claude"], original)

    def test_empty_or_none_is_a_no_op(self):
        before = dict(impact._AI_ALIAS_KEYS)
        with impact.extra_aliases(None):
            self.assertEqual(impact._AI_ALIAS_KEYS, before)
        with impact.extra_aliases({}):
            self.assertEqual(impact._AI_ALIAS_KEYS, before)


class TestExcludeModules(unittest.TestCase):
    def test_module_under_excluded_prefix_is_waived(self):
        # "legacy" (not "vendor") — "vendor" is itself in modules.EXCLUDE_DIRS,
        # so it would never surface as a candidate module at all.
        files = ["legacy/a.py", "legacy/sub/b.py", "src/main.py"]
        mods, _ = modules.detect_modules(
            REPO, files, is_git=False, exclude_prefixes=frozenset({"legacy"}),
        )
        by_path = {m.path: m for m in mods}
        self.assertIn("legacy", by_path)
        self.assertTrue(by_path["legacy"].waived)
        if "src" in by_path:
            self.assertFalse(by_path["src"].waived)

    def test_no_excludes_is_unchanged(self):
        files = ["src/main.py"]
        mods, _ = modules.detect_modules(REPO, files, is_git=False)
        self.assertTrue(all(not m.waived for m in mods if m.path == "src"))


class TestBadgeLabel(unittest.TestCase):
    def test_default_label_unchanged(self):
        import json
        payload = json.loads(report.render_badge_json({"score": 90, "grade": "A"}))
        self.assertEqual(payload["label"], "readiness")

    def test_custom_label(self):
        import json
        payload = json.loads(
            report.render_badge_json({"score": 90, "grade": "A"}, label="my-score")
        )
        self.assertEqual(payload["label"], "my-score")


class TestFailUnderPrecedence(unittest.TestCase):
    """End-to-end: CLI flag beats config file beats built-in default."""

    def setUp(self):
        d = Path(tempfile.mkdtemp())
        env = _git_init(d)
        (d / "README.md").write_text("# r\n" * 30, encoding="utf-8")
        (d / config.CONFIG_FILENAME).write_text(
            # 101 is unreachable (score caps at 100) -> the gate always fails.
            "[readiness]\nfail_under = 101\n", encoding="utf-8",
        )
        _git_commit(d, env, "init", "2026-05-15 12:00:00")
        self.root = d

    def _run(self, *extra_args):
        return subprocess.run(
            [sys.executable, "-m", "shipsignal.cli", "scan", str(self.root), *extra_args],
            capture_output=True, text=True, cwd=str(REPO),
        )

    def test_config_fail_under_gates_without_cli_flag(self):
        result = self._run()
        self.assertEqual(result.returncode, 1, msg=result.stderr)
        self.assertIn("FAIL", result.stderr)

    def test_cli_flag_overrides_config(self):
        result = self._run("--fail-under", "0")
        self.assertEqual(result.returncode, 0, msg=result.stderr)

    def test_config_warning_is_printed_for_a_typo(self):
        (self.root / config.CONFIG_FILENAME).write_text(
            "[readiness]\nfail_under = 0\ntypo = 1\n", encoding="utf-8",
        )
        result = self._run()
        self.assertIn("config:", result.stderr)
        self.assertIn("typo", result.stderr)


if __name__ == "__main__":
    unittest.main()
