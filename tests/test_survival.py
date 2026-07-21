"""Surviving-lines-by-sha tests (Package L, slices 1 and 2)."""
import os
import subprocess
import tempfile
import unittest
from collections import namedtuple
from datetime import date, timedelta
from pathlib import Path

from shipsignal import config, impact, prdata
from shipsignal.survival import (
    MIN_GROUP_COMMITS,
    MIN_GROUP_LINES,
    MIN_SURVIVAL_AGE_DAYS,
    compute_survival,
    matched_survival,
    parse_incremental_blame,
    surviving_lines_by_sha,
)

Commit = namedtuple("Commit", ["sha", "date", "lines_added"])


def _git_init(d: Path) -> dict:
    env = {**os.environ, "GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@t"}
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=d, check=True, env=env)
    for key, val in (("commit.gpgsign", "false"), ("gc.auto", "0"),
                     ("maintenance.auto", "false")):
        subprocess.run(["git", "config", key, val], cwd=d, check=True, env=env)
    return env


def _commit(d: Path, env: dict, msg: str, date_str: str, fname: str, content: str,
            *, ai: bool = False) -> str:
    (d / fname).write_text(content)
    e = {**env, "GIT_AUTHOR_DATE": date_str, "GIT_COMMITTER_DATE": date_str}
    if ai:
        msg = f"{msg}\n\nCo-authored-by: Copilot <copilot@github.com>"
    subprocess.run(["git", "add", "-A"], cwd=d, check=True, env=e)
    subprocess.run(["git", "commit", "-q", "-m", msg], cwd=d, check=True, env=e)
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=d, check=True, env=e,
                          capture_output=True, text=True).stdout.strip()


SHA_A = "a" * 40
SHA_B = "b" * 40
SHA_C = "c" * 40


# A hand-captured `git blame --incremental -w` payload: three blocks, distinct
# shas, known num_lines, with metadata lines (author/author-time/filename) that
# the parser MUST ignore. The incremental form emits no source content.
INCREMENTAL_FIXTURE = (
    f"{SHA_A} 1 1 4\n"
    f"author T\n"
    f"author-time 1700000000\n"
    f"author-mail <t@t>\n"
    f"filename app.py\n"
    f"{SHA_B} 5 5 2\n"
    f"author U\n"
    f"author-time 1700000100\n"
    f"author-mail <u@u>\n"
    f"filename app.py\n"
    f"{SHA_A} 7 7 1\n"
    f"author T\n"
    f"author-time 1700000200\n"
    f"filename app.py\n"
    f"{SHA_C} 8 8 3\n"
    f"author V\n"
    f"author-time 1700000300\n"
    f"filename other.py\n"
)


class TestParseIncrementalBlame(unittest.TestCase):
    def test_known_line_accounting(self):
        result = parse_incremental_blame(INCREMENTAL_FIXTURE)
        # SHA_A: 4 (block 1) + 1 (block 3) = 5
        # SHA_B: 2
        # SHA_C: 3
        self.assertEqual(result, {SHA_A: 5, SHA_B: 2, SHA_C: 3})

    def test_metadata_lines_ignored(self):
        result = parse_incremental_blame(INCREMENTAL_FIXTURE)
        # No metadata-key string leaks into the dict as a key.
        for key in result:
            self.assertEqual(len(key), 40)
            self.assertTrue(all(c in "0123456789abcdef" for c in key))
        # "author" / "filename" must never appear as keys.
        self.assertNotIn("author", result)
        self.assertNotIn("filename", result)
        self.assertNotIn("author-time", result)

    def test_empty_input(self):
        self.assertEqual(parse_incremental_blame(""), {})
        self.assertEqual(parse_incremental_blame("\n\n"), {})

    def test_non_hex_sha_skipped(self):
        # 40 chars but contains a 'g' (not hex). Should be skipped entirely
        # rather than crashing or miscounting.
        bad = "g" * 40 + " 1 1 1\n"
        self.assertEqual(parse_incremental_blame(bad), {})


class TestSurvivingLinesByShaSmoke(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.env = _git_init(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_single_commit_all_lines_survive(self):
        content = "line1\nline2\nline3\n"
        sha = _commit(self.root, self.env, "c1", "2026-01-01 12:00:00",
                      "app.py", content)
        result = surviving_lines_by_sha(self.root, ["app.py"])
        self.assertIn(sha, result)
        self.assertEqual(result[sha], 3)
        # Only that one sha should be present.
        self.assertEqual(list(result.keys()), [sha])

    def test_duplicate_paths_not_double_counted(self):
        # A caller passing the same path twice must not blame it twice: the
        # counts are summed per sha, so a repeat would silently inflate them.
        sha = _commit(self.root, self.env, "c1", "2026-01-01 12:00:00",
                      "app.py", "line1\nline2\nline3\n")
        result = surviving_lines_by_sha(self.root, ["app.py", "app.py"])
        self.assertEqual(result[sha], 3,
                         "a repeated path double-counted its surviving lines")

    def test_non_code_ext_skipped(self):
        _commit(self.root, self.env, "c1", "2026-01-01 12:00:00",
                "README.md", "x\n")
        result = surviving_lines_by_sha(self.root, ["README.md"])
        self.assertEqual(result, {})


# --- Slice 2: age-matched survival -------------------------------------------
# Synthetic shas for the pure aggregator tests (no real git needed).
AI1 = "a1" * 20
AI2 = "a2" * 20
OT1 = "b1" * 20
OT2 = "b2" * 20
AI3 = "a3" * 20  # AI-only month, high survival (the pooled-flattering one)


class TestMatchedSurvivalHappyPath(unittest.TestCase):
    def test_scored_exact_hand_computed(self):
        # Two matched months. Hand-compute survival:
        #   Month 2024-01: AI adds 100, survives 50 -> 0.50
        #                 other adds 200, survives 80 -> 0.40
        #   Month 2024-02: AI adds 100, survives 30 -> 0.30
        #                 other adds 100, survives 60 -> 0.60
        # Overall AI:    (50+30)/(100+100) = 80/200 = 0.40
        # Overall other: (80+60)/(200+100) = 140/300 ≈ 0.4666...
        today = date(2026, 6, 1)
        adoption = date(2024, 1, 1)
        commits = [
            Commit(AI1, date(2024, 1, 10), 100),
            Commit(OT1, date(2024, 1, 20), 200),
            Commit(AI2, date(2024, 2, 5), 100),
            Commit(OT2, date(2024, 2, 25), 100),
        ]
        surviving = {AI1: 50, OT1: 80, AI2: 30, OT2: 60}
        res = matched_survival(commits, surviving, {AI1, AI2, AI3}, adoption, today,
                               min_group_commits=1, min_group_lines=1)
        self.assertEqual(res["status"], "scored")
        self.assertAlmostEqual(res["ai_survival"], 0.40)
        self.assertAlmostEqual(res["other_survival"], 140 / 300)
        self.assertEqual(len(res["buckets"]), 2)
        self.assertEqual(res["buckets"][0]["month"], "2024-01")
        self.assertEqual(res["buckets"][1]["month"], "2024-02")
        self.assertAlmostEqual(res["buckets"][0]["ai_survival"], 0.50)
        self.assertAlmostEqual(res["buckets"][0]["other_survival"], 0.40)
        self.assertEqual(res["age_floor_days"], MIN_SURVIVAL_AGE_DAYS)


class TestAgeMatchingNotPooled(unittest.TestCase):
    """THE load-bearing test: pooled != age-matched, and reported == matched."""

    def test_age_matching_excludes_ai_only_month_pool_vs_matched(self):
        # Two matched months + one AI-only month with high survival.
        # The AI-only month would flatter AI under a naive pooled comparison
        # but must be EXCLUDED by age-matching.
        today = date(2026, 6, 1)
        adoption = date(2024, 1, 1)
        commits = [
            # Matched month 2024-01
            Commit(AI1, date(2024, 1, 10), 100),
            Commit(OT1, date(2024, 1, 20), 100),
            # Matched month 2024-02
            Commit(AI2, date(2024, 2, 10), 100),
            Commit(OT2, date(2024, 2, 20), 100),
            # AI-only month 2024-03 — high survival, flatters AI if pooled
            Commit(AI3, date(2024, 3, 10), 100),
        ]
        surviving = {AI1: 40, OT1: 80, AI2: 40, OT2: 80, AI3: 95}
        ai_shas = {AI1, AI2, AI3}

        res = matched_survival(commits, surviving, ai_shas, adoption, today,
                               min_group_commits=1, min_group_lines=1)
        self.assertEqual(res["status"], "scored")

        # Age-matched AI: (40+40)/(100+100) = 0.40  (AI3 month excluded)
        matched_ai = (40 + 40) / (100 + 100)
        # Pooled AI (naive, includes AI-only month): (40+40+95)/(100+100+100)
        pooled_ai = (40 + 40 + 95) / (100 + 100 + 100)

        self.assertNotEqual(matched_ai, pooled_ai,
                            "test setup bug: pooled == matched, no divergence")
        self.assertAlmostEqual(res["ai_survival"], matched_ai)
        self.assertNotAlmostEqual(res["ai_survival"], pooled_ai)
        # The AI-only month must not appear as a bucket.
        months = [b["month"] for b in res["buckets"]]
        self.assertNotIn("2024-03", months)
        self.assertEqual(set(months), {"2024-01", "2024-02"})


class TestMatchedSurvivalFloors(unittest.TestCase):
    def test_withheld_below_min_group_commits(self):
        today = date(2026, 6, 1)
        adoption = date(2024, 1, 1)
        # 5 AI + 5 other commits in one matched month — below MIN_GROUP_COMMITS.
        commits = []
        surviving = {}
        for i in range(5):
            sha_ai = f"{i:039x}1"  # 40 hex chars
            sha_ot = f"{i:039x}2"
            commits.append(Commit(sha_ai, date(2024, 1, 10 + i), 100))
            commits.append(Commit(sha_ot, date(2024, 1, 15 + i), 100))
            surviving[sha_ai] = 50
            surviving[sha_ot] = 50
        ai_shas = {c.sha for c in commits if c.sha.endswith("1")}
        res = matched_survival(commits, surviving, ai_shas, adoption, today)
        self.assertEqual(res["status"], "withheld")
        self.assertIn("min_group_commits", res["reason"])
        self.assertEqual(res["coverage"]["ai_commits"], 5)
        self.assertEqual(res["coverage"]["other_commits"], 5)

    def test_withheld_below_min_group_lines(self):
        today = date(2026, 6, 1)
        adoption = date(2024, 1, 1)
        # Plenty of commits but each adds only 1 line -> below MIN_GROUP_LINES.
        commits = []
        surviving = {}
        for i in range(MIN_GROUP_COMMITS + 5):
            sha_ai = f"{i:039x}1"
            sha_ot = f"{i:039x}2"
            commits.append(Commit(sha_ai, date(2024, 1, 1), 1))
            commits.append(Commit(sha_ot, date(2024, 1, 1), 1))
            surviving[sha_ai] = 0
            surviving[sha_ot] = 0
        ai_shas = {c.sha for c in commits if c.sha.endswith("1")}
        res = matched_survival(commits, surviving, ai_shas, adoption, today)
        self.assertEqual(res["status"], "withheld")
        self.assertIn("min_group_lines", res["reason"])
        # Each group's added lines = commit count * 1, below MIN_GROUP_LINES.
        self.assertLess(res["coverage"]["ai_lines"], MIN_GROUP_LINES)

    def test_withheld_no_matched_months(self):
        # AI-only and other-only in DIFFERENT months -> no matched month.
        today = date(2026, 6, 1)
        adoption = date(2024, 1, 1)
        commits = [
            Commit(AI1, date(2024, 1, 10), 100),
            Commit(OT1, date(2024, 2, 10), 100),
        ]
        res = matched_survival(commits, {AI1: 50, OT1: 50}, {AI1}, adoption, today,
                               min_group_commits=1, min_group_lines=1)
        self.assertEqual(res["status"], "withheld")
        self.assertIn("matched months", res["reason"])


class TestComputeSurvivalSmoke(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.env = _git_init(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_two_commit_repo_withholds_under_default_floors(self):
        # One AI commit + one human commit, same month, > 90 days old.
        ai_sha = _commit(self.root, self.env, "ai", "2025-01-01 12:00:00",
                         "app.py", "a\nb\nc\n")
        # Replace app.py entirely under a human sha so both have surviving lines.
        human_sha = _commit(self.root, self.env, "human", "2025-01-02 12:00:00",
                            "app.py", "x\ny\nz\nw\n")
        commits = [
            Commit(ai_sha, date(2025, 1, 1), 3),
            Commit(human_sha, date(2025, 1, 2), 4),
        ]
        res = compute_survival(self.root, commits, {ai_sha},
                               adoption_dt=date(2025, 1, 1),
                               today=date(2026, 6, 1))
        # Single month with 1 AI + 1 other commit -> below MIN_GROUP_COMMITS.
        self.assertEqual(res["status"], "withheld")
        self.assertIn("sampled", res)
        self.assertEqual(res["files_blamed"], 1)
        self.assertEqual(res["files_total"], 1)
        self.assertFalse(res["sampled"])

    def test_sampling_determinism_low_max_files(self):
        # Two source files; cap at 1 -> sampled, and two runs agree.
        _commit(self.root, self.env, "c1", "2025-01-01 12:00:00",
                "a.py", "a\nb\n")
        sha2 = _commit(self.root, self.env, "c2", "2025-01-02 12:00:00",
                       "b.py", "x\ny\nz\n")
        commits = [Commit(sha2, date(2025, 1, 2), 3)]
        r1 = compute_survival(self.root, commits, {sha2},
                              adoption_dt=date(2025, 1, 1),
                              today=date(2026, 6, 1), max_files=1)
        r2 = compute_survival(self.root, commits, {sha2},
                              adoption_dt=date(2025, 1, 1),
                              today=date(2026, 6, 1), max_files=1)
        self.assertEqual(r1, r2)
        self.assertTrue(r1["sampled"])
        self.assertEqual(r1["files_blamed"], 1)
        self.assertEqual(r1["files_total"], 2)


# --- Slice 3: wiring into impact / CLI / config --------------------------------
class TestImpactSurvivalWiring(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.env = _git_init(self.root)
        # Two sustained weeks each with 50% AI commits so adoption is detected.
        base = date(2025, 1, 6)  # Monday
        _commit(self.root, self.env, "w1 human", f"{base} 12:00:00",
                "app.py", "x\n", ai=False)
        _commit(self.root, self.env, "w1 ai", f"{base + timedelta(days=1)} 12:00:00",
                "app.py", "x\ny\n", ai=True)
        _commit(self.root, self.env, "w2 human", f"{base + timedelta(days=7)} 12:00:00",
                "app.py", "x\ny\nz\n", ai=False)
        _commit(self.root, self.env, "w2 ai", f"{base + timedelta(days=8)} 12:00:00",
                "app.py", "x\ny\nz\nw\n", ai=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_survival_off_does_not_add_key(self):
        result = impact.compute_impact(self.root, survival=False)
        self.assertNotIn("error", result)
        self.assertNotIn("survival", result)

    def test_survival_on_adds_status_block(self):
        result = impact.compute_impact(self.root, survival=True)
        self.assertIn("survival", result)
        self.assertIn("status", result["survival"])


class TestRecoverFromPRDataNewlyShas(unittest.TestCase):
    """The returned recovery block must surface the recovered shas so survival
    can include them in the AI set."""

    def test_newly_shas_surfaces_recovered_sha(self):
        sha = "abc123" + "0" * 34
        commit = impact.Commit(
            sha=sha,
            date=date(2025, 1, 1),
            email="human@example.com",
            subject="feat: add thing (#123)",
            trailers=[],
            files=["app.py"],
            lines_added=10,
            lines_deleted=0,
            body="",
        )
        self.assertFalse(commit.ai_authored)
        pr_rec = prdata.PRRecord(
            number=123,
            merge_oid=sha,
            merged_at=date(2025, 1, 1),
            authors=[prdata.PRAuthor(name="Copilot", email="copilot@github.com")],
        )
        recovered = impact._recover_from_pr_data(
            [commit], prdata.PRData([pr_rec]), measured_ai=0
        )
        self.assertIn("newly_shas", recovered)
        self.assertEqual(recovered["newly_shas"], [sha])
        self.assertEqual(recovered["newly_attributed"], 1)


class TestConfigSurvival(unittest.TestCase):
    def test_bool_survival_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".shipsignal.toml").write_text("[impact]\nsurvival = true\n", encoding="utf-8")
            cfg, warnings = config.load_config(root)
            self.assertEqual(cfg.impact.survival, True)
            self.assertEqual(warnings, [])

    def test_non_bool_survival_warns_and_keeps_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".shipsignal.toml").write_text(
                '[impact]\nsurvival = "yes"\n', encoding="utf-8"
            )
            cfg, warnings = config.load_config(root)
            self.assertIsNone(cfg.impact.survival)
            self.assertTrue(any("survival" in w for w in warnings))


if __name__ == "__main__":
    unittest.main()
