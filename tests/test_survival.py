"""Surviving-lines-by-sha tests (Package L, slice 1)."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from shipsignal.survival import parse_incremental_blame, surviving_lines_by_sha


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


if __name__ == "__main__":
    unittest.main()
