"""gitinfo.clone: the `--` separator must precede the URL so a target string
starting with `-` (e.g. an attacker-controlled `--upload-pack=...`) can never
be parsed by git as an option instead of a positional argument."""
import unittest
from pathlib import Path
from unittest import mock

from shipsignal import gitinfo


class TestCloneArgvSafety(unittest.TestCase):
    def _captured_argv(self, url: str, treeless: bool = True) -> list[str]:
        with mock.patch.object(gitinfo.subprocess, "run") as run:
            run.return_value = mock.Mock(returncode=0, stderr="")
            gitinfo.clone(url, Path("/tmp/dest"), treeless=treeless)
        return run.call_args.args[0]

    def test_dash_separator_precedes_url(self):
        argv = self._captured_argv("https://github.com/example/repo.git")
        self.assertIn("--", argv)
        dash_idx = argv.index("--")
        url_idx = argv.index("https://github.com/example/repo.git")
        # `--` must be the argument immediately before the url.
        self.assertEqual(dash_idx + 1, url_idx)

    def test_malicious_looking_target_is_not_treated_as_an_option(self):
        hostile = "--upload-pack=touch /tmp/pwned;http://example.com/x"
        argv = self._captured_argv(hostile)
        dash_idx = argv.index("--")
        # The hostile string must appear strictly after the `--` separator.
        self.assertGreater(argv.index(hostile), dash_idx)

    def test_treeless_flag_still_present(self):
        argv = self._captured_argv("https://github.com/example/repo.git", treeless=True)
        self.assertIn("--filter=blob:none", argv)


if __name__ == "__main__":
    unittest.main()
