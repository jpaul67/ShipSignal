"""Scoring model (v0.1).

Five scored categories sum to 100. A category can also be:
  * n/a            — excluded from the score and its denominator (e.g. no MCP,
                     or agent-instructions on a small repo);
  * indeterminate  — shown but excluded from the score (e.g. freshness with no
                     git history). Honest > silently zero-or-max.

The final score renormalizes over whatever was actually scored, so a small,
well-documented library is never punished for lacking an agent file.
"""
from __future__ import annotations

from dataclasses import dataclass

GRADE_BANDS = [(90, "A"), (80, "B"), (70, "C"), (60, "D"), (0, "F")]


def grade_for(score: int) -> str:
    for threshold, letter in GRADE_BANDS:
        if score >= threshold:
            return letter
    return "F"


@dataclass
class Category:
    id: str
    points: float | None
    max: float | None
    status: str  # scored | n/a | indeterminate | present


def score_scan(metrics: dict) -> tuple[int, str, list[Category]]:
    cats: list[Category] = []

    # Entry point /20 — heavy-warn: missing README costs the whole category,
    # but does NOT cap the grade.
    if metrics["has_root_readme"]:
        pts = 20 if metrics["root_readme_substantial"] else 12
    else:
        pts = 0
    cats.append(Category("entry_point", pts, 20, "scored"))

    # Agent instructions /15 — size-scaled (A1) and depth-graded (A2).
    # Depth grade is heuristic (looks for build/test tokens + a structure pointer);
    # disclosed in the glossary. Absent => 0; present-but-thin => partial credit
    # (the file exists but doesn't help an agent build/test).
    if metrics["is_small_repo"] and not metrics["has_agent_file"]:
        cats.append(Category("agent_instructions", None, None, "n/a"))
    else:
        root_use = metrics.get("agent_usefulness_root")
        nested_use = metrics.get("agent_usefulness_nested")
        if metrics["has_root_agent_file"]:
            # Best agent file is at the root — full credit when actionable.
            pts = {
                "actionable": 15.0,
                "actionable_no_structure": 11.0,
                "thin": 9.0,
            }.get(root_use, 15.0)  # fallback to full if grade missing
        elif metrics["has_agent_file"]:
            # Only nested agent files — still helpful, but less discoverable.
            pts = {
                "actionable": 9.0,
                "actionable_no_structure": 7.0,
                "thin": 5.0,
            }.get(nested_use, 7.0)
        else:
            pts = 0.0
        cats.append(Category("agent_instructions", pts, 15, "scored"))

    # Module coverage /20.
    total = metrics["modules_total"]
    if total == 0:
        cats.append(Category("module_coverage", None, 20, "indeterminate"))
    else:
        cov = metrics["modules_covered"] / total
        cats.append(Category("module_coverage", round(20 * cov, 1), 20, "scored"))

    # Setup & conventions /20 — discoverable build/test, deps, lint/format/type,
    # convention files, and (when present) MCP resolution.
    if "setup_score_frac" not in metrics:
        cats.append(Category("setup_tooling", None, 20, "indeterminate"))
    else:
        cats.append(Category("setup_tooling", round(20 * metrics["setup_score_frac"], 1), 20, "scored"))

    # Doc integrity /13 — proportional to the share of links that resolve.
    checked = metrics.get("links_checked", 0)
    integrity = 13.0 if checked == 0 else round(13 * (1 - metrics["broken_links"] / checked), 1)
    cats.append(Category("doc_integrity", integrity, 13, "scored"))

    # Doc freshness /12 — needs git history; graded drift (B4): each doc scores
    # in [0, 1] by how far past threshold it has fallen, not yes/no.
    if not metrics["is_git"]:
        cats.append(Category("doc_freshness", None, 12, "indeterminate"))
    else:
        docs = metrics.get("docs_checked", 0)
        if docs == 0:
            fresh = 12.0
        else:
            fresh = round(12 * (metrics.get("fresh_score_sum", docs * 1.0) / docs), 1)
        cats.append(Category("doc_freshness", fresh, 12, "scored"))

    scored = [c for c in cats if c.status == "scored" and c.max]
    denom = sum(c.max for c in scored)
    num = sum(c.points for c in scored)
    score = round(100 * num / denom) if denom else 0
    return score, grade_for(score), cats
