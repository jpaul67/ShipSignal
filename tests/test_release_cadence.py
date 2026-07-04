"""Release cadence & lead-time tests (Package K): tags-based DORA proxies."""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from shipsignal import impact, report
from shipsignal.impact import MIN_RELEASE_TAGS, compute_release_cadence

REPO = Path(__file__).resolve().parent.parent


def _git_init(d: Path) -> dict:
    env = {**os.environ, "GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@t"}
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=d, check=True, env=env)
    for key, val in (("commit.gpgsign", "false"), ("gc.auto", "0"),
                     ("maintenance.auto", "false")):
        subprocess.run(["git", "config", key, val], cwd=d, check=True, env=env)
    return env


def _commit(d: Path, env: dict, msg: str, date_str: str, fname: str, content: str) -> str:
    (d / fname).write_text(content)
    e = {**env, "GIT_AUTHOR_DATE": date_str, "GIT_COMMITTER_DATE": date_str}
    subprocess.run(["git", "add", "-A"], cwd=d, check=True, env=e)
    subprocess.run(["git", "commit", "-q", "-m", msg], cwd=d, check=True, env=e)
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=d, check=True, env=e,
                          capture_output=True, text=True).stdout.strip()


def _tag_lightweight(d: Path, env: dict, name: str, target: str = "HEAD") -> None:
    # Lightweight tags carry no tag object of their own — for-each-ref's
    # creatordate falls back to the target commit's own committer date.
    subprocess.run(["git", "tag", name, target], cwd=d, check=True, env=env)


def _tag_annotated(d: Path, env: dict, name: str, date_str: str, target: str = "HEAD") -> None:
    # Annotated tags have their own tagger line, controlled the same way a
    # commit's committer identity/date is.
    e = {**env, "GIT_COMMITTER_DATE": date_str}
    subprocess.run(["git", "tag", "-a", name, "-m", name, target], cwd=d, check=True, env=e)


class TestComputeReleaseCadenceHappyPath(unittest.TestCase):
    """A 4-tag, 10-commit history with hand-computable cadence + lead-time numbers."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        env = _git_init(d)
        _commit(d, env, "c1", "2026-01-01 12:00:00", "f1.txt", "1")
        _tag_lightweight(d, env, "v1.0.0")
        _commit(d, env, "c2", "2026-01-05 12:00:00", "f2.txt", "2")
        _commit(d, env, "c3", "2026-01-10 12:00:00", "f3.txt", "3")
        _commit(d, env, "c4", "2026-01-15 12:00:00", "f4.txt", "4")
        _tag_lightweight(d, env, "v1.1.0")
        _commit(d, env, "c5", "2026-01-18 12:00:00", "f5.txt", "5")
        _commit(d, env, "c6", "2026-01-22 12:00:00", "f6.txt", "6")
        _commit(d, env, "c7", "2026-01-25 12:00:00", "f7.txt", "7")
        _tag_lightweight(d, env, "v1.2.0")
        _commit(d, env, "c8", "2026-02-01 12:00:00", "f8.txt", "8")
        _commit(d, env, "c9", "2026-02-08 12:00:00", "f9.txt", "9")
        _commit(d, env, "c10", "2026-02-14 12:00:00", "f10.txt", "10")
        _tag_lightweight(d, env, "v1.3.0")
        self.root = d

    def tearDown(self):
        self.tmp.cleanup()

    def test_cadence_and_lead_time_numbers(self):
        rc = compute_release_cadence(self.root)
        self.assertEqual(rc["status"], "scored")
        self.assertEqual(rc["tags_matched"], 4)
        self.assertEqual(rc["tags_total"], 4)
        self.assertEqual(rc["window"], "trailing 12 months")
        self.assertEqual(rc["latest_tag"], "v1.3.0")
        self.assertEqual(rc["cadence"]["tags_per_month"], 2.73)
        self.assertEqual(rc["cadence"]["median_gap_days"], 14.0)
        lt = rc["lead_time"]
        self.assertEqual(lt["status"], "scored")
        self.assertEqual(lt["commits"], 9)
        self.assertEqual(lt["median_days"], 5.0)

    def test_renders_in_all_three_formats(self):
        result = impact.compute_impact(self.root, repo_label="release-cadence-fixture")
        rc = result["release_cadence"]
        self.assertEqual(rc["status"], "scored")

        cli = report.render_impact(result)
        self.assertIn("Release cadence & lead time", cli)
        self.assertIn("2.73 tags/mo", cli)
        self.assertIn("lead time: median 5d", cli)

        md = report.render_impact_markdown(result)
        self.assertIn("## Release cadence & lead time (context — never scored)", md)
        self.assertIn("Cadence:** 2.73 tags/mo", md)
        self.assertIn("Lead time:** median **5d**", md)

        html = report.render_impact_html(result)
        self.assertIn("Release cadence", html)
        self.assertIn("2.73", html)


class TestComputeReleaseCadenceDegradePaths(unittest.TestCase):
    def test_no_tags_is_na(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            env = _git_init(d)
            _commit(d, env, "c1", "2026-01-01 12:00:00", "f.txt", "1")
            rc = compute_release_cadence(d)
            self.assertEqual(rc["status"], "n/a")
            self.assertEqual(rc["tags_matched"], 0)
            self.assertEqual(rc["tags_total"], 0)
            self.assertIn(f"need {MIN_RELEASE_TAGS}", rc["reason"])

    def test_below_floor_is_na(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            env = _git_init(d)
            _commit(d, env, "c1", "2026-01-01 12:00:00", "f.txt", "1")
            _tag_lightweight(d, env, "v0.1.0")
            _commit(d, env, "c2", "2026-02-01 12:00:00", "f2.txt", "2")
            _tag_lightweight(d, env, "v0.2.0")
            rc = compute_release_cadence(d)
            self.assertEqual(rc["status"], "n/a")
            self.assertEqual(rc["tags_matched"], 2)
            self.assertIn(f"need {MIN_RELEASE_TAGS}", rc["reason"])

    def test_noise_tags_filtered_by_default_pattern(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            env = _git_init(d)
            _commit(d, env, "c1", "2026-01-01 12:00:00", "f.txt", "1")
            _tag_lightweight(d, env, "v1.0.0")
            _tag_lightweight(d, env, "checkpoint-mar")
            _commit(d, env, "c2", "2026-01-15 12:00:00", "f2.txt", "2")
            _tag_lightweight(d, env, "v1.1.0")
            _tag_lightweight(d, env, "wip-testing")
            _commit(d, env, "c3", "2026-02-01 12:00:00", "f3.txt", "3")
            _tag_lightweight(d, env, "v1.2.0")
            rc = compute_release_cadence(d)
            self.assertEqual(rc["status"], "scored")
            self.assertEqual(rc["tags_matched"], 3)
            self.assertEqual(rc["tags_total"], 5)

    def test_custom_pattern_override_for_monorepo_tags(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            env = _git_init(d)
            _commit(d, env, "c1", "2026-01-01 12:00:00", "f.txt", "1")
            _tag_lightweight(d, env, "pkg-a@1.0.0")
            _commit(d, env, "c2", "2026-01-15 12:00:00", "f2.txt", "2")
            _tag_lightweight(d, env, "pkg-a@1.1.0")
            _commit(d, env, "c3", "2026-02-01 12:00:00", "f3.txt", "3")
            _tag_lightweight(d, env, "pkg-a@1.2.0")

            default_rc = compute_release_cadence(d)
            self.assertEqual(default_rc["status"], "n/a")
            self.assertEqual(default_rc["tags_matched"], 0)

            custom_rc = compute_release_cadence(
                d, tag_pattern=re.compile(r"^pkg-a@\d+\.\d+\.\d+$")
            )
            self.assertEqual(custom_rc["status"], "scored")
            self.assertEqual(custom_rc["tags_matched"], 3)

    def test_trailing_window_falls_back_to_full_history_when_sparse(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            env = _git_init(d)
            _commit(d, env, "c1", "2020-01-01 12:00:00", "f1.txt", "1")
            _tag_lightweight(d, env, "v1.0.0")
            _commit(d, env, "c2", "2020-06-01 12:00:00", "f2.txt", "2")
            _tag_lightweight(d, env, "v1.1.0")
            _commit(d, env, "c3", "2021-01-01 12:00:00", "f3.txt", "3")
            _tag_lightweight(d, env, "v1.2.0")
            # Only this last tag falls within 12 months of itself — the other
            # three are all years older, so the trailing window is sparse.
            _commit(d, env, "c4", "2026-01-01 12:00:00", "f4.txt", "4")
            _tag_lightweight(d, env, "v2.0.0")
            rc = compute_release_cadence(d)
            self.assertEqual(rc["status"], "scored")
            self.assertEqual(rc["window"], "full history")
            self.assertEqual(rc["tags_matched"], 4)

    def test_lead_time_na_when_consecutive_tags_share_a_commit(self):
        # Three annotated tags with distinct tagger dates but pointing at the
        # SAME commit: cadence can still be computed from tag dates, but
        # `git log t1..t2` between them is empty, so lead time is n/a rather
        # than a false zero.
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            env = _git_init(d)
            _commit(d, env, "c1", "2026-01-01 12:00:00", "f.txt", "1")
            _tag_annotated(d, env, "v1.0.0", "2026-01-01 12:00:00")
            _tag_annotated(d, env, "v1.1.0", "2026-02-01 12:00:00")
            _tag_annotated(d, env, "v1.2.0", "2026-03-01 12:00:00")
            rc = compute_release_cadence(d)
            self.assertEqual(rc["status"], "scored")
            lt = rc["lead_time"]
            self.assertEqual(lt["status"], "n/a")
            self.assertEqual(lt["commits"], 0)
            self.assertIsNone(lt["median_days"])

    def test_untagged_repo_shows_na_not_penalized(self):
        # An untagged repo must never be scored down for it — the delivery
        # health score doesn't read release_cadence at all, and the impact
        # pipeline still runs end-to-end.
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            env = _git_init(d)
            for i in range(1, 25):
                _commit(d, env, f"c{i}", f"2026-01-{i:02d} 12:00:00", f"f{i}.txt", str(i))
            result = impact.compute_impact(d, repo_label="untagged-fixture")
            self.assertEqual(result["release_cadence"]["status"], "n/a")
            cli = report.render_impact(result)
            self.assertIn("Release cadence & lead time", cli)
            self.assertIn("n/a", cli)


class TestReleaseTagPatternCLIWiring(unittest.TestCase):
    """End-to-end: `.shipsignal.toml`'s [impact].release_tag_pattern reaches
    compute_release_cadence via the CLI, same wiring style as squash/extra_ai_aliases."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        env = _git_init(d)
        for i, tag in enumerate(("pkg-a@1.0.0", "pkg-a@1.1.0", "pkg-a@1.2.0"), start=1):
            _commit(d, env, f"c{i}", f"2026-01-{i:02d} 12:00:00", f"f{i}.txt", str(i))
            _tag_lightweight(d, env, tag)
        self.root = d

    def tearDown(self):
        self.tmp.cleanup()

    def test_config_pattern_reaches_impact_command(self):
        (self.root / "README.md").write_text("# r\n", encoding="utf-8")
        (self.root / ".shipsignal.toml").write_text(
            r'[impact]' "\n" r'release_tag_pattern = "^pkg-a@\\d+\\.\\d+\\.\\d+$"' "\n",
            encoding="utf-8",
        )
        out_json = self.root / "impact.json"
        result = subprocess.run(
            [sys.executable, "-m", "shipsignal.cli", "impact", str(self.root),
             "--no-readiness", "--json", str(out_json)],
            capture_output=True, text=True, encoding="utf-8", cwd=str(REPO),
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        payload = json.loads(out_json.read_text(encoding="utf-8"))
        rc = payload["release_cadence"]
        self.assertEqual(rc["status"], "scored")
        self.assertEqual(rc["tags_matched"], 3)


if __name__ == "__main__":
    unittest.main()
