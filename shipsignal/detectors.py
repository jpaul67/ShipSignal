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

from . import gitinfo
from .modules import CODE_EXTS, DOC_EXTS, TEST_DATA_DIRS, WAIVED_DIRS, basename, dir_of, ext_of

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

# --- A2: agent-file usefulness heuristic ------------------------------------
# Concrete build/test invocations. A word-boundary match would be ideal but a
# substring works well here (these tokens rarely show up in unrelated prose).
_AGENT_CMD_TOKENS = (
    "npm test", "npm run", "pnpm test", "pnpm run", "yarn test", "yarn run",
    "pytest", "python -m", "python3 -m",
    "make test", "make build", "make check", "make run",
    "cargo test", "cargo run", "cargo build", "cargo check",
    "go test", "go run", "go build",
    "gradle test", "mvn test", "mvn package",
    "bundle exec", "rake test", "rspec",
    "dotnet test", "dotnet run", "dotnet build",
    "composer test", "phpunit",
    "uv run", "uvx ", "poetry run",
)
# Headings that conventionally introduce build/test guidance — a fenced code
# block under one of these counts as "commands present" even if the literal
# tokens above don't match (covers unconventional but valid agent files).
_AGENT_CMD_HEADING_RE = re.compile(
    r"^#+\s*(commands?|build|test|develop|getting started|setup|usage|"
    r"quick\s?start|how to (?:build|test|run|develop))",
    re.IGNORECASE | re.MULTILINE,
)
# Structure / "where things live" pointers — orientation for an agent.
_AGENT_STRUCTURE_HEADING_RE = re.compile(
    r"^#+\s*(architecture|structure|project layout|layout|conventions|gotchas|"
    r"where to (?:read|look|go)|how (?:this|it) is organized|"
    r"module(?:s)? map|file map|read next|design|overview|"
    r"what (?:this|it) is)",
    re.IGNORECASE | re.MULTILINE,
)
# A link to another markdown/doc file — implicit structure pointer ("read X.md").
_MD_DOC_LINK_RE = re.compile(
    r"\]\([^)]+\.(?:md|markdown|rst|txt)(?:#[^)]*)?\)", re.IGNORECASE
)
# Imperative rule / conventions language — what a good `.cursorrules` or
# `.windsurfrules` carries even without markdown headings. Word-boundary so we
# don't false-match "always" inside "always-on" etc.
_AGENT_RULES_RE = re.compile(
    r"(?:^|\W)(?:always|never|prefer|must|do not|don't|should not|shouldn't|"
    r"avoid|use\s+the|follow\s+the|stick\s+to|rule[s]?:|convention[s]?:)\b",
    re.IGNORECASE,
)
_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)


def _agent_usefulness(text: str) -> dict:
    """Grade agent-file content on three vendor-neutral signals:

      * **commands** — concrete build/test invocations (CLAUDE/Make/Cargo/etc.)
      * **structure** — orientation / "where things live" headings or doc links
      * **rules**    — imperative conventions language (``always``, ``never``,
                       ``prefer``, dos-and-don'ts) — what a ``.cursorrules`` or
                       ``.windsurfrules`` legitimately carries instead of
                       markdown sections

    Grade is 2-of-3:
      * ``actionable`` — any 2 of 3 signals present (a useful agent file)
      * ``partial``    — exactly 1 of 3 (helps but is missing depth)
      * ``thin``       — 0 of 3 (boilerplate / empty)

    Returns ``{grade, signals: {commands, structure, rules}}`` so the caller
    can emit a finding specific to whichever signal is missing.
    """
    if not text or len(text.strip()) < 40:
        return {"grade": "thin", "signals": {"commands": False,
                                              "structure": False, "rules": False}}
    # Strip fenced blocks before scanning for markdown headings — a code example
    # mentioning "## Build" inside ``` isn't a real heading.
    no_fences = _FENCE_RE.sub("", text)
    low = text.lower()

    has_commands = any(tok in low for tok in _AGENT_CMD_TOKENS)
    if not has_commands and "```" in text and _AGENT_CMD_HEADING_RE.search(no_fences):
        # A commands-style heading with at least one fenced block in the file
        # is treated as actionable (covers Makefiles, custom scripts, etc.).
        has_commands = True

    has_structure = bool(
        _AGENT_STRUCTURE_HEADING_RE.search(no_fences) or _MD_DOC_LINK_RE.search(text)
    )

    # Require at least 2 matches so a single "do not" in passing prose doesn't
    # qualify as a rules-style file. Real rules files repeat the pattern.
    has_rules = len(_AGENT_RULES_RE.findall(no_fences)) >= 2

    signals = {"commands": has_commands, "structure": has_structure, "rules": has_rules}
    score = sum(signals.values())
    if score >= 2:
        grade = "actionable"
    elif score == 1:
        grade = "partial"
    else:
        grade = "thin"
    return {"grade": grade, "signals": signals}


def _best_usefulness(grades: list) -> dict | None:
    """Pick the strongest grade-dict from a list (None if list is empty).
    Accepts either the new dict form or legacy string form for backward compat
    with callers/tests that pass plain strings during the transition.
    """
    if not grades:
        return None
    order = {"actionable": 3, "partial": 2,
             "actionable_no_structure": 2,  # legacy alias
             "thin": 1}

    def key(g):
        label = g["grade"] if isinstance(g, dict) else g
        return order.get(label, 0)
    return max(grades, key=key)


def _finding(detector, severity, path, evidence, fix, *, line=None, resolution=None):
    """A finding. ``line`` (#5) cites a location for link/path fixes; ``resolution``
    (#1) carries per-finding hints score_impact needs to value the fix (e.g. a
    setup check's weight, a doc's drift grade). Both optional; snapshots still
    fingerprint on (detector, path, severity) so extra fields are harmless."""
    f = {"detector": detector, "severity": severity, "path": path,
         "evidence": evidence, "fix": fix}
    if line is not None:
        f["line"] = line
    if resolution is not None:
        f["resolution"] = resolution
    return f


# Which readiness area each detector belongs to — drives the fixed grouping
# order in the renderer (#4). Fixed order: Agent context → Module docs →
# Setup → Integrity → Freshness.
FINDING_AREA = {
    "entry_point": "Agent context",
    "agent_instructions": "Agent context",
    "module_readme": "Module docs",
    "setup": "Setup",
    "broken_link": "Integrity",
    "doc_drift": "Freshness",
    "doc_ref_missing": "Freshness",
    "doc_predates_modules": "Freshness",
    "doc_written_once": "Freshness",
    "doc_stale": "Freshness",
}
AREA_ORDER = ["Agent context", "Module docs", "Setup", "Integrity", "Freshness"]

# Heuristic effort tag per detector (#1). Honest tags, not fabricated minutes:
#   quick       — add/repair a single file
#   moderate    — write a focused doc or config (commands section, CI, README)
#   substantial — multi-file work (only used when count is high; see enrich)
FINDING_EFFORT = {
    "entry_point": "moderate",
    "agent_instructions": "moderate",
    "module_readme": "moderate",
    "setup": "quick",
    "broken_link": "quick",
    "doc_drift": "moderate",
    "doc_ref_missing": "quick",
    "doc_predates_modules": "moderate",
    "doc_written_once": "moderate",
    "doc_stale": "moderate",
}


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


def _drift_grade(doc_date: str, code_date: str, gentle: bool) -> float:
    """B4: graded drift in [0, 1] — 1.0 = fresh, 0.0 = very stale.

    Threshold mirrors the original binary check (180/365 days). Past the
    threshold, score reflects *how far* behind:

      * ≤ 0 mo past threshold  → 1.0 (fresh)
      * 0–3 mo past            → 0.85 (small drift — slight ding)
      * 3–6 mo past            → 0.5
      * 6–12 mo past           → 0.2
      * 12+ mo past            → 0.0

    Returns 1.0 when dates are missing so callers behave like the prior
    binary "no drift" path on indeterminate data.
    """
    dd, cd = _pdate(doc_date), _pdate(code_date)
    if not dd or not cd:
        return 1.0
    threshold = 365 if gentle else 180
    past = (cd - dd).days - threshold
    if past <= 0:
        return 1.0
    months = past / 30
    if months < 3:
        return 0.85
    if months < 6:
        return 0.5
    if months < 12:
        return 0.2
    return 0.0


def _drifted(doc_date: str, code_date: str, gentle: bool) -> bool:
    """Binary drift check — kept as a thin wrapper over the graded function so
    existing callers and tests still work. Drift is "yes" when the graded score
    drops below full freshness.
    """
    return _drift_grade(doc_date, code_date, gentle) < 1.0


# --- B1: referenced-but-missing paths in agent/entry docs ------------------
# Precision over recall (matches existing link-checking philosophy): only flag
# refs that look unambiguously like in-repo paths. Bare filenames are too
# noisy — a doc may say "render via report.html" without that being a checked
# path. We require a directory separator AND skip agent-file class patterns
# (`.cursor/rules` etc. are conventionally referenced as classes, not paths).
_REF_PATH_RE = re.compile(r"`([\w./~%-]+)`|\(([\w./~%-]+)\)")
_AGENT_CLASS_PATHS = (
    ".cursor/rules", ".github/copilot-instructions",
)


def _ref_paths(text: str) -> set[str]:
    """Path-like tokens from inline-code (``foo/bar.md``) and parenthetical
    refs (foo/bar.py). Requires a path separator, a recognizable extension,
    and skips known agent-file class patterns that are usually descriptive
    rather than navigational.
    """
    out: set[str] = set()
    for a, b in _REF_PATH_RE.findall(text):
        tok = (a or b).strip()
        if not tok or "://" in tok or tok.startswith("#"):
            continue
        if not _PATHLIKE.match(tok):
            continue
        bare = tok.split("#", 1)[0]
        if "/" not in bare.rstrip("/"):
            continue  # bare filename — too noisy (output names, informal mentions)
        if any(bare.startswith(prefix) for prefix in _AGENT_CLASS_PATHS):
            continue  # ".cursor/rules" etc. — usually a class description, not a path
        # Either a directory (ends in /) or a path-with-extension we recognize.
        if bare.endswith("/") or ext_of(bare) in _FILE_EXTS:
            out.add(bare)
    return out


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

    # 2. agent instructions (size-scaled, depth-graded via A2 usefulness)
    code_count = _code_count(files)
    is_small = code_count < 25
    has_agent = len(agent_files) > 0
    has_root_agent = any(dir_of(a) == "." for a in agent_files)
    # Grade each detected agent file's content. JSON configs (.mcp.json etc.)
    # aren't here — only prose files match AGENT_BASENAMES. Each grade is a
    # dict {grade, signals: {commands, structure, rules}} so we can emit a
    # finding specific to the missing signal — vendor-neutral by construction.
    root_grades: list[dict] = []
    nested_grades: list[dict] = []
    for af in agent_files:
        try:
            txt = (root / af).read_text(encoding="utf-8", errors="ignore")
        except Exception:
            txt = ""
        root_grades.append(_agent_usefulness(txt)) if dir_of(af) == "." \
            else nested_grades.append(_agent_usefulness(txt))
    root_usefulness = _best_usefulness(root_grades)
    nested_usefulness = _best_usefulness(nested_grades)

    def _missing_signal_advice(signals: dict) -> tuple[str, str]:
        """Return (description, action) for the first missing signal — used
        when grading ``partial``. Order: commands > structure > rules, since
        commands have the highest leverage for an agent."""
        if not signals.get("commands"):
            return ("doesn't say how to build or test",
                    "Add the build/test invocations agents need (e.g. a "
                    "Commands section, fenced shell block, or `pytest`/`npm test` lines)")
        if not signals.get("structure"):
            return ("has commands but no structure pointer",
                    "Add a brief Architecture / Structure section or links to "
                    "module READMEs so agents can orient")
        return ("doesn't document conventions",
                "Add a Conventions / Rules section (do / don't, style rules) "
                "so agents follow house style")

    if not has_agent and not is_small:
        findings.append(_finding(
            "agent_instructions", "warn", ".",
            "No agent instruction file (AGENTS.md / CLAUDE.md / .cursor/rules / equivalent)",
            "Add AGENTS.md (or CLAUDE.md / .cursorrules / your tool's equivalent) "
            "with build/test commands, structure pointers, or conventions"))
    elif not has_agent and is_small:
        findings.append(_finding(
            "agent_instructions", "info", ".",
            "No agent instruction file (small repo — optional)",
            "Optional for a small/stable repo; a good README may be enough"))
    elif root_usefulness and root_usefulness["grade"] == "thin":
        # Present at root, but no useful signals at all.
        thin_file = next((a for a in agent_files if dir_of(a) == "."), ".")
        findings.append(_finding(
            "agent_instructions", "warn", thin_file,
            f"{basename(thin_file)} exists but looks like boilerplate "
            "(no commands, structure, or conventions detected)",
            "Add at least one of: build/test commands, a structure pointer, or "
            "conventions / rules — vendor-neutral, just needs to help an agent"))
    elif root_usefulness and root_usefulness["grade"] == "partial":
        thin_file = next((a for a in agent_files if dir_of(a) == "."), ".")
        evidence, action = _missing_signal_advice(root_usefulness["signals"])
        findings.append(_finding(
            "agent_instructions", "info", thin_file,
            f"{basename(thin_file)} {evidence}",
            action))

    # 3. module README coverage. Include a concrete hint of what's in the
    # module (file count + a couple example basenames) so the action lands —
    # "Add scripts/README.md" is generic; "Add scripts/README.md describing
    # the 5 .js files (build.js, pack.js, sign.js, …)" tells the writer what
    # to write about.
    covered = 0

    def _module_inventory(mod_path: str) -> tuple[int, list[str], str]:
        """Code-file count + up to 3 example basenames + dominant extension
        for one module (skipping nested submodules so the count reflects the
        directory itself, not the whole subtree)."""
        mod_code: list[str] = []
        prefix = "" if mod_path == "." else mod_path + "/"
        for f in files:
            if not f.startswith(prefix) or "/" in f[len(prefix):]:
                continue  # not in this dir, or in a nested subdir
            if ext_of(f) in CODE_EXTS:
                mod_code.append(f)
        examples = sorted({basename(f) for f in mod_code})[:3]
        ext_counts: dict[str, int] = {}
        for f in mod_code:
            ext_counts[ext_of(f)] = ext_counts.get(ext_of(f), 0) + 1
        top_ext = max(ext_counts, key=ext_counts.get) if ext_counts else ""
        return len(mod_code), examples, top_ext

    for m in nonwaived:
        if m.has_readme:
            covered += 1
            continue
        n, examples, top_ext = _module_inventory(m.path)
        if n:
            sample = ", ".join(examples) + (", …" if n > 3 else "")
            evidence = (f"Module '{m.path}' ({m.type}) has no README "
                        f"({n} {top_ext} file{'s' if n != 1 else ''}: {sample})")
            if n == 1:
                fix = (f"Add {m.path}/README.md — say what this file does and "
                       "when an agent should read it")
            else:
                fix = (f"Add {m.path}/README.md — say what these {n} files do, "
                       "how they fit together, and which is the entry point")
        else:
            # Module has subdirs but no code files at its top level.
            evidence = f"Module '{m.path}' ({m.type}) has no README"
            fix = f"Add {m.path}/README.md orienting an agent to this subtree"
        findings.append(_finding("module_readme", "warn", m.path, evidence, fix))

    # 4. broken links in markdown — line-aware (#5) so the fix cites README.md:42.
    broken = 0
    links_checked = 0
    for f in files:
        if ext_of(f) not in (".md", ".markdown"):
            continue
        # Skip test-data trees: their markdown often contains intentionally-broken
        # links as test fixtures, which would generate false positives.
        if any(part in TEST_DATA_DIRS for part in f.split("/")[:-1]):
            continue
        text = (root / f).read_text(encoding="utf-8", errors="ignore")
        base = root if dir_of(f) == "." else (root / dir_of(f))
        for lineno, line in enumerate(text.splitlines(), 1):
            for raw in LINK_RE.findall(line):
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
                    bl = _finding(
                        "broken_link", "warn", f,
                        f"Link to '{raw}' does not resolve",
                        f"Fix or remove the link in {f}",
                        line=lineno)
                    bl["link_target"] = tgt  # used by renderer to collapse per-target
                    findings.append(bl)
                # extensionless / unknown-ext unresolved → doc-site route or anchor; skip

    # 5. doc freshness / drift (needs git history) — B4 graded drift.
    # Per-doc fresh_score in [0, 1]; category aggregates with mean.
    fresh_score_sum = 0.0
    drift = 0  # legacy "any drift" count, kept for backward compatibility
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
            grade = _drift_grade(ddate, m.last_code_commit, gentle)
            fresh_score_sum += grade
            if grade < 1.0:
                drift += 1
                # Severity tracks how stale: warn for any drift today; bumped to
                # info on mildly stale so the fix list isn't drowned in yellow.
                sev = "info" if grade >= 0.7 else "warn"
                lag_label = (
                    "slightly stale" if grade >= 0.7
                    else ("stale" if grade > 0 else "very stale")
                )
                findings.append(_finding(
                    "doc_drift", sev, doc,
                    f"Code in '{m.path}' changed after this doc — {lag_label} "
                    f"(code {m.last_code_commit} vs doc {ddate})",
                    "Review and refresh the doc",
                    resolution={"drift_grade": grade}))

    # --- B1/B2/B3: doc tech-debt depth (findings-only; B4 already moved score) ---
    # These flag *demonstrable desync*, never mere age. All gated on git history.
    if is_git:
        # B1: agent files / root README that reference paths no longer on disk.
        candidates = list(agent_files)
        if has_root_readme and root_mod and root_mod.readme_path:
            candidates.append(root_mod.readme_path)
        for doc in candidates:
            try:
                text = (root / doc).read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            base = root if dir_of(doc) == "." else (root / dir_of(doc))
            seen_refs: set[str] = set()
            for lineno, line in enumerate(text.splitlines(), 1):
                for ref in _ref_paths(line):
                    if ref in seen_refs:
                        continue  # report each dead ref once, at its first line
                    # Resolve relative to the doc's directory; skip refs that
                    # escape the repo (url/absolute tokens already filtered).
                    target = base / ref.rstrip("/")
                    try:
                        inside = target.resolve().is_relative_to(root.resolve())
                    except Exception:
                        inside = False
                    if not inside or target.exists():
                        continue
                    seen_refs.add(ref)
                    findings.append(_finding(
                        "doc_ref_missing", "warn", doc,
                        f"References `{ref}` which no longer exists",
                        f"Fix or remove the `{ref}` reference in {basename(doc)}",
                        line=lineno))

        # B2: agent files at root that predate modules added later. Honest signal
        # that the agent file has fallen behind the codebase.
        for doc in [a for a in agent_files if dir_of(a) == "."]:
            ddate = gitinfo.last_commit_date(root, doc)
            if not ddate:
                continue
            newer_modules = []
            for m in nonwaived:
                if m.path == ".":
                    continue
                first = gitinfo.first_commit_date_for_path(root, m.path)
                if first and first > ddate:
                    newer_modules.append(m.path)
            if len(newer_modules) >= 2:
                examples = ", ".join(newer_modules[:3])
                more = f" (+{len(newer_modules) - 3} more)" if len(newer_modules) > 3 else ""
                findings.append(_finding(
                    "doc_predates_modules", "warn", doc,
                    f"{basename(doc)} last updated {ddate}; "
                    f"{len(newer_modules)} module(s) added since: {examples}{more}",
                    f"Review {basename(doc)} — newer modules likely aren't documented there"))

        # B3: written-once / never-revised. The honest denominator is commits
        # that landed AFTER the doc existed — not total repo churn. A doc that
        # was added 4 days ago in a 700-commit repo legitimately hasn't been
        # revised because there's been no opportunity, not because it's stale.
        # Threshold: at least 100 commits since the doc was introduced.
        B3_POST_DOC_CHURN_THRESHOLD = 100
        once_candidates: list[str] = list(agent_files)
        if has_root_readme and root_mod and root_mod.readme_path:
            once_candidates.append(root_mod.readme_path)
        for doc in once_candidates:
            count = gitinfo.commit_count_for_path(root, doc)
            if count != 1:
                continue
            first = gitinfo.first_commit_date_for_path(root, doc)
            if not first:
                continue
            post_doc_churn = gitinfo.commits_since(root, first)
            if post_doc_churn < B3_POST_DOC_CHURN_THRESHOLD:
                continue  # not enough churn after the doc landed to expect revision
            when = first[:7]  # YYYY-MM
            findings.append(_finding(
                "doc_written_once", "info", doc,
                f"{basename(doc)} written {when}, untouched while "
                f"{post_doc_churn} commits landed after it",
                f"Skim {basename(doc)} for staleness — a doc untouched while "
                "hundreds of commits landed after it is rarely still accurate"))

        # B5: standalone living docs (CHANGELOG, ROADMAP, docs/*.md, …) that have
        # fallen behind active development. These are the "other markdown that
        # needs regular updates" the module-doc drift (section 5) and B1-B3 don't
        # reach: not a module README, not an agent file. Churn-relative drift
        # ONLY — flagged when many commits landed AFTER the doc's last edit, never
        # mere calendar age (same honesty bar as B3). Surfaced as a warn so it
        # reaches the fix list, but informational like B2/B3 (0 pts — doesn't move
        # the freshness score) and capped so a doc-heavy repo can't drown the list.
        B5_POST_EDIT_CHURN_THRESHOLD = 100
        B5_MAX = 5
        covered_docs = {m.readme_path for m in nonwaived if m.readme_path}
        covered_docs |= set(agent_files)
        loose: list[tuple[int, str, str]] = []  # (churn_since_edit, doc, last_edit)
        for doc in files:
            if ext_of(doc) not in {".md", ".markdown"} or doc in covered_docs:
                continue
            if any(seg in WAIVED_DIRS for seg in dir_of(doc).split("/")):
                continue  # examples/fixtures/benchmarks — sample docs, not living docs
            last_edit = gitinfo.last_commit_date(root, doc)
            if not last_edit:
                continue
            churn = gitinfo.commits_since(root, last_edit)
            if churn >= B5_POST_EDIT_CHURN_THRESHOLD:
                loose.append((churn, doc, last_edit))
        for churn, doc, last_edit in sorted(loose, reverse=True)[:B5_MAX]:
            findings.append(_finding(
                "doc_stale", "warn", doc,
                f"{basename(doc)} last updated {last_edit}; {churn} commits have "
                "landed since — likely behind the current code",
                f"Skim {basename(doc)} and refresh anything the code has outgrown"))

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
        # A2: best usefulness grade per location ("actionable" / "partial" /
        # "thin"); None when no agent file there.
        "agent_usefulness_root": root_usefulness["grade"] if root_usefulness else None,
        "agent_usefulness_nested": nested_usefulness["grade"] if nested_usefulness else None,
        "modules_total": len(nonwaived),
        "modules_covered": covered,
        "broken_links": broken,
        "links_checked": links_checked,
        "drift_count": drift,
        # B4: graded freshness — sum of per-doc scores in [0,1]; scoring uses
        # this divided by docs_checked instead of the binary drift count.
        "fresh_score_sum": fresh_score_sum,
        "docs_checked": docs_checked,
        "is_git": is_git,
        "mcp_present": mcp_present,
    }
    return findings, metrics
