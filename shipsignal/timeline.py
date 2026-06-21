"""Over-time trajectory — how AI adoption and delivery health evolve across a
repo's own history. Pure git: reuses the human-commit stream the Impact lens
already walks (no checkout, no new dependency).

Honesty by construction: the adoption line and the health line are PARALLEL
TIMELINES, never a causal claim. Thin/empty periods are shown as gaps, never
interpolated or zero-filled.

Readiness-over-time is deliberately NOT here — it needs the file tree at each
historical commit (a SHA-level read or worktree sampler), which is a separate,
bigger lift (v2).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import timedelta

from .impact import (
    Commit,
    MIN_CONTRIBUTORS_FOR_BREADTH,
    change_shape_metrics,
    delivery_health,
    flow_metrics,
    people_metrics,
    quality_metrics,
)

# A trajectory needs enough history to be a trend, not noise.
MIN_TRAJECTORY_COMMITS = 40
MIN_TRAJECTORY_WEEKS = 8
MIN_BUCKETS = 3
TARGET_COMMITS_PER_BUCKET = 18
MAX_BUCKETS = 14
# Looser than the snapshot's 20-commit floor: a per-period point can be noisier
# because the trend across periods is what matters, not any single value.
MIN_BUCKET_HEALTH_COMMITS = 10


@dataclass
class Period:
    start: str               # ISO date (bucket start)
    end: str                 # ISO date (bucket end)
    commits: int
    adoption_pct: float | None   # None = no commits in this period (a gap)
    health_score: int | None     # None = empty or below the per-bucket floor
    health_status: str           # "scored" | "insufficient"
    breadth_pct: float | None = None     # Feature C: per-period team breadth %.
                                         # None = below MIN_CONTRIBUTORS_FOR_BREADTH.


def _choose_period_days(span_days: int, n_commits: int) -> int:
    """Pick a bucket width that yields a readable number of periods (~MIN..MAX)
    while keeping roughly TARGET_COMMITS_PER_BUCKET commits each. Min one week."""
    target_buckets = max(MIN_BUCKETS, min(MAX_BUCKETS, n_commits // TARGET_COMMITS_PER_BUCKET))
    return max(7, math.ceil(span_days / target_buckets))


def build_trajectory(commits: list[Commit]) -> dict:
    """Bucket human commits into tumbling time periods and compute adoption % +
    delivery-health per period. ``commits`` are the human, non-merge commits the
    Impact lens already isolated. Returns a dict with status/periods."""
    if len(commits) < MIN_TRAJECTORY_COMMITS:
        return {"status": "insufficient", "periods": [],
                "reason": f"only {len(commits)} commits "
                          f"(need {MIN_TRAJECTORY_COMMITS} to chart a trajectory)"}

    ordered = sorted(commits, key=lambda c: c.date)
    first, last = ordered[0].date, ordered[-1].date
    span_days = (last - first).days + 1
    if span_days / 7 < MIN_TRAJECTORY_WEEKS:
        return {"status": "insufficient", "periods": [],
                "reason": f"only {span_days / 7:.1f} weeks of history "
                          f"(need {MIN_TRAJECTORY_WEEKS})"}

    period_days = _choose_period_days(span_days, len(ordered))
    buckets: dict[int, list[Commit]] = {}
    for c in ordered:
        idx = (c.date - first).days // period_days
        buckets.setdefault(idx, []).append(c)

    n_buckets = max(buckets) + 1
    if n_buckets < MIN_BUCKETS:
        return {"status": "insufficient", "periods": [],
                "reason": "not enough distinct periods to chart"}

    periods: list[Period] = []
    for idx in range(n_buckets):
        b = buckets.get(idx, [])
        start = first + timedelta(days=idx * period_days)
        end = first + timedelta(days=min(span_days - 1, (idx + 1) * period_days - 1))
        if not b:  # a quiet stretch — a genuine gap, not 0% adoption / 0 health
            periods.append(Period(start.isoformat(), end.isoformat(), 0, None, None,
                                  "insufficient"))
            continue
        ai = sum(1 for c in b if c.ai_authored)
        m = {
            "flow": flow_metrics(b),
            "change_shape": change_shape_metrics(b),
            "quality": quality_metrics(b),
            "people": people_metrics(b),
        }
        dh = delivery_health(b, m, min_commits=MIN_BUCKET_HEALTH_COMMITS)
        # Feature C: per-period breadth — same aggregate definition as the
        # window-wide breadth, gated on the same contributor floor so single-
        # contributor periods don't show as 0% or 100%.
        humans_in_bucket = [c for c in b if not c.is_ai_agent]
        active_emails = {c.email for c in humans_in_bucket}
        if len(active_emails) >= MIN_CONTRIBUTORS_FOR_BREADTH:
            ai_emails = {c.email for c in humans_in_bucket if c.ai_authored}
            bucket_breadth = round(100 * len(ai_emails) / len(active_emails), 1)
        else:
            bucket_breadth = None
        periods.append(Period(
            start=start.isoformat(),
            end=end.isoformat(),
            commits=len(b),
            adoption_pct=round(100 * ai / len(b), 1),
            health_score=dh["score"] if dh["status"] == "scored" else None,
            health_status=dh["status"],
            breadth_pct=bucket_breadth,
        ))

    return {
        "status": "ok",
        "period_days": period_days,
        "buckets": n_buckets,
        "periods": [p.__dict__ for p in periods],
    }
