"""Points-at-stake (#1) — how much each readiness fix would move the score.

Computed by *simulation*, never a parallel hand-coded estimate: we build a copy
of ``metrics`` as if the finding were resolved, re-run the real ``score_scan``,
and diff the total. This guarantees the number we show a user always matches the
actual scoring model — if the model changes, these track it for free.

Honesty notes:
  * Each value is the *marginal* payoff of resolving that one finding, holding
    the others constant. Because the score renormalizes over scored categories,
    the deltas are NOT additive — resolving everything won't equal the sum. The
    renderer labels values with ``≈`` and footnotes this once.
  * Findings that don't move the score (the B1/B2/B3 desync flags are
    findings-only) return 0.0 — and that's worth showing: "informational, not a
    score lever" is useful triage, not a defect.
"""
from __future__ import annotations

import copy

from .scoring import score_scan

# Detectors whose findings are informational — they surface real desync but
# don't feed the 0–100 model (see the doc-tech-debt spec: B1/B2/B3 are
# findings-only; only B4 graded drift moves doc_freshness).
_INFORMATIONAL = {"doc_ref_missing", "doc_predates_modules", "doc_written_once",
                  "doc_stale"}


def _resolved_metrics(finding: dict, metrics: dict) -> dict | None:
    """Return a copy of ``metrics`` mutated as if ``finding`` were fixed, or
    None when the finding doesn't map to a scoring lever."""
    det = finding.get("detector")
    m = copy.deepcopy(metrics)
    res = finding.get("resolution") or {}

    if det == "entry_point":
        m["has_root_readme"] = True
        m["root_readme_substantial"] = True
        return m

    if det == "agent_instructions":
        # Whether absent or thin/partial, the fix is "make it actionable".
        m["has_agent_file"] = True
        m["has_root_agent_file"] = True
        m["agent_usefulness_root"] = "actionable"
        return m

    if det == "module_readme":
        if m.get("modules_total"):
            m["modules_covered"] = min(m["modules_total"], m.get("modules_covered", 0) + 1)
        return m

    if det == "setup":
        weight = res.get("setup_weight", 0)
        total = res.get("setup_total_weight") or m.get("setup_total_weight")
        if total:
            m["setup_score_frac"] = min(1.0, m.get("setup_score_frac", 0.0) + weight / total)
        return m

    if det == "broken_link":
        m["broken_links"] = max(0, m.get("broken_links", 0) - 1)
        return m

    if det == "doc_drift":
        # Resolving brings this doc's freshness grade to a full 1.0.
        grade = res.get("drift_grade", 0.0)
        m["fresh_score_sum"] = m.get("fresh_score_sum", 0.0) + (1.0 - grade)
        # one fewer drifted doc (kept for the legacy count, not scored directly)
        m["drift_count"] = max(0, m.get("drift_count", 0) - 1)
        return m

    return None  # informational / unknown → no score lever


def points_at_stake(finding: dict, metrics: dict) -> float:
    """Marginal score gain (rounded to 0.5, clamped ≥ 0) from resolving
    ``finding``. 0.0 for informational findings or when resolution is a no-op."""
    if finding.get("detector") in _INFORMATIONAL:
        return 0.0
    resolved = _resolved_metrics(finding, metrics)
    if resolved is None:
        return 0.0
    base_score, _, _ = score_scan(metrics)
    new_score, _, _ = score_scan(resolved)
    delta = new_score - base_score
    if delta <= 0:
        return 0.0
    return round(delta * 2) / 2  # nearest 0.5


def is_informational(finding: dict) -> bool:
    return finding.get("detector") in _INFORMATIONAL
