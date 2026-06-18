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

## Impact lens — three always-on numbers

Every impact scan headlines with three numbers that are *always* computed (above a tiny sample floor):

| Number | What it is |
|---|---|
| **AI Adoption** | `Co-Authored-By:` trailer share + level (None / Emerging / Established / Pervasive). The one direct, AI-specific signal — reported as a lower bound (squash-merges drop trailers). |
| **Delivery Health** | A 0–100 snapshot scored against general engineering norms — *not* AI-attributed. Combines change-size discipline, test discipline, and (for teams) knowledge distribution. Flags surface real risks (`low test discipline`, `concentration risk`). |
| **Readiness** | The static-state score from `scan` (runs by default; `--no-readiness` to skip). |

A fourth, *conditional* **Before/after AI Enablement** delta appears only when the data supports it — there's a clean pre-AI baseline window AND ≥ 20 commits in both windows AND ≥ 50 commits total AND ≥ 6 weeks of history. In the wild that combination is rare (most repos are AI-from-inception, no-AI, or ambient-AI), so it's the *bonus*, not the headline — competitors fake this score; we don't.

Calibrated across crown (Pervasive · 55/F · 83/B — flags real test gap), chalk (None · 77/C · 80/B — flags concentration), vitest (Emerging · 97/A · 97/A — clean). Component definitions in [the spec](#) (Drive).

## Output

A canonical JSON (`readiness.json` / `impact.json` — findings or metrics, **never file or diff contents**), CLI text, optional Markdown / HTML reports, and (Readiness only) a `readiness: N/100` badge SVG. Exit non-zero with `--fail-under N` for CI gates.

## Project layout

- [bellwether/](bellwether/README.md) — the package (module map inside)
- `tests/` — stdlib `unittest` suite
- Working with an agent? See [CLAUDE.md](CLAUDE.md) / [AGENTS.md](AGENTS.md).

## License

MIT (see [pyproject.toml](pyproject.toml)).
