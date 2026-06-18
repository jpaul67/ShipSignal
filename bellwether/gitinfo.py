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


def clone(url: str, dest: Path, timeout: int = 600) -> tuple[bool, str]:
    """Treeless clone (full history, blobs on demand) — fast and freshness-safe."""
    try:
        res = subprocess.run(
            ["git", "clone", "--filter=blob:none", "--single-branch", url, str(dest)],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except Exception as exc:  # pragma: no cover - network/runtime dependent
        return False, str(exc)
    return res.returncode == 0, res.stderr
