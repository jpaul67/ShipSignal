# Bellwether — AI readiness & impact scanner

> One read-only local CLI with two lenses. **Readiness** — is your codebase set up for AI agents to succeed? **Impact** — is AI actually changing how the team ships? Pure Python stdlib, no runtime deps, runs on any repo in seconds.

## Quick start

Requires Python 3.11+.

```bash
# Readiness lens — repo state, "set up for agents?"
python -m bellwether.cli scan .                  # scan this repo
python -m bellwether.cli scan ../crown           # scan a local path
python -m bellwether.cli scan vitest-dev/vitest  # scan a public GitHub repo
python -m bellwether.cli scan . --json readiness.json --fail-under 80

# Impact lens — git-history analytics, "AI changing how we ship?"
python -m bellwether.cli impact ../crown
python -m bellwether.cli impact ../crown --json impact.json --md impact.md
python -m bellwether.cli impact . --with-readiness     # feed agent_readiness pillar
```

Once [uv](https://docs.astral.sh/uv/) is installed it also runs as `uvx bellwether scan <target>` (entry point declared in [pyproject.toml](pyproject.toml)).

## Readiness lens — what it checks

| Detector | What |
|---|---|
| Entry point | Root README present and substantial |
| Agent instructions | `CLAUDE.md` / `AGENTS.md` / `.cursor/rules` / copilot-instructions (size-scaled) |
| Module README coverage | Each detected module is documented |
| Setup & conventions | test command, CI, deps/lockfile, lint/format/type config, `.editorconfig`, LICENSE, CONTRIBUTING, MCP path-resolution |
| Broken links | Markdown links resolve (with false-positive guards) |
| Doc freshness | Module docs haven't drifted behind their code |

Module detection is **ecosystem-aware** (npm / pnpm / Cargo workspaces, then a directory fallback), respects `.gitignore`, and excludes vendored/build dirs.

Six scored categories sum to 100 (entry 20, agent 15, coverage 20, setup 20, integrity 13, freshness 12). Categories can be **n/a** or **indeterminate**; the score renormalizes over what was actually scored, so a small well-documented library isn't punished.

## Impact lens — what it measures

| Family | Signal |
|---|---|
| AI adoption | `Co-Authored-By:` trailer share — the one direct, AI-specific signal (lower bound) |
| Flow | commits/week, active-day ratio |
| Change shape | median/p90 lines per commit, large-change rate |
| Quality | fix/revert subject rate, test-to-code co-change |
| People | contributors, top-author share, bus-factor (solo repos get a "descriptive only" guard) |

The Enablement Score is **withheld** when history is too thin (confidence gate) or AI was present from inception (no pre-AI baseline). That restraint is the point — *"the most valuable output is what the lens refuses to do"* — see [docs/impact-lens.md](#) (spec lives in Drive).

## Output

A canonical JSON (`readiness.json` / `impact.json` — findings or metrics, **never file or diff contents**), CLI text, optional Markdown / HTML reports, and (Readiness only) a `readiness: N/100` badge SVG. Exit non-zero with `--fail-under N` for CI gates.

## Project layout

- [bellwether/](bellwether/README.md) — the package (module map inside)
- `tests/` — stdlib `unittest` suite
- Working with an agent? See [CLAUDE.md](CLAUDE.md) / [AGENTS.md](AGENTS.md).

## License

MIT (see [pyproject.toml](pyproject.toml)).
