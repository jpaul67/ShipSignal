"""Git helpers: tracked-file listing, commit dates, and a treeless clone.

Everything degrades gracefully: on a non-git directory the listing falls back to
a filesystem walk and dates come back as ``None`` (which the scorer treats as
*indeterminate* rather than zero).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

# Read-only safety flags injected into every `git` call:
#   gc.auto=0          — git's background auto-gc otherwise triggers during a
#                        long `log` and can abort with code 128 mid-output on
#                        large OSS repos. We never want a scanner to mutate the
#                        target repo.
#   maintenance.auto=false — same intent for the newer maintenance machinery.
_GIT_SAFE_FLAGS = ["-c", "gc.auto=0", "-c", "maintenance.auto=false"]


def _run(args: list[str], cwd: Path | None = None, timeout: int = 120) -> str | None:
    if args and args[0] == "git":
        args = [args[0], *_GIT_SAFE_FLAGS, *args[1:]]
    # Explicit UTF-8 with replacement: git's default output encoding is UTF-8,
    # but Python on Windows would otherwise pick cp1252 and crash on the first
    # non-Latin-1 byte (real bug found scanning mature OSS commit histories).
    try:
        res = subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except Exception:
        return None
    if res.returncode != 0:
        return None
    return res.stdout


def is_git_repo(root: Path) -> bool:
    return _run(["git", "rev-parse", "--is-inside-work-tree"], root) is not None


def tracked_files(root: Path) -> list[str]:
    out = _run(["git", "ls-files"], root)
    return [ln for ln in out.splitlines() if ln] if out else []


def tracked_files_at_head(root: Path) -> list[str]:
    """Files tracked in the HEAD commit tree (``git ls-tree -r HEAD``).

    Unlike :func:`tracked_files` (``git ls-files``, which reads the index and so
    returns nothing when a checkout was incomplete — a big repo whose deep paths
    exceed the Windows path limit, or a partial clone), this reads HEAD's tree
    directly, so it reflects the committed source regardless of working-tree state.
    Used by the survival lens, which analyses committed history.
    """
    out = _run(["git", "ls-tree", "-r", "--name-only", "HEAD"], root)
    return [ln for ln in out.splitlines() if ln] if out else []


def head_sha(root: Path) -> str | None:
    out = _run(["git", "rev-parse", "HEAD"], root)
    return out.strip() if out else None


def head_date(root: Path) -> str | None:
    out = _run(["git", "log", "-1", "--format=%cs"], root)
    return out.strip() if out else None


def last_commit_date(root: Path, path: str) -> str | None:
    """Last commit date (YYYY-MM-DD) that touched ``path``, or None."""
    out = _run(["git", "log", "-1", "--format=%cs", "--", path], root)
    return out.strip() if out and out.strip() else None


def commit_count_for_path(root: Path, path: str) -> int:
    """How many commits touched ``path`` over its history. 0 if not tracked."""
    out = _run(["git", "rev-list", "--count", "HEAD", "--", path], root)
    try:
        return int(out.strip()) if out and out.strip() else 0
    except ValueError:
        return 0


def first_commit_date_for_path(root: Path, path: str) -> str | None:
    """First commit date (YYYY-MM-DD) that touched ``path``, or None.

    Uses ``git log --diff-filter=A`` to find the introduction commit (the one
    that first added a file matching the path). Falls back to oldest matching
    commit when no add-event is found (e.g. for a dir that pre-existed via a
    rename or filter-branch).

    Note: ``git log --reverse -1`` returns the NEWEST commit (the count
    limit is applied before the reversal), so we take all matching commits
    and pick the first line. The set is small in practice (one or two adds
    per path, or all commits touching a doc/dir).
    """
    out = _run(
        ["git", "log", "--diff-filter=A", "--reverse", "--format=%cs", "--", path],
        root,
    )
    if out and out.strip():
        return out.strip().splitlines()[0]
    # Fallback: oldest commit touching the path, even without a recorded add.
    out = _run(["git", "log", "--reverse", "--format=%cs", "--", path], root)
    if out and out.strip():
        return out.strip().splitlines()[0]
    return None


def total_commit_count(root: Path) -> int:
    """Total non-merge commits on HEAD. 0 on a non-git repo."""
    out = _run(["git", "rev-list", "--count", "--no-merges", "HEAD"], root)
    try:
        return int(out.strip()) if out and out.strip() else 0
    except ValueError:
        return 0


def commits_since(root: Path, date: str) -> int:
    """Non-merge commits authored on/after ``date`` (YYYY-MM-DD). 0 on a
    non-git repo or invalid date.

    Used by B3 (doc_written_once): the *honest* denominator is "commits that
    landed AFTER the doc existed," not total repo churn. A 4-day-old file in
    a 724-commit repo legitimately has zero post-introduction churn against it
    — so it shouldn't flag as "never revised across 724 commits."
    """
    if not date:
        return 0
    out = _run(
        ["git", "rev-list", "--count", "--no-merges", f"--since={date}", "HEAD"],
        root,
    )
    try:
        return int(out.strip()) if out and out.strip() else 0
    except ValueError:
        return 0


def list_tags(root: Path) -> list[tuple[str, int]]:
    """[(tag_name, creatordate_unix)] for every tag, unfiltered. ``creatordate``
    resolves to the tag's own date for an annotated tag and the pointed-at
    commit's date for a lightweight tag — either way, the date the release
    actually happened. Empty list on a repo with no tags."""
    # Unlike `git log --format`, `for-each-ref --format` only interpolates
    # `%(atom)` placeholders — it does NOT support the `%x1f` hex-escape
    # syntax, so the separator byte is embedded literally here instead.
    out = _run(
        ["git", "for-each-ref", "refs/tags",
         "--format=%(refname:short)\x1f%(creatordate:unix)"],
        root,
    )
    if not out:
        return []
    tags: list[tuple[str, int]] = []
    for ln in out.splitlines():
        if not ln.strip():
            continue
        parts = ln.split("\x1f")
        if len(parts) != 2:
            continue
        name, ts = parts
        try:
            tags.append((name, int(ts)))
        except ValueError:
            continue
    return tags


def commits_between_tags(root: Path, t1: str, t2: str) -> list[int]:
    """Committer-date unix timestamps for non-merge commits in ``(t1, t2]``
    (``git log t1..t2``) — one subprocess call per tag pair, not per commit."""
    out = _run(["git", "log", f"{t1}..{t2}", "--no-merges", "--format=%ct"], root)
    if not out:
        return []
    times: list[int] = []
    for ln in out.splitlines():
        if ln.strip():
            try:
                times.append(int(ln.strip()))
            except ValueError:
                pass
    return times


def blame_incremental(root: Path, path: str, rev: str = "HEAD",
                      timeout: int = 120) -> str | None:
    """Raw ``git blame --incremental -w --no-abbrev <rev>`` stdout for ``path``, or None.

    Blames ``rev`` (HEAD by default) from the object store, NOT the working tree, so
    it works even when the checkout is incomplete (e.g. a large repo whose deep paths
    exceed the Windows path limit, or a partial/treeless clone) — and it matches the
    survival lens's semantics: surviving lines are lines still present in the committed
    HEAD, never uncommitted working-tree edits.

    The ``--incremental`` form is the ONLY permitted blame shape here: unlike
    default ``git blame`` it emits block headers + metadata only and NEVER carries
    source-line content, so a parser cannot accidentally read file contents.
    Returns None on failure or empty output (e.g. untracked or binary paths).
    """
    out = _run(
        ["git", "blame", "--incremental", "-w", "--no-abbrev", rev, "--", path],
        root,
        timeout=timeout,
    )
    return out if out and out.strip() else None


def clone(url: str, dest: Path, timeout: int = 600, treeless: bool = True) -> tuple[bool, str]:
    """Clone a repo for scanning. Always full history (never ``--depth``: freshness,
    adoption detection, and the before/after delta all need the whole commit graph).

    ``treeless=True`` (default, ``--filter=blob:none``): fast and small — all the
    Readiness lens needs. ``treeless=False``: a normal clone *with* blobs — the
    Impact lens needs them, because ``git log --numstat`` computes per-commit line
    counts; on a treeless clone that triggers an on-demand blob fetch per commit and
    crawls (or times out) on large histories.
    """
    flt = ["--filter=blob:none"] if treeless else []
    try:
        res = subprocess.run(
            # `--` stops option parsing so a URL starting with `-` (e.g.
            # `--upload-pack=...`) can never be interpreted as a git flag.
            ["git", "clone", *flt, "--single-branch", "--", url, str(dest)],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except Exception as exc:  # pragma: no cover - network/runtime dependent
        return False, str(exc)
    return res.returncode == 0, res.stderr
