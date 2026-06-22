"""Setup & convention detection — can an agent build, test, and conform here?

The Phase-A "all the right setup files" checklist: a discoverable build/test
command, CI, dependency manifest/lockfile, lint/format/type config, the common
convention files, and (when present) a resolvable MCP config. Scored as a
weighted proportion of the *applicable* checks, so language-specific items
(e.g. type config) only count where they make sense.
"""
from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

from .modules import CODE_EXTS, basename, ext_of

LOCKFILES = {
    "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lockb",
    "npm-shrinkwrap.json", "poetry.lock", "uv.lock", "pipfile.lock",
    "cargo.lock", "go.sum", "gemfile.lock", "composer.lock",
}
MANIFESTS = {
    "package.json", "pyproject.toml", "setup.py", "setup.cfg", "cargo.toml",
    "go.mod", "requirements.txt", "gemfile", "build.gradle", "pom.xml",
    "composer.json", "pubspec.yaml",
}
CI_FILES = {
    ".gitlab-ci.yml", "azure-pipelines.yml", "jenkinsfile", ".travis.yml",
    ".drone.yml", "bitbucket-pipelines.yml",
}

# A3: architecture-doc check. Only *expected* on multi-module repos — below this
# module count, an architecture doc is informative but not required (avoids
# nagging a 200-line utility for an ARCHITECTURE.md).
ARCH_MODULE_THRESHOLD = 4
# Headings inside the root README that count as an architecture overview when
# followed by enough content under them.
_ARCH_HEADING_RE = re.compile(
    r"^(#+)\s*(architecture|structure|project layout|layout|how it works|"
    r"design|overview|module(?:s)? map|file map|project structure)\b.*$",
    re.IGNORECASE | re.MULTILINE,
)
_ARCH_README_MIN_CHARS = 200  # content under the heading needed to count
_ARCH_DOCS_MIN_CHARS = 500    # content needed in a docs/*.md to count


def _has_arch_doc(root: Path, rootfiles: set[str], files: list[str]) -> bool:
    """Any of: an ARCHITECTURE.md at root, a docs/ dir with substantive content,
    or a root README with an Architecture/Structure section ≥ _ARCH_README_MIN_CHARS.
    """
    # 1) ARCHITECTURE.md at root (case-insensitive).
    if any(rf in rootfiles for rf in ("architecture.md", "architecture.markdown")):
        return True
    # 2) docs/ directory with a non-trivial markdown file.
    for f in files:
        low = f.lower()
        if not (low.startswith("docs/") or "/docs/" in low):
            continue
        if not low.endswith((".md", ".markdown", ".rst", ".txt")):
            continue
        try:
            if len((root / f).read_text(encoding="utf-8", errors="ignore")) >= _ARCH_DOCS_MIN_CHARS:
                return True
        except Exception:
            continue
    # 3) Root README has an Architecture/Structure section with real content.
    readme = next((rf for rf in rootfiles
                   if rf in ("readme.md", "readme.markdown", "readme.rst", "readme.txt")), None)
    if not readme:
        return False
    text = _rt(root, readme)
    m = _ARCH_HEADING_RE.search(text)
    if not m:
        return False
    start = m.end()
    # Content under the heading runs until the next heading of the same-or-shallower depth.
    depth = len(m.group(1))
    after = text[start:]
    next_h = re.search(rf"^#{{1,{depth}}}\s", after, re.MULTILINE)
    section = after[: next_h.start()] if next_h else after
    return len(section.strip()) >= _ARCH_README_MIN_CHARS


def _rt(root: Path, rel: str) -> str:
    try:
        return (root / rel).read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _pyproject_tool(root: Path, rootfiles: set[str], tool: str) -> bool:
    if "pyproject.toml" not in rootfiles:
        return False
    try:
        return tool in tomllib.loads(_rt(root, "pyproject.toml")).get("tool", {})
    except Exception:
        return False


def _has_deps(root: Path, rootfiles: set[str]) -> bool:
    """Does the manifest actually declare dependencies? (No deps → no lockfile needed.)"""
    if "package.json" in rootfiles:
        try:
            o = json.loads(_rt(root, "package.json"))
            if o.get("dependencies") or o.get("devDependencies"):
                return True
        except Exception:
            pass
    if "pyproject.toml" in rootfiles:
        try:
            t = tomllib.loads(_rt(root, "pyproject.toml"))
            if t.get("project", {}).get("dependencies"):
                return True
            if t.get("tool", {}).get("poetry", {}).get("dependencies"):
                return True
        except Exception:
            pass
    return bool({"requirements.txt", "cargo.toml", "go.mod", "gemfile", "composer.json"} & rootfiles)


def _mcp_resolves(root: Path, files: list[str]) -> tuple[bool, str]:
    mcp = next((f for f in files
                if basename(f).lower() in {".mcp.json", "mcp.json"}
                or f.lower().endswith(".cursor/mcp.json")), None)
    if not mcp:
        return True, ""
    try:
        obj = json.loads(_rt(root, mcp))
    except Exception:
        return False, "unparseable"
    servers = obj.get("mcpServers") or obj.get("servers") or {}
    if not isinstance(servers, dict):
        return True, ""
    for name, cfg in servers.items():
        if not isinstance(cfg, dict):
            continue
        candidates = []
        if isinstance(cfg.get("cwd"), str):
            candidates.append(cfg["cwd"])
        if isinstance(cfg.get("args"), list):
            candidates += [a for a in cfg["args"] if isinstance(a, str)]
        for c in candidates:
            cl = c.strip()
            if cl.startswith(("-", "http://", "https://", "@")):
                continue
            if ("/" in cl or "\\" in cl) and ext_of(cl):  # looks like an in-repo file path
                p = root / cl
                try:
                    inside = p.resolve().is_relative_to(root.resolve())
                except Exception:
                    inside = False
                if inside and not p.exists():
                    return False, f"{name}: missing {cl}"
    return True, ""


def detect_setup(root: Path, files: list[str], mcp_present: bool, modules_total: int = 0):
    low = [f.lower() for f in files]
    lowset = set(low)
    rootfiles = {f for f in low if "/" not in f}
    bn = {basename(f) for f in low}
    exts = {ext_of(f) for f in files}
    has_code = bool(exts & CODE_EXTS)

    # A handful of .ts files in an otherwise-JS repo (e.g. Deno Edge Functions
    # in a Phaser game) shouldn't trigger a TypeScript-config warning. Treat
    # the language as "really used" only when there's a real signal: a config
    # file, a deps declaration, or enough files to look like the main stack.
    # Crown calibration: 2 .ts files (out of 73 .js) — currently warns; should be n/a.
    LANG_PRESENCE_FLOOR = 4

    def _file_count(extensions: set[str]) -> int:
        return sum(1 for e in (ext_of(f) for f in files) if e in extensions)

    def _has_npm_dep(pkg: str) -> bool:
        if "package.json" not in rootfiles:
            return False
        try:
            obj = json.loads(_rt(root, "package.json"))
        except Exception:
            return False
        for key in ("dependencies", "devDependencies", "peerDependencies",
                    "optionalDependencies"):
            if pkg in (obj.get(key) or {}):
                return True
        return False

    has_ts_files = bool({".ts", ".tsx"} & exts)
    has_ts = has_ts_files and (
        "tsconfig.json" in bn
        or _has_npm_dep("typescript")
        or _file_count({".ts", ".tsx"}) >= LANG_PRESENCE_FLOOR
    )
    has_py_files = ".py" in exts
    has_py = has_py_files and (
        "pyproject.toml" in rootfiles
        or "setup.py" in rootfiles
        or "setup.cfg" in rootfiles
        or "requirements.txt" in rootfiles
        or _file_count({".py"}) >= LANG_PRESENCE_FLOOR
    )

    # Discoverable test command
    test_cmd = False
    if "package.json" in rootfiles:
        try:
            if json.loads(_rt(root, "package.json")).get("scripts", {}).get("test"):
                test_cmd = True
        except Exception:
            pass
    if not test_cmd:
        if {"pytest.ini", "tox.ini"} & rootfiles or _pyproject_tool(root, rootfiles, "pytest"):
            test_cmd = True
        elif "cargo.toml" in bn or "go.mod" in rootfiles:
            test_cmd = True
        else:
            for mk in ("makefile", "justfile", "taskfile.yml"):
                if mk in rootfiles and re.search(r"(?mi)^[ \t]*test\b[ \t]*:", _rt(root, mk)):
                    test_cmd = True
                    break

    has_ci = (any(f.startswith(".github/workflows/") for f in low)
              or any(f.startswith(".circleci/") for f in low)
              or bool(CI_FILES & bn))
    has_manifest = bool(MANIFESTS & bn)
    has_lock = bool(LOCKFILES & bn)
    has_lint = (any(n.startswith(".eslintrc") or n.startswith("eslint.config.") for n in bn)
                or bool({"biome.json", ".flake8", ".pylintrc", ".rubocop.yml",
                         ".golangci.yml", ".golangci.yaml", "ruff.toml", ".ruff.toml"} & bn)
                or _pyproject_tool(root, rootfiles, "ruff")
                or _pyproject_tool(root, rootfiles, "flake8"))
    has_format = (any(n.startswith(".prettierrc") or n.startswith("prettier.config.") for n in bn)
                  or bool({"rustfmt.toml", ".rustfmt.toml"} & bn)
                  or _pyproject_tool(root, rootfiles, "black")
                  or _pyproject_tool(root, rootfiles, "ruff"))
    has_types = (has_ts and "tsconfig.json" in bn) or (
        has_py and ({"mypy.ini", ".mypy.ini", "pyrightconfig.json", "py.typed"} & bn
                    or _pyproject_tool(root, rootfiles, "mypy")
                    or _pyproject_tool(root, rootfiles, "pyright")))
    has_editorconfig = ".editorconfig" in rootfiles
    has_contributing = any(n.startswith("contributing") for n in bn)
    has_license = any(n.startswith(("license", "licence")) or n in {"copying", "unlicense"} for n in bn)
    deps = _has_deps(root, rootfiles)

    # (id, ok, weight, applicable, label, fix)
    checks = [
        ("test_command", test_cmd, 3, True, "discoverable test command",
         'Add a test script/target (package.json "test", a Makefile test:, or pytest config)'),
        ("ci_config", has_ci, 3, True, "CI configuration",
         "Add CI (e.g. .github/workflows) so agents can see how it's built and tested"),
        ("dependency_manifest", has_manifest, 2, True, "dependency manifest",
         "Add a manifest (package.json / pyproject.toml / go.mod / Cargo.toml)"),
        ("lockfile", has_lock, 1, deps, "dependency lockfile",
         "Commit a lockfile for reproducible installs"),
        ("lint_config", has_lint, 2, has_code, "lint config",
         "Add a linter config (eslint / ruff / etc.) so agents produce conforming code"),
        ("format_config", has_format, 1, has_code, "formatter config",
         "Add a formatter config (prettier / black / ruff / rustfmt)"),
        ("type_config", has_types, 2, (has_ts or has_py), "type config",
         "Add type config (tsconfig.json / mypy / pyright / py.typed)"),
        ("editorconfig", has_editorconfig, 1, True, ".editorconfig",
         "Add an .editorconfig for consistent whitespace/style"),
        ("contributing", has_contributing, 1, True, "CONTRIBUTING",
         "Add CONTRIBUTING with how to build, test, and submit changes"),
        ("license", has_license, 1, True, "LICENSE",
         "Add a LICENSE file"),
    ]
    # A3: architecture/overview doc — only *expected* on multi-module repos so we
    # don't nag small utilities. Below the threshold it's informational (omitted
    # from the checklist entirely; presence elsewhere is fine).
    arch_applicable = modules_total >= ARCH_MODULE_THRESHOLD
    has_arch = _has_arch_doc(root, rootfiles, files) if arch_applicable else False
    checks.append(("architecture_doc", has_arch, 2, arch_applicable, "architecture overview",
                   f"No architecture overview for a {modules_total}-module repo — add "
                   "ARCHITECTURE.md, a docs/ overview, or a Structure section in the README"))
    if mcp_present:
        ok, detail = _mcp_resolves(root, files)
        checks.append(("mcp_resolves", ok, 2, True, "MCP config resolves",
                       "Fix MCP config — a referenced server path doesn't resolve"
                       + (f" ({detail})" if detail else "")))

    applicable = [c for c in checks if c[3]]
    total_w = sum(c[2] for c in applicable) or 1
    got_w = sum(c[2] for c in applicable if c[1])

    findings = []
    for cid, ok, weight, _app, label, fix in applicable:
        if ok:
            continue
        findings.append({
            "detector": "setup",
            "severity": "warn" if weight >= 2 else "info",
            "path": ".",
            "evidence": f"Missing {label}",
            "fix": fix,
        })

    metrics = {
        "setup_score_frac": got_w / total_w,
        "setup_present": [c[0] for c in applicable if c[1]],
        "setup_missing": [c[0] for c in applicable if not c[1]],
    }
    return findings, metrics
