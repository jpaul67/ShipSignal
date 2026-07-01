"""CLI surface tests — flags that don't belong to any single subcommand."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


class TestVersionFlag(unittest.TestCase):
    def test_version_flag_exits_zero_and_prints_name(self):
        # argparse's action="version" writes to stdout and exits 0.
        result = subprocess.run(
            [sys.executable, "-m", "shipsignal.cli", "--version"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertTrue(
            result.stdout.startswith("shipsignal "),
            f"unexpected --version stdout: {result.stdout!r}",
        )


class TestBadgeJsonFlag(unittest.TestCase):
    def test_scan_badge_json_is_a_valid_shields_endpoint(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "badge.json"
            result = subprocess.run(
                [sys.executable, "-m", "shipsignal.cli", "scan", ".", "--badge-json", str(out)],
                capture_output=True, text=True, cwd=str(REPO),
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(payload["schemaVersion"], 1)
            self.assertEqual(payload["label"], "readiness")
            self.assertRegex(payload["message"], r"^\d+/100$")


if __name__ == "__main__":
    unittest.main()
