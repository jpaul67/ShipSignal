# Bellwether — agent-readiness scanner

> Is your codebase set up for AI agents to succeed? Bellwether is a fast, read-only static scan that grades a repo on how navigable and trustworthy it is to a coding agent landing in it cold — and tells you the specific fixes that move the score.

This is **v0**: a standalone, LLM-free scanner (stdlib only). It's the lead-magnet and the seed of the larger Bellwether AI-enablement tool.

## Quick start

Requires Python 3.11+.

```bash
# from the repo root (no install needed for local dev)
python -m bellwether.cli scan .                 # scan this repo
python -m bellwether.cli scan ../crown          # scan a local path
python -m bellwether.cli scan vitest-dev/vitest # scan a public GitHub repo (owner/repo)
python -m bellwether.cli scan . --json readiness.json --fail-under 80
```

Once [uv](https://docs.astral.sh/uv/) is installed it also runs as `uvx bellwether scan <target>` (entry point declared in [pyproject.toml](pyproject.toml)).

## What it checks

| Detector | What |
|---|---|
| Entry point | Root README present and substantial |
| Agent instructions | `CLAUDE.md` / `AGENTS.md` / `.cursor/rules` / copilot-instructions (size-scaled) |
| Module README coverage | Each detected module is documented |
| Broken links | Markdown links resolve (with false-positive guards) |
| Doc freshness | Module docs haven't drifted behind their code |
| MCP | Config presence (conditional) |

Module detection is **ecosystem-aware** (npm / pnpm / Cargo workspaces, then a directory fallback), respects `.gitignore`, and excludes vendored/build dirs.

## Output

A 0–100 score + letter grade, a per-category breakdown, and a ranked list of fixes. `--json` emits the canonical `readiness.json` (findings only — never file contents). Exit non-zero with `--fail-under N` for CI gates.

## Scoring

Five categories sum to 100 (entry 25, agent 20, coverage 25, integrity 15, freshness 15). Categories can be **n/a** (e.g. no MCP, or agent files on a small repo) or **indeterminate** (e.g. freshness without git history); the score renormalizes over what was actually scored, so a small well-documented library isn't punished.

## Project layout

- [bellwether/](bellwether/README.md) — the package (module map inside)
- `tests/` — stdlib `unittest` suite
- Working with an agent? See [CLAUDE.md](CLAUDE.md) / [AGENTS.md](AGENTS.md).

## License

MIT (see [pyproject.toml](pyproject.toml)).
