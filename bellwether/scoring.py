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

    # Entry point /25 — heavy-warn: missing README costs the whole category,
    # but does NOT cap the grade.
    if metrics["has_root_readme"]:
        pts = 25 if metrics["root_readme_substantial"] else 16
    else:
        pts = 0
    cats.append(Category("entry_point", pts, 25, "scored"))

    # Agent instructions /20 — size-scaled.
    if metrics["is_small_repo"] and not metrics["has_agent_file"]:
        cats.append(Category("agent_instructions", None, None, "n/a"))
    else:
        if metrics["has_root_agent_file"]:
            pts = 20
        elif metrics["has_agent_file"]:
            pts = 14  # only nested agent files
        else:
            pts = 0
        cats.append(Category("agent_instructions", pts, 20, "scored"))

    # Module coverage /25.
    total = metrics["modules_total"]
    if total == 0:
        cats.append(Category("module_coverage", None, 25, "indeterminate"))
    else:
        cov = metrics["modules_covered"] / total
        cats.append(Category("module_coverage", round(25 * cov, 1), 25, "scored"))

    # Doc integrity /15 — proportional to the share of links that resolve, so a
    # few bad links in a big docs tree don't zero the category.
    checked = metrics.get("links_checked", 0)
    if checked == 0:
        integrity = 15.0
    else:
        integrity = round(15 * (1 - metrics["broken_links"] / checked), 1)
    cats.append(Category("doc_integrity", integrity, 15, "scored"))

    # Doc freshness /15 — needs git history; proportional to share of fresh docs.
    if not metrics["is_git"]:
        cats.append(Category("doc_freshness", None, 15, "indeterminate"))
    else:
        docs = metrics.get("docs_checked", 0)
        fresh = 15.0 if docs == 0 else round(15 * (1 - metrics["drift_count"] / docs), 1)
        cats.append(Category("doc_freshness", fresh, 15, "scored"))

    # MCP — conditional modifier, informational in v0 (not in the base score).
    cats.append(Category("mcp_health", None, None, "present" if metrics["mcp_present"] else "n/a"))

    scored = [c for c in cats if c.status == "scored" and c.max]
    denom = sum(c.max for c in scored)
    num = sum(c.points for c in scored)
    score = round(100 * num / denom) if denom else 0
    return score, grade_for(score), cats
