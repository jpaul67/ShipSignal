"""Snapshot persistence (Feature S1) — trim a live scan/impact/report result
to a small, delta-comparable JSON and write it to ``.shipsignal/snapshots/``.

Design goals:
  * Small (<8KB on typical repos) so committing a year of history stays sane
  * Byte-identical at the same SHA *with the same tool version* — no
    wall-clock fields are stored; ``commit_date`` (committer date of HEAD)
    is the deterministic timestamp.
  * Fingerprinted fixes: identity is ``(detector, path, severity)``. Evidence
    and fix text are dropped because they carry dates/counts that change
    run-to-run and would create false "resolved" entries when nothing moved.
  * Aggregate-only by construction. The breadth invariant
    (``impact._BREADTH_ALLOWED_KEYS``) carries through unchanged — snapshots
    structurally cannot leak per-person data.
"""
from __future__ import annotations

import json
from datetime import UTC
from pathlib import Path

from . import __version__, gitinfo

SNAPSHOT_SCHEMA_VERSION = "snapshot-0.1"
DEFAULT_SNAPSHOT_DIR = ".shipsignal/snapshots"


# ---------------------------------------------------------------------------
# Trimming — keep only what the future `trend` command needs to compute deltas.
# ---------------------------------------------------------------------------
def _trim_categories(categories: list[dict]) -> list[dict]:
    return [
        {"id": c["id"], "points": c.get("points"),
         "max": c.get("max"), "status": c.get("status")}
        for c in categories
    ]


def _trim_fixes(findings: list[dict]) -> list[dict]:
    """Fingerprint each finding as ``(detector, path, severity)``. Evidence
    and fix text are intentionally dropped — they carry dates/counts that
    change every run and would generate false resolutions.
    """
    return [
        {"detector": f["detector"], "path": f["path"], "severity": f["severity"]}
        for f in findings
    ]


def _trim_readiness(readiness: dict) -> dict:
    return {
        "score": readiness.get("score"),
        "grade": readiness.get("grade"),
        "categories": _trim_categories(readiness.get("categories", [])),
        "fixes": _trim_fixes(readiness.get("findings", [])),
    }


def _trim_impact(imp: dict) -> dict:
    """Project the impact result down to delta-comparable fields only.

    Drops: trajectory periods (computable on demand), weekly_series sparkline
    data, descriptive metrics, attribution_caveat, full pillar breakdown.
    Keeps: window, adoption headline + breadth, delivery-health score, the
    before/after score when it was actually earned.
    """
    out: dict = {}
    if imp.get("error"):
        out["error"] = imp["error"]
        return out

    if "window" in imp:
        out["window"] = imp["window"]
    if "analysis" in imp:
        a = imp["analysis"]
        out["analysis"] = {
            "commits_analyzed": a.get("commits_analyzed", 0),
            "merges_excluded": a.get("merges_excluded", 0),
            "maintenance_bots_excluded": a.get("maintenance_bots_excluded", 0),
            "ai_agent_commits": a.get("ai_agent_commits", 0),
        }

    ad = imp.get("adoption") or {}
    if ad:
        out["adoption"] = {
            "ai_coauthor_share": ad.get("ai_coauthor_share"),
            "level": ad.get("level"),
            "ai_commits": ad.get("ai_commits"),
            "total_commits": ad.get("total_commits"),
            "adoption_date": ad.get("adoption_date"),
            "per_tool": ad.get("per_tool") or {},
            # Breadth is already aggregate-only — copy verbatim, preserving the
            # _BREADTH_ALLOWED_KEYS invariant for downstream comparison.
            "breadth": ad.get("breadth") or {},
        }

    dh = imp.get("delivery_health") or {}
    if dh:
        out["delivery_health"] = {
            "score": dh.get("score"),
            "grade": dh.get("grade"),
            "status": dh.get("status"),
        }

    # Only persist the before/after when it was actually earned — withheld
    # status doesn't survive into the snapshot (matches the live-report stance).
    if imp.get("score_status") == "scored":
        out["before_after"] = {"score": imp.get("score"), "status": "scored"}

    return out


# ---------------------------------------------------------------------------
# Build + path helpers
# ---------------------------------------------------------------------------
def _commit_date_for(root: Path | None, fallback_commit_sha: str | None) -> str | None:
    """Committer date (YYYY-MM-DD) of HEAD — deterministic, unlike wall-clock.
    Falls back to None when there's no git history available."""
    if root is not None and gitinfo.is_git_repo(root):
        return gitinfo.head_date(root)
    return None


def build_snapshot(
    *,
    readiness: dict | None = None,
    impact: dict | None = None,
    repo_label: str | None = None,
    root: Path | None = None,
) -> dict:
    """Project a live scan/impact/combined result into the snapshot schema.

    At least one of ``readiness`` / ``impact`` must be supplied.
    ``root`` is used only to look up the deterministic commit_date — pass it
    when available so the snapshot is byte-identical across re-runs.
    """
    if not readiness and not impact:
        raise ValueError("build_snapshot requires at least one of readiness/impact")

    src = readiness or impact
    commit_sha = src.get("commit_sha")
    snap: dict = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "shipsignal_version": __version__,
        "repo": repo_label or src.get("repo"),
        "commit_sha": commit_sha,
        "commit_date": _commit_date_for(root, commit_sha),
    }
    if readiness is not None:
        snap["readiness"] = _trim_readiness(readiness)
    if impact is not None:
        snap["impact"] = _trim_impact(impact)
    return snap


def default_snapshot_path(root: Path, commit_sha: str | None,
                          commit_date: str | None = None) -> Path:
    """Default storage: ``ROOT/.shipsignal/snapshots/YYYY-MM-DD-<short-sha>.json``

    Date-first for human-readable sortability; short-sha suffix so multiple
    commits on the same day don't collide. When SHA is unknown (not a git
    repo) uses ``"nogit"`` as the suffix and today's date as the prefix.
    """
    if commit_date and len(commit_date) >= 10:
        date = commit_date[:10]
    else:
        # Only used on non-git directories; tests inject a date to keep paths
        # deterministic. Live runs on a git repo always have commit_date.
        from datetime import datetime
        date = datetime.now(UTC).strftime("%Y-%m-%d")
    sha = (commit_sha or "nogit")[:8]
    return root / DEFAULT_SNAPSHOT_DIR / f"{date}-{sha}.json"


def write_snapshot(snapshot: dict, path: Path) -> Path:
    """Serialize and write the snapshot. Creates the parent dir as needed.

    Uses ``sort_keys=True`` so two runs of the same SHA produce byte-identical
    output — easy to dedupe with ``sha256sum`` or a git hash, and easy to
    eyeball in PR diffs.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(snapshot, indent=2, sort_keys=True, default=str)
    # Trailing newline matches POSIX convention + plays nice with diff tools.
    path.write_text(payload + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Load + filter — feeds the trend command (S2). Reads what S1 has written.
# ---------------------------------------------------------------------------
def _resolve_snapshots_dir(path: Path) -> Path:
    """Accept a repo root or the snapshots dir itself.

    Resolution order:
      1. If ``path/.shipsignal/snapshots`` exists, use that (the standard
         repo-root case).
      2. Else if ``path`` itself is a directory with ``*.json`` files in it,
         use ``path`` directly (the "I'm pointing at the snapshots dir"
         case — useful for CI artifacts or unconventional layouts).
      3. Else return the default location even if it doesn't exist — the
         caller surfaces the "no snapshots yet" message.
    """
    standard = path / DEFAULT_SNAPSHOT_DIR
    if standard.exists() and standard.is_dir():
        return standard
    if path.is_dir() and any(path.glob("*.json")):
        return path
    return standard


def load_snapshots(path: Path) -> list[dict]:
    """Load all snapshot JSON files under PATH, sorted by ``(commit_date, name)``.

    PATH can be a repo root (looks in ``.shipsignal/snapshots/``) or the
    snapshots directory itself. Malformed JSON files are silently skipped —
    we'd rather show the user a degraded trend than crash on one bad file.

    Returns ``[]`` when the directory is missing or empty (callers handle the
    "no snapshots yet — scan with --snapshot to start" case).
    """
    snaps_dir = _resolve_snapshots_dir(path)
    if not snaps_dir.exists() or not snaps_dir.is_dir():
        return []
    out: list[dict] = []
    for f in sorted(snaps_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(data, dict) or "schema_version" not in data:
            continue  # not a snapshot file
        # Stash the source filename so trend output can cite it.
        data.setdefault("_source_file", f.name)
        out.append(data)
    # Sort by commit_date (chronological); ties broken by filename so the
    # ordering is stable across runs and identical at the same commit.
    out.sort(key=lambda s: (s.get("commit_date") or "", s.get("_source_file", "")))
    return out


def filter_snapshots(
    snapshots: list[dict],
    *,
    since: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    """Apply ``--since`` then ``--limit``. Order matters: limit is applied
    AFTER the date filter so users can say "last 4 since March 1" and get
    the most-recent 4 within that window."""
    out = snapshots
    if since:
        out = [s for s in out if (s.get("commit_date") or "") >= since]
    if limit is not None and limit > 0:
        out = out[-limit:]
    return out
