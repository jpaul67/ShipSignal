"""Trend — compute deltas across snapshots (Feature S2).

Reads the JSON snapshots produced by S1 (``shipsignal.snapshot``) and turns
them into the input for the visual viewer (CLI sparklines + HTML). Honesty
rules carry through from the spec:

  * **N=1** → single-point view, no fabricated deltas.
  * **Schema-version mismatch** between snapshots → skip the fixes diff and
    surface a warning; the live data layer changed underfoot.
  * **Category status flips (n/a ↔ scored)** → flag, don't subtract through.
  * **Window-mismatch warning** when the latest snapshot covers >30% more
    commits than its predecessor (likely a refactor / new module batch).
  * **Aggregate-only breadth** preserved — snapshots already carry only the
    allowed keys, so the trend computation does too.
"""
from __future__ import annotations

from collections.abc import Iterable

# A "fixes growth" warning is more noise than signal below this commit threshold —
# small repos legitimately churn. Above it, a >30% jump deserves a hint.
WINDOW_GROWTH_THRESHOLD = 0.30
WINDOW_GROWTH_MIN_COMMITS = 50

# Per-headline metric paths (dotted keys into the snapshot dict).
# Each is paired with how to extract the value — most are direct, but breadth
# needs to honor the n/a status.
HEADLINE_KEYS = (
    ("readiness", "readiness.score"),
    ("breadth", "impact.adoption.breadth.breadth_pct"),
    ("ai_adoption", "impact.adoption.ai_coauthor_share"),
    ("delivery_health", "impact.delivery_health.score"),
)


def _dig(d: dict, dotted: str):
    """Read a dotted-path key out of a nested dict. None on any miss."""
    cur = d
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _series(snapshots: list[dict], dotted: str) -> list:
    """Time series for one metric. Carries None through — the renderer uses
    None as a gap marker (same honesty rule as the trajectory feature)."""
    return [_dig(s, dotted) for s in snapshots]


def _delta(prev, current):
    """Compute prev→current delta. Returns ``None`` (not 0) when either side
    is None, so the renderer can show "newly scored" / "newly n/a" instead
    of a misleading number."""
    if prev is None or current is None:
        return None
    return round(current - prev, 3)


def _fix_fingerprint(fix: dict) -> tuple[str, str, str]:
    """Same identity scheme S1 already uses — keeps diff layer aligned with
    what snapshot.py persists."""
    return (fix.get("detector", ""), fix.get("path", ""),
            fix.get("severity", ""))


def _category_flips(prev: dict, current: dict) -> list[dict]:
    """Detect n/a ↔ scored flips between snapshots so the renderer can flag
    them instead of doing a meaningless subtraction (a category that was
    n/a yesterday and is scored today didn't "improve from 0")."""
    flips: list[dict] = []
    prev_cats = {c["id"]: c for c in _dig(prev, "readiness.categories") or []}
    cur_cats = {c["id"]: c for c in _dig(current, "readiness.categories") or []}
    for cid in cur_cats.keys() | prev_cats.keys():
        p = (prev_cats.get(cid) or {}).get("status")
        c = (cur_cats.get(cid) or {}).get("status")
        if p != c and (p in ("n/a", "indeterminate") or c in ("n/a", "indeterminate")):
            flips.append({"id": cid, "from": p, "to": c})
    return flips


def _fixes_diff(prev: dict, current: dict) -> dict:
    """Movement between the two latest snapshots' fix sets.

    Identity: ``(detector, path, severity)`` — matches what S1 fingerprints.
    Returns ``comparable=False`` with a ``schema_warning`` when the two
    snapshots used different ``schema_version`` strings; the detector set may
    have changed underfoot, so a diff would invent false resolutions.
    """
    prev_sv = prev.get("schema_version")
    cur_sv = current.get("schema_version")
    if prev_sv != cur_sv:
        return {
            "comparable": False,
            "schema_warning": (
                f"snapshot schema changed ({prev_sv} → {cur_sv}); "
                "fixes diff skipped to avoid false resolutions"
            ),
            "resolved": [],
            "new": [],
            "still_open_count": 0,
        }

    prev_fixes = _dig(prev, "readiness.fixes") or []
    cur_fixes = _dig(current, "readiness.fixes") or []
    prev_set = {_fix_fingerprint(f): f for f in prev_fixes}
    cur_set = {_fix_fingerprint(f): f for f in cur_fixes}

    resolved_keys = prev_set.keys() - cur_set.keys()
    new_keys = cur_set.keys() - prev_set.keys()
    still_open = prev_set.keys() & cur_set.keys()

    return {
        "comparable": True,
        "schema_warning": None,
        "resolved": [prev_set[k] for k in sorted(resolved_keys)],
        "new": [cur_set[k] for k in sorted(new_keys)],
        "still_open_count": len(still_open),
    }


def _window(prev: dict, current: dict) -> dict:
    """Window-honesty block: dates compared, commits-between, growth warning."""
    prev_total = _dig(prev, "impact.adoption.total_commits") or 0
    cur_total = _dig(current, "impact.adoption.total_commits") or 0
    growth = (cur_total - prev_total) / prev_total if prev_total else None
    growth_warning = None
    if (
        growth is not None
        and growth > WINDOW_GROWTH_THRESHOLD
        and cur_total >= WINDOW_GROWTH_MIN_COMMITS
    ):
        growth_warning = (
            f"latest snapshot covers {cur_total - prev_total} more commits "
            f"(+{growth * 100:.0f}%) — large delta may reflect new code, "
            "not improvement"
        )
    return {
        "from": prev.get("commit_date"),
        "to": current.get("commit_date"),
        "commits_prev": prev_total,
        "commits_current": cur_total,
        "growth_warning": growth_warning,
    }


def compute_trend(snapshots: list[dict]) -> dict:
    """Build the trend payload — the input the CLI/HTML renderers consume.

    ``snapshots`` is expected to be sorted oldest → newest (load_snapshots
    does this). The function never raises on empty / single-point input —
    those are valid states that the renderer surfaces honestly.
    """
    if not snapshots:
        return {
            "status": "empty",
            "reason": "no snapshots found — run a scan with --snapshot to start",
            "snapshot_count": 0,
        }

    repo = snapshots[-1].get("repo") or snapshots[0].get("repo")
    first_date = snapshots[0].get("commit_date")
    last_date = snapshots[-1].get("commit_date")
    schema_versions = sorted({s.get("schema_version") for s in snapshots
                              if s.get("schema_version")})
    series_by_key = {
        name: _series(snapshots, dotted) for name, dotted in HEADLINE_KEYS
    }

    if len(snapshots) == 1:
        only = snapshots[0]
        return {
            "status": "single_point",
            "reason": "only one snapshot — scan again to start a trend",
            "snapshot_count": 1,
            "repo": repo,
            "first": first_date,
            "last": last_date,
            "schema_versions": schema_versions,
            "headlines": {
                name: {
                    "current": _dig(only, dotted),
                    "delta": None,
                    "series": [_dig(only, dotted)],
                }
                for name, dotted in HEADLINE_KEYS
            },
            # Single point: no diff to compute, but we still expose the fix
            # list so the viewer can show "open fixes at this point in time."
            "fixes": {
                "comparable": False,
                "schema_warning": "single snapshot — nothing to diff",
                "resolved": [],
                "new": [],
                "still_open_count": len(_dig(only, "readiness.fixes") or []),
            },
            "window": None,
            "category_flips": [],
        }

    prev, current = snapshots[-2], snapshots[-1]
    headlines = {
        name: {
            "current": _dig(current, dotted),
            "delta": _delta(_dig(prev, dotted), _dig(current, dotted)),
            "series": series_by_key[name],
        }
        for name, dotted in HEADLINE_KEYS
    }

    return {
        "status": "ok",
        "snapshot_count": len(snapshots),
        "repo": repo,
        "first": first_date,
        "last": last_date,
        "schema_versions": schema_versions,
        "headlines": headlines,
        "fixes": _fixes_diff(prev, current),
        "window": _window(prev, current),
        "category_flips": _category_flips(prev, current),
    }


def snapshot_summary(snap: dict) -> dict:
    """Compact, render-friendly summary of one snapshot — used by the
    single-point view and for the table-row rendering of each entry in a
    multi-snapshot trend. Aggregates only; preserves the breadth invariant."""
    return {
        "commit_date": snap.get("commit_date"),
        "commit_sha": (snap.get("commit_sha") or "")[:8],
        "readiness_score": _dig(snap, "readiness.score"),
        "readiness_grade": _dig(snap, "readiness.grade"),
        "ai_share": _dig(snap, "impact.adoption.ai_coauthor_share"),
        "ai_level": _dig(snap, "impact.adoption.level"),
        "breadth_pct": _dig(snap, "impact.adoption.breadth.breadth_pct"),
        "breadth_status": _dig(snap, "impact.adoption.breadth.status"),
        "delivery_health_score": _dig(snap, "impact.delivery_health.score"),
        "delivery_health_status": _dig(snap, "impact.delivery_health.status"),
        "fix_count": len(_dig(snap, "readiness.fixes") or []),
    }


def all_summaries(snapshots: Iterable[dict]) -> list[dict]:
    return [snapshot_summary(s) for s in snapshots]
