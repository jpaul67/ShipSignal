"""CLI surface tests — flags that don't belong to any single subcommand."""
import subprocess
import sys
import unittest


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


if __name__ == "__main__":
    unittest.main()
