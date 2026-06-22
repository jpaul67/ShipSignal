"""Starter snippets (Feature #3) — copy-pasteable scaffolds attached to
readiness fixes.

Strict framing: these are **starters**, never "the correct content for your
repo". We use facts the scanner already detected (the test command, the
module's file list, the ecosystem) to pre-fill — and explicitly fall back to
``None`` when we'd have to fabricate. Better no snippet than a confident lie.

The renderer is responsible for showing/hiding snippets (top-3 in CLI per
the plan; always in Markdown + HTML).
"""
from __future__ import annotations


def _basename(p: str) -> str:
    return p.rsplit("/", 1)[-1] if "/" in p else p


def _agent_file_starter(metrics: dict, modules: list[dict] | None = None) -> str:
    """A CLAUDE.md / AGENTS.md skeleton pre-filled with detected commands and
    module names. We label *every* placeholder so a reader never mistakes the
    starter for content. No facts? We still emit a useful skeleton with
    explicit `<fill-in>` markers — that's still better than a blank page."""
    test_cmd = metrics.get("detected_test_cmd")
    build_cmd = metrics.get("detected_build_cmd")
    ecosystem = metrics.get("ecosystem")

    cmd_lines: list[str] = []
    if test_cmd:
        cmd_lines.append(f"- Test: `{test_cmd}`")
    if build_cmd:
        cmd_lines.append(f"- Build: `{build_cmd}`")
    if not cmd_lines:
        cmd_lines = [
            "- Test: `<fill in test command>`",
            "- Build: `<fill in build command, if any>`",
        ]
    cmds = "\n".join(cmd_lines)

    # Pull a handful of non-waived module names, if any were detected.
    mod_paths = [m["path"] for m in (modules or []) if m.get("path") not in (".", None)
                 and not m.get("waived", False)][:5]
    if mod_paths:
        mod_lines = "\n".join(f"- `{p}` — <one-line role>" for p in mod_paths)
    else:
        mod_lines = "- `<module>` — <one-line role>"

    eco_line = f"Stack: {ecosystem}." if ecosystem else "Stack: <fill in>."

    return (
        "# Project\n"
        "\n"
        "<one-paragraph: what this is>\n"
        "\n"
        "## Commands\n"
        "\n"
        f"{cmds}\n"
        "\n"
        "## Structure\n"
        "\n"
        f"{eco_line} Where things live:\n"
        "\n"
        f"{mod_lines}\n"
        "\n"
        "## Conventions\n"
        "\n"
        "- <rule — e.g. always run tests before committing>\n"
        "- <rule — e.g. prefer composition over inheritance>\n"
    )


def _module_readme_starter(finding: dict) -> str:
    """A module README skeleton — uses the file count and example basenames
    that detectors.run_detectors already put into the evidence string."""
    path = finding.get("path", "<module>")
    evidence = finding.get("evidence", "") or ""
    name = _basename(path)
    # Try to recover the example list from the evidence; fall back to a
    # generic placeholder if we can't (we never invent file names).
    if ": " in evidence and evidence.endswith(")"):
        try:
            example_part = evidence.rsplit(": ", 1)[1].rstrip(")")
            example_lines = "\n".join(f"- `{e.strip()}` — <one-line role>"
                                       for e in example_part.split(",") if e.strip())
        except Exception:
            example_lines = "- `<file>` — <one-line role>"
    else:
        example_lines = "- `<file>` — <one-line role>"
    return (
        f"# {name}\n"
        "\n"
        "<one-paragraph: what this directory does and when an agent should read it>\n"
        "\n"
        "## Files\n"
        "\n"
        f"{example_lines}\n"
        "\n"
        "## Entry point\n"
        "\n"
        "`<file>` — <how an agent should start reading>\n"
    )


def _test_command_starter(metrics: dict) -> str | None:
    """Suggest a test-command convention for the detected ecosystem. Only
    emitted when we have a real ecosystem signal — fabrication would mislead."""
    eco = metrics.get("ecosystem")
    if eco == "npm":
        return ('// package.json\n'
                '{\n'
                '  "scripts": {\n'
                '    "test": "<your test runner, e.g. vitest run / jest>"\n'
                '  }\n'
                '}\n')
    if eco == "python":
        return ('# pyproject.toml\n'
                '[tool.pytest.ini_options]\n'
                'testpaths = ["tests"]\n')
    if eco == "make":
        return ('# Makefile\n'
                'test:\n'
                '\t<your test command>\n')
    return None


def snippet_for(finding: dict, metrics: dict,
                modules: list[dict] | None = None) -> str | None:
    """Return a markdown-formatted starter block for this finding, or None
    when we have no useful template. Always a starter, never positioned as
    the right answer."""
    det = finding.get("detector")
    if det == "agent_instructions":
        return _agent_file_starter(metrics, modules)
    if det == "module_readme":
        return _module_readme_starter(finding)
    if det == "setup":
        # Only the test_command check has a useful starter; others (LICENSE,
        # .editorconfig) are too trivial to scaffold and would be insulting.
        if "test_command" in (finding.get("fix") or "").lower() \
                or "test script/target" in (finding.get("fix") or "").lower():
            return _test_command_starter(metrics)
    return None
