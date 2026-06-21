"""Scan pipeline: list files -> detect modules -> run detectors -> score."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from . import detectors, gitinfo, scoring, setupcheck
from . import modules as mod


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
