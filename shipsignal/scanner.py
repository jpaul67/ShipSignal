"""Scan pipeline: list files -> detect modules -> run detectors -> score
-> enrich findings (points-at-stake, effort, area)."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from . import detectors, gitinfo, score_impact, scoring, setupcheck, snippets
from . import modules as mod


def _detected_cmds_clause(metrics: dict) -> str:
    """Compose a 'we detected `npm test` and `npm run build`' clause when the
    setup pass found concrete commands. Empty string when we have no facts —
    we never fabricate (#2 honesty rule: cross-detector facts must be real)."""
    t = metrics.get("detected_test_cmd")
    b = metrics.get("detected_build_cmd")
    if not t and not b:
        return ""
    parts = []
    if t:
        parts.append(f"`{t}`")
    if b:
        parts.append(f"`{b}`")
    joined = " and ".join(parts)
    return f"we detected {joined} — name {'them' if len(parts) > 1 else 'it'} in the file"


def _specialize_fix(finding: dict, metrics: dict) -> None:
    """Idea #2: rewrite the generic ``fix`` text using cross-detector facts.
    Mutates in place. No-op when no concrete fact is available — generic text
    is still better than fabrication."""
    det = finding.get("detector")
    if det == "agent_instructions":
        clause = _detected_cmds_clause(metrics)
        if clause:
            finding["fix"] = f"{finding['fix']} ({clause})"
    elif det == "entry_point":
        clause = _detected_cmds_clause(metrics)
        if clause:
            finding["fix"] = f"{finding['fix']} ({clause})"


def _enrich_findings(findings: list[dict], metrics: dict,
                     modules: list | None = None) -> list[dict]:
    """Attach actionability metadata (#1, #2, #4) to each finding, then order
    the list by payoff so the most valuable fixes float to the top.

    Runs after scoring, with full metrics in hand — the one place that knows
    everything both detector passes found. ``points_at_stake`` is computed by
    re-scoring (see score_impact), so the displayed payoff always matches the
    real model. ``_specialize_fix`` rewrites generic action text with the
    concrete commands the setup pass detected (#2).
    """
    # Setup checks vary in effort: dropping in a LICENSE / .editorconfig is
    # quick; standing up CI or a test command is real work.
    _SETUP_MODERATE = {"ci_config", "test_command", "type_config", "lint_config",
                       "architecture_doc", "dependency_manifest", "mcp_resolves"}
    for f in findings:
        det = f.get("detector")
        res = f.get("resolution") or {}
        f["area"] = detectors.FINDING_AREA.get(det, "Other")
        f["points_at_stake"] = score_impact.points_at_stake(f, metrics)
        f["informational"] = score_impact.is_informational(f)
        if det == "setup":
            f["effort"] = ("moderate" if res.get("setup_check") in _SETUP_MODERATE
                           else "quick")
        else:
            f["effort"] = detectors.FINDING_EFFORT.get(det, "moderate")
        _specialize_fix(f, metrics)  # #2 cross-detector specificity
        snippet = snippets.snippet_for(f, metrics,
                                        [m.__dict__ for m in (modules or [])])
        if snippet:
            f["snippet"] = snippet
        # Strip the internal resolution hint — it's scaffolding for scoring,
        # not user-facing, and keeps the snapshot/JSON output clean.
        f.pop("resolution", None)
    # Sort by points desc, then warn-before-info, then area order for stability.
    sev_rank = {"warn": 0, "info": 1}
    area_rank = {a: i for i, a in enumerate(detectors.AREA_ORDER)}
    findings.sort(key=lambda f: (
        -f.get("points_at_stake", 0.0),
        sev_rank.get(f.get("severity"), 2),
        area_rank.get(f.get("area"), 99),
        f.get("path", ""),
    ))
    return findings


def scan(root: Path, repo_label: str | None = None) -> dict:
    files, is_git = mod.list_files(root)
    modules, agent_files = mod.detect_modules(root, files, is_git)
    findings, metrics = detectors.run_detectors(root, files, modules, agent_files, is_git)
    setup_findings, setup_metrics = setupcheck.detect_setup(
        root, files, metrics["mcp_present"], modules_total=metrics["modules_total"]
    )
    findings = findings + setup_findings
    metrics.update(setup_metrics)
    score, grade, categories = scoring.score_scan(metrics)
    findings = _enrich_findings(findings, metrics, modules)
    return {
        "schema_version": "0.1",
        "repo": repo_label or root.name,
        "commit_sha": gitinfo.head_sha(root) if is_git else None,
        "scanned_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "score": score,
        "grade": grade,
        "categories": [c.__dict__ for c in categories],
        "modules": [m.__dict__ for m in modules],
        "findings": findings,
        "metrics": metrics,
    }
