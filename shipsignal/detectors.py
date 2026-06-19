"""The static detectors. Each contributes findings (severity, path, evidence,
fix) and a few metrics the scorer turns into category points.

False-positive guards baked in (all learned from real-repo calibration):
skip http/mailto/anchor/absolute links, strip #anchors, ignore links that
escape the repo, and treat agent-file freshness gently.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from .modules import CODE_EXTS, DOC_EXTS, WAIVED_DIRS, basename, dir_of, ext_of
from . import gitinfo

LINK_RE = re.compile(r"\]\(([^)]+)\)")
_ABS = re.compile(r"^[a-zA-Z]:[\\/]")  # C:\ or C:/
# A checkable internal link target looks like a path: word chars plus . / ~ % -.
# Anything with spaces, commas, brackets, parens (type signatures, prose) is not
# a file link and is skipped — favouring precision over recall on this detector.
_PATHLIKE = re.compile(r"^[\w./~%-]+$")
# Known file extensions — an unresolved link is only "broken" if it points at one
# of these. Extensionless unresolved links (e.g. VitePress routes like
# ./test-project) are doc-site routing, not filesystem paths, so we skip them.
_FILE_EXTS = CODE_EXTS | DOC_EXTS | {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico",
    ".json", ".yaml", ".yml", ".toml", ".lock", ".html", ".css", ".pdf", ".csv",
}


def _finding(detector, severity, path, evidence, fix):
    return {"detector": detector, "severity": severity, "path": path,
            "evidence": evidence, "fix": fix}


def _code_count(files: list[str]) -> int:
    n = 0
    for f in files:
        if any(p in WAIVED_DIRS for p in f.split("/")[:-1]):
            continue
        if ext_of(f) in CODE_EXTS:
            n += 1
    return n


def _skip_link(t: str) -> bool:
    low = t.strip().lower()
    return (
        low.startswith(("http://", "https://", "mailto:", "tel:", "#", "<"))
        or low.startswith("/")
        or bool(_ABS.match(t.strip()))
    )


def _pdate(s: str) -> date | None:
    try:
        y, m, d = (int(x) for x in s.split("-"))
        return date(y, m, d)
    except Exception:
        return None


def _drifted(doc_date: str, code_date: str, gentle: bool) -> bool:
    dd, cd = _pdate(doc_date), _pdate(code_date)
    if not dd or not cd:
        return False
    return (cd - dd).days > (365 if gentle else 180)


def run_detectors(root: Path, files, modules, agent_files, is_git):
    findings: list[dict] = []
    nonwaived = [m for m in modules if not m.waived]

    # 1. entry point
    root_mod = next((m for m in modules if m.path == "."), None)
    has_root_readme = bool(root_mod and root_mod.has_readme)
    substantial = False
    if has_root_readme:
        txt = (root / root_mod.readme_path).read_text(encoding="utf-8", errors="ignore")
        substantial = len(txt) >= 300
    else:
        findings.append(_finding(
            "entry_point", "warn", ".",
            "No README at the repo root",
            "Add README.md: what it is, quick start, how to run/build/test"))

    # 2. agent instructions (size-scaled)
    code_count = _code_count(files)
    is_small = code_count < 25
    has_agent = len(agent_files) > 0
    has_root_agent = any(dir_of(a) == "." for a in agent_files)
    if not has_agent and not is_small:
        findings.append(_finding(
            "agent_instructions", "warn", ".",
            "No agent instruction file (CLAUDE.md / AGENTS.md / .cursor/rules / copilot-instructions)",
            "Add CLAUDE.md or AGENTS.md with build/test commands and conventions"))
    elif not has_agent and is_small:
        findings.append(_finding(
            "agent_instructions", "info", ".",
            "No agent instruction file (small repo — optional)",
            "Optional for a small/stable repo; a good README may be enough"))

    # 3. module README coverage
    covered = 0
    for m in nonwaived:
        if m.has_readme:
            covered += 1
        else:
            findings.append(_finding(
                "module_readme", "warn", m.path,
                f"Module '{m.path}' ({m.type}) has no README",
                f"Add {m.path}/README.md describing this module"))

    # 4. broken links in markdown
    broken = 0
    links_checked = 0
    for f in files:
        if ext_of(f) not in (".md", ".markdown"):
            continue
        text = (root / f).read_text(encoding="utf-8", errors="ignore")
        base = root if dir_of(f) == "." else (root / dir_of(f))
        for raw in LINK_RE.findall(text):
            if _skip_link(raw):
                continue
            tgt = raw.strip().split("#", 1)[0].strip()
            if not tgt or not _PATHLIKE.match(tgt):
                continue
            abs_t = base / tgt
            try:
                inside = abs_t.resolve().is_relative_to(root.resolve())
            except Exception:
                inside = False
            if not inside:
                continue  # link escapes the repo — not checkable
            if abs_t.exists():
                links_checked += 1
                continue
            if ext_of(tgt) in _FILE_EXTS:
                links_checked += 1
                broken += 1
                findings.append(_finding(
                    "broken_link", "warn", f,
                    f"Link to '{raw}' does not resolve",
                    f"Fix or remove the link in {f}"))
            # extensionless / unknown-ext unresolved → likely a doc-site route or anchor; skip

    # 5. doc freshness / drift (needs git history)
    drift = 0
    docs_checked = 0
    if is_git:
        for m in nonwaived:
            doc = m.readme_path or m.agent_file
            if not doc or not m.last_code_commit:
                continue
            ddate = gitinfo.last_commit_date(root, doc)
            if not ddate:
                continue
            docs_checked += 1
            gentle = (doc == m.agent_file and not m.readme_path)
            if _drifted(ddate, m.last_code_commit, gentle):
                drift += 1
                findings.append(_finding(
                    "doc_drift", "warn", doc,
                    f"Code in '{m.path}' changed after this doc ({m.last_code_commit} vs doc {ddate})",
                    "Review and refresh the doc"))

    # mcp presence (conditional; resolution of referenced paths is a later increment)
    mcp_present = any(
        basename(f).lower() in {"mcp.json", ".mcp.json"} or f.lower().endswith(".cursor/mcp.json")
        for f in files
    )

    metrics = {
        "has_root_readme": has_root_readme,
        "root_readme_substantial": substantial,
        "is_small_repo": is_small,
        "code_count": code_count,
        "has_agent_file": has_agent,
        "has_root_agent_file": has_root_agent,
        "modules_total": len(nonwaived),
        "modules_covered": covered,
        "broken_links": broken,
        "links_checked": links_checked,
        "drift_count": drift,
        "docs_checked": docs_checked,
        "is_git": is_git,
        "mcp_present": mcp_present,
    }
    return findings, metrics
