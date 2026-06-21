"""Snapshot writer tests (Feature S1)."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from shipsignal import scanner, snapshot
from shipsignal.impact import _BREADTH_ALLOWED_KEYS, compute_impact
from shipsignal.snapshot import (
    SNAPSHOT_SCHEMA_VERSION,
    build_snapshot,
    default_snapshot_path,
    write_snapshot,
)

REPO = Path(__file__).resolve().parent.parent


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


class TestSnapshotShape(unittest.TestCase):
    def setUp(self):
        d = Path(tempfile.mkdtemp())
        env = _git_init(d)
        (d / "README.md").write_text("# r\n" * 30, encoding="utf-8")
        (d / "main.py").write_text("print('ok')\n", encoding="utf-8")
        _git_commit(d, env, "init", "2026-05-15 12:00:00")
        self.root = d

    def test_readiness_only_snapshot(self):
        r = scanner.scan(self.root, repo_label="t")
        snap = build_snapshot(readiness=r, repo_label="t", root=self.root)
        self.assertEqual(snap["schema_version"], SNAPSHOT_SCHEMA_VERSION)
        self.assertIn("readiness", snap)
        self.assertNotIn("impact", snap)
        # Readiness payload is trimmed: only score/grade/categories/fixes.
        self.assertEqual(set(snap["readiness"].keys()),
                         {"score", "grade", "categories", "fixes"})

    def test_impact_only_snapshot(self):
        imp = compute_impact(self.root, repo_label="t")
        # Tiny synthetic repo => error path likely, but snapshot still works.
        snap = build_snapshot(impact=imp, repo_label="t", root=self.root)
        self.assertIn("impact", snap)
        self.assertNotIn("readiness", snap)

    def test_combined_snapshot(self):
        r = scanner.scan(self.root, repo_label="t")
        imp = compute_impact(self.root, repo_label="t")
        snap = build_snapshot(readiness=r, impact=imp, repo_label="t", root=self.root)
        self.assertIn("readiness", snap)
        self.assertIn("impact", snap)

    def test_raises_without_any_lens(self):
        with self.assertRaises(ValueError):
            build_snapshot()


class TestFingerprintedFixes(unittest.TestCase):
    """Fixes are projected to (detector, path, severity) only — no evidence."""

    def test_no_evidence_in_fixes(self):
        d = Path(tempfile.mkdtemp())
        env = _git_init(d)
        # Repo with multiple findings: missing module README, stale doc, etc.
        (d / "README.md").write_text("# r\n" * 30, encoding="utf-8")
        (d / "src").mkdir()
        (d / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
        _git_commit(d, env, "init", "2026-05-15 12:00:00")

        r = scanner.scan(d, repo_label="t")
        self.assertTrue(r["findings"], "expected at least one finding")
        snap = build_snapshot(readiness=r, repo_label="t", root=d)
        for fix in snap["readiness"]["fixes"]:
            self.assertEqual(set(fix.keys()), {"detector", "path", "severity"})
            # The evidence/fix strings (which carry dates/counts) must not leak.
            self.assertNotIn("evidence", fix)
            self.assertNotIn("fix", fix)


class TestBreadthPrivacyInSnapshot(unittest.TestCase):
    """The breadth aggregate-only invariant must carry through to snapshots."""

    def test_breadth_keys_remain_allowed_only(self):
        imp = compute_impact(REPO, repo_label="shipsignal")
        snap = build_snapshot(impact=imp, repo_label="shipsignal", root=REPO)
        breadth = snap["impact"]["adoption"]["breadth"]
        extras = set(breadth.keys()) - _BREADTH_ALLOWED_KEYS
        self.assertEqual(extras, set(),
                         f"snapshot breadth leaked extra keys: {extras}")


class TestDefaultPath(unittest.TestCase):
    def test_path_format(self):
        root = Path("/tmp/foo")
        p = default_snapshot_path(root, "abc1234567890def", "2026-06-21")
        self.assertEqual(
            p, root / ".shipsignal" / "snapshots" / "2026-06-21-abc12345.json"
        )

    def test_nogit_fallback(self):
        # When SHA is unknown the suffix becomes "nogit" (still a valid filename).
        root = Path("/tmp/foo")
        p = default_snapshot_path(root, None, "2026-06-21")
        self.assertTrue(p.name.endswith("-nogit.json"))


class TestIdempotency(unittest.TestCase):
    """Same SHA + same tool version => byte-identical snapshot (deterministic)."""

    def test_byte_identical_re_run(self):
        d = Path(tempfile.mkdtemp())
        env = _git_init(d)
        (d / "README.md").write_text("# r\n" * 30, encoding="utf-8")
        (d / "main.py").write_text("print('ok')\n", encoding="utf-8")
        _git_commit(d, env, "init", "2026-05-15 12:00:00")

        out1 = d / "snap1.json"
        out2 = d / "snap2.json"
        s1 = build_snapshot(readiness=scanner.scan(d, "t"), repo_label="t", root=d)
        s2 = build_snapshot(readiness=scanner.scan(d, "t"), repo_label="t", root=d)
        write_snapshot(s1, out1)
        write_snapshot(s2, out2)
        self.assertEqual(out1.read_bytes(), out2.read_bytes(),
                         "two scans of the same SHA produced different bytes")


class TestSelfScanSize(unittest.TestCase):
    """Snapshots should stay small — the spec target is < 8KB for typical repos."""

    def test_self_scan_under_target(self):
        r = scanner.scan(REPO, repo_label="shipsignal")
        imp = compute_impact(REPO, repo_label="shipsignal")
        snap = build_snapshot(readiness=r, impact=imp, repo_label="shipsignal", root=REPO)
        out = Path(tempfile.mkdtemp()) / "self.json"
        write_snapshot(snap, out)
        size = out.stat().st_size
        self.assertLess(size, 8 * 1024,
                        f"self snapshot is {size} bytes — over the 8KB target")


class TestCLISnapshot(unittest.TestCase):
    """End-to-end: the --snapshot CLI flag writes the expected file."""

    def test_scan_snapshot_default_path(self):
        d = Path(tempfile.mkdtemp())
        env = _git_init(d)
        (d / "README.md").write_text("# r\n" * 30, encoding="utf-8")
        (d / "main.py").write_text("print('ok')\n", encoding="utf-8")
        _git_commit(d, env, "init", "2026-05-15 12:00:00")
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        rc = subprocess.run(
            ["python", "-m", "shipsignal.cli", "scan", str(d), "--snapshot"],
            cwd=REPO, capture_output=True, env=env,
        )
        self.assertEqual(rc.returncode, 0, rc.stderr.decode("utf-8", errors="replace"))
        snaps = list((d / ".shipsignal" / "snapshots").glob("*.json"))
        self.assertEqual(len(snaps), 1, f"expected one snapshot file, got {snaps}")
        body = json.loads(snaps[0].read_text(encoding="utf-8"))
        self.assertEqual(body["schema_version"], SNAPSHOT_SCHEMA_VERSION)
        self.assertIn("readiness", body)
        self.assertEqual(body["commit_date"], "2026-05-15")

    def test_scan_snapshot_explicit_path(self):
        d = Path(tempfile.mkdtemp())
        env = _git_init(d)
        (d / "README.md").write_text("# r\n" * 30, encoding="utf-8")
        _git_commit(d, env, "init", "2026-05-15 12:00:00")
        explicit = d / "custom" / "snap.json"
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        rc = subprocess.run(
            ["python", "-m", "shipsignal.cli", "scan", str(d),
             "--snapshot", str(explicit)],
            cwd=REPO, capture_output=True, env=env,
        )
        self.assertEqual(rc.returncode, 0, rc.stderr.decode("utf-8", errors="replace"))
        self.assertTrue(explicit.exists(), f"snapshot not written to {explicit}")


if __name__ == "__main__":
    unittest.main()
