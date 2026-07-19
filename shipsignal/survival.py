"""Surviving-lines-by-sha (Package L, slice 1): metadata-only blame aggregation.

This slice implements ONLY the parser and a thin aggregator. There is no CLI,
report, or config wiring here — those are later slices.
"""
from __future__ import annotations

from pathlib import Path

from shipsignal.gitinfo import blame_incremental
from shipsignal.impact import _CODE_EXTS


def parse_incremental_blame(text: str) -> dict[str, int]:
    """Count surviving lines per commit sha from ``git blame --incremental`` output.

    The incremental format is a sequence of blocks. Each block STARTS with a
    header line:

        <40-hex-sha> <orig-lineno> <final-lineno> <num-lines>

    followed by key/value metadata lines (``author``, ``author-time``,
    ``filename``, ...). The parser reads ONLY the header's sha and num-lines and
    SKIPS every metadata line.

    NOTE: the ``--incremental`` format carries NO source content by construction
    (no file lines are ever emitted), which is precisely why it is the only
    permitted blame form here. NEVER parse default ``git blame`` output — that
    form interleaves the file's actual source lines with each header, and reading
    them would amount to reading repo content.
    """
    surviving: dict[str, int] = {}
    for ln in text.splitlines():
        if not ln:
            continue
        parts = ln.split(" ")
        # A blame header has exactly 4 whitespace-separated numeric/hex fields;
        # metadata lines are "key value" (2 fields) or "key" (1 field), so the
        # 4-field check cleanly distinguishes headers from metadata without us
        # ever inspecting the metadata content itself.
        if len(parts) != 4:
            continue
        sha, _orig_lineno, _final_lineno, num_lines = parts
        if len(sha) != 40 or not _is_hex(sha):
            continue
        try:
            n = int(num_lines)
        except ValueError:
            continue
        try:
            int(_orig_lineno)
            int(_final_lineno)
        except ValueError:
            continue
        surviving[sha] = surviving.get(sha, 0) + n
    return surviving


def _is_hex(s: str) -> bool:
    for c in s:
        if c not in "0123456789abcdef":
            return False
    return True


def surviving_lines_by_sha(root: Path, paths: list[str]) -> dict[str, int]:
    """Merge surviving-line counts across the given source-file ``paths``.

    A path is included only if its lowercase suffix is in ``impact._CODE_EXTS``.
    Paths that ``blame_incremental`` returns None/empty for (e.g. binaries,
    untracked, or deleted files) are skipped. Paths are de-duplicated and sorted:
    a repeated path would otherwise blame the same file twice and double-count its
    lines, and sorting keeps the output deterministic. Returns a sha ->
    surviving-line-count dict.
    """
    result: dict[str, int] = {}
    for path in sorted(set(paths)):
        if Path(path).suffix.lower() not in _CODE_EXTS:
            continue
        out = blame_incremental(root, path)
        if not out:
            continue
        for sha, n in parse_incremental_blame(out).items():
            result[sha] = result.get(sha, 0) + n
    return result
