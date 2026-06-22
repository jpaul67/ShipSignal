"""Module detection and exclusion rules — the foundation the scan depends on.

Calibration (see the spec) showed a generic "top-level dirs + packages/" heuristic
silently under-detects: it found zero of codex's 91 Cargo crates. So detection is
ecosystem-aware first (npm / pnpm / Cargo workspaces, anywhere in the tree) and
falls back to a directory heuristic only when no workspace manifest is found.
"""
from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass
from pathlib import Path

from . import gitinfo

# Excluded anywhere in a path (vendored, build output, tooling).
EXCLUDE_DIRS = {
    ".git", "node_modules", "dist", "build", "out", ".venv", "venv",
    "vendor", "third_party", "third-party", "patches", "target",
    ".next", ".nuxt", ".cache", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "coverage", ".idea", ".vscode",
    "site-packages", ".tox", ".gradle", ".egg-info",
}
# Code-bearing but waived from the README requirement.
WAIVED_DIRS = {
    "tests", "test", "__tests__", "spec", "specs",
    "examples", "example", "fixtures", "e2e", "benchmarks",
}
# Dirs whose markdown is test input, not reader-facing docs. Links inside
# these are often *intentionally* broken (they're the subject of the test).
# Narrower than WAIVED_DIRS: examples/ is excluded because example-doc links
# should resolve — only genuine test-data trees are skipped.
TEST_DATA_DIRS = {"tests", "test", "__tests__", "spec", "specs", "fixtures", "e2e"}
CODE_EXTS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".rs", ".go",
    ".java", ".kt", ".rb", ".c", ".h", ".cpp", ".hpp", ".cc", ".cs",
    ".php", ".swift", ".scala", ".sh", ".vue", ".svelte", ".sql", ".lua",
}
DOC_EXTS = {".md", ".markdown", ".rst", ".txt"}
SOURCE_ROOTS = {"src", "lib", "app", "packages", "crates", "apps", "modules", "pkg"}
AGENT_BASENAMES = {
    "claude.md", "agents.md", "gemini.md", "copilot-instructions.md",
    ".cursorrules", ".windsurfrules", ".clinerules",
    # .mcp.json is intentionally NOT here — it's a tool config (consumed by
    # MCP-aware clients), not prose context, and it's already credited by
    # setupcheck.mcp_resolves. Including it would double-count and fail the
    # prose-based A2 usefulness heuristic confusingly.
}


@dataclass
class Module:
    path: str  # posix, "." for the repo root
    type: str
    has_readme: bool = False
    readme_path: str | None = None
    agent_file: str | None = None
    last_code_commit: str | None = None
    waived: bool = False


# --- small path helpers -----------------------------------------------------

def dir_of(rel: str) -> str:
    return rel.rsplit("/", 1)[0] if "/" in rel else "."


def basename(rel: str) -> str:
    return rel.rsplit("/", 1)[-1]


def ext_of(rel: str) -> str:
    name = basename(rel)
    return "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""


def is_excluded(rel: str) -> bool:
    return any(part in EXCLUDE_DIRS for part in rel.split("/")[:-1])


def is_agent_file(rel: str) -> bool:
    low = rel.lower()
    if basename(low) in AGENT_BASENAMES:
        return True
    return "/.cursor/rules/" in "/" + low or low.startswith(".cursor/rules/")


# --- file listing -----------------------------------------------------------

def list_files(root: Path) -> tuple[list[str], bool]:
    """(relative posix paths, is_git). Respects .gitignore via ``git ls-files``."""
    if gitinfo.is_git_repo(root):
        return [f for f in gitinfo.tracked_files(root) if not is_excluded(f)], True
    files: list[str] = []
    for p in root.rglob("*"):
        if p.is_file():
            rel = p.relative_to(root).as_posix()
            if not is_excluded(rel):
                files.append(rel)
    return files, False


# --- workspace (ecosystem-aware) detection ----------------------------------

def _read_text(root: Path, rel: str) -> str | None:
    try:
        return (root / rel).read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None


def _expand(base: Path, patterns: list[str], root: Path) -> list[str]:
    out: list[str] = []
    for pat in patterns:
        if not isinstance(pat, str):
            continue
        pat = pat.strip().strip("'\"")
        if not pat or pat.startswith("!"):
            continue
        try:
            matches = list(base.glob(pat))
        except Exception:
            matches = []
        for m in matches:
            if m.is_dir():
                try:
                    out.append(m.relative_to(root).as_posix())
                except Exception:
                    pass
    return out


def _parse_pnpm_packages(text: str) -> list[str]:
    pats, in_pkgs = [], False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("packages:"):
            in_pkgs = True
            continue
        if in_pkgs:
            if s.startswith("- "):
                pats.append(s[2:].strip().strip("'\""))
            elif s and not s.startswith("#") and not line[:1].isspace():
                break
    return pats


def _detect_workspaces(root: Path, files: list[str]) -> list[Module]:
    found: dict[str, Module] = {}
    for rel in files:
        name = basename(rel).lower()
        base = (root / rel).parent
        if name == "package.json":
            obj = _read_text(root, rel)
            try:
                ws = json.loads(obj).get("workspaces") if obj else None
            except Exception:
                ws = None
            pats = ws.get("packages") if isinstance(ws, dict) else ws
            if isinstance(pats, list):
                for m in _expand(base, pats, root):
                    found[m] = Module(path=m, type="npm-workspace")
        elif name == "pnpm-workspace.yaml":
            obj = _read_text(root, rel)
            if obj:
                for m in _expand(base, _parse_pnpm_packages(obj), root):
                    found[m] = Module(path=m, type="pnpm-workspace")
        elif name == "cargo.toml":
            obj = _read_text(root, rel)
            try:
                members = tomllib.loads(obj).get("workspace", {}).get("members") if obj else None
            except Exception:
                members = None
            if isinstance(members, list):
                for m in _expand(base, members, root):
                    found[m] = Module(path=m, type="cargo-crate")
    return list(found.values())


def _detect_fallback(files: list[str]) -> list[Module]:
    dirs: set[str] = set()
    for rel in files:
        d = dir_of(rel)
        if d == ".":
            continue
        parts = d.split("/")
        dirs.add(parts[0])
        if parts[0] in SOURCE_ROOTS and len(parts) >= 2:
            dirs.add(parts[0] + "/" + parts[1])
    mods = []
    for d in sorted(dirs):
        leaf = d.split("/")[-1]
        if leaf in EXCLUDE_DIRS:
            continue
        mods.append(Module(path=d, type="dir", waived=leaf in WAIVED_DIRS))
    return mods


def _code_dirs(files: list[str]) -> set[str]:
    """All dirs (and ancestors) that contain at least one code file."""
    out = {"."}
    for rel in files:
        if ext_of(rel) in CODE_EXTS:
            parts = rel.split("/")[:-1]
            for i in range(len(parts)):
                out.add("/".join(parts[: i + 1]))
    return out


def _find_readme(dir_path: str, by_dir: dict[str, list[str]]) -> str | None:
    for f in by_dir.get(dir_path, []):
        name = basename(f).lower()
        stem, _, ext = name.rpartition(".")
        if stem == "readme" and "." + ext in DOC_EXTS:
            return f
    return None


def detect_modules(root: Path, files: list[str], is_git: bool):
    by_dir: dict[str, list[str]] = {}
    for f in files:
        by_dir.setdefault(dir_of(f), []).append(f)

    code_dirs = _code_dirs(files)
    workspace = _detect_workspaces(root, files)
    candidates = workspace or _detect_fallback(files)

    modules = [Module(path=".", type="root")]
    seen = {"."}
    for m in candidates:
        if m.path in seen or m.path not in code_dirs:
            continue
        seen.add(m.path)
        modules.append(m)

    agent_files = [f for f in files if is_agent_file(f)]
    for m in modules:
        # Waive example/test/fixture modules anywhere in their path (a workspace
        # member like examples/lit shouldn't be required to carry a README).
        if m.path != "." and any(seg in WAIVED_DIRS for seg in m.path.split("/")):
            m.waived = True
        m.readme_path = _find_readme(m.path, by_dir)
        m.has_readme = m.readme_path is not None
        for af in agent_files:
            if dir_of(af) == m.path:
                m.agent_file = af
                break
        if is_git:
            m.last_code_commit = gitinfo.last_commit_date(root, m.path)

    return modules, agent_files
