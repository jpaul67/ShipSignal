# ShipSignal — the AI impact & delivery-health scanner

[![PyPI](https://img.shields.io/pypi/v/shipsignal.svg)](https://pypi.org/project/shipsignal/) [![Python](https://img.shields.io/pypi/pyversions/shipsignal.svg)](https://pypi.org/project/shipsignal/) [![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

> **Is AI actually changing how your team ships — and can you prove it without overclaiming?**
> One read-only, local command points at any repo and tells you three things: how much AI is *actually* being used (measured from commit trailers, not guessed), whether delivery health is sound (graded against general engineering norms, never falsely credited to AI), and whether the repo is set up for agents to succeed — with the specific fixes. The only scanner honest enough to withhold a number it can't back up.

Pure Python stdlib, no runtime deps, runs on any repo in seconds. Read-only and local — nothing leaves your box.

## Install

```bash
uvx shipsignal report <repo>   # zero-install, via uv
# or
pip install shipsignal
```

Requires Python 3.11+. No runtime dependencies.

## Quick start

```bash
# Unified audit — all three numbers + fixes, one deliverable (recommended)
shipsignal report ../crown --html crown-audit.html

# Or run a single lens
shipsignal impact ../crown          # impact + delivery health
shipsignal scan ../crown            # readiness only
shipsignal scan . --fail-under 80   # CI gate
```

See [examples/crown-audit.html](examples/crown-audit.html) for a real audit deliverable. From a source checkout, the same commands run as `python -m shipsignal.cli …`.

## Impact lens — three always-on numbers

Every impact scan headlines with three numbers that are *always* computed (above a tiny sample floor):

| Number | What it is |
|---|---|
| **AI Adoption** | `Co-Authored-By:` trailer share + level (None / Emerging / Established / Pervasive). The one direct, AI-specific signal — reported as a lower bound (squash-merges drop trailers). |
| **Delivery Health** | A 0–100 snapshot scored against general engineering norms — *not* AI-attributed. Combines change-size discipline, test discipline, and (for teams) knowledge distribution. Flags surface real risks (`low test discipline`, `concentration risk`). |
| **Readiness** | The static-state score (the readiness lens, below). Runs by default; `--no-readiness` to skip. |

A fourth, *conditional* **Before/after AI Enablement** delta appears only when the data supports it — a clean pre-AI baseline window AND ≥ 20 commits in both windows AND ≥ 50 commits total AND ≥ 6 weeks of history. In the wild that combination is rare (most repos are AI-from-inception, no-AI, or ambient-AI), so it's the *bonus*, not the headline — competitors fake this score; we don't.

Calibrated across crown (Pervasive · 55/F · 83/B — flags a real test gap), chalk (None · 77/C · 80/B — flags maintainer concentration), vitest (Emerging · 97/A · 97/A — clean). Every delivery number carries an attribution caveat: it measures general delivery health, never *proves* AI caused a change.

## Readiness lens — is the repo set up for agents?

| Detector | What |
|---|---|
| Entry point | Root README present and substantial |
| Agent instructions | `CLAUDE.md` / `AGENTS.md` / `.cursor/rules` / copilot-instructions (size-scaled) |
| Module README coverage | Each detected module is documented |
| Setup & conventions | test command, CI, deps/lockfile, lint/format/type config, `.editorconfig`, LICENSE, CONTRIBUTING, MCP path-resolution |
| Broken links | Markdown links resolve (with false-positive guards) |
| Doc freshness | Module docs haven't drifted behind their code |

Module detection is **ecosystem-aware** (npm / pnpm / Cargo workspaces, then a directory fallback), respects `.gitignore`, and excludes vendored/build dirs. Six scored categories sum to 100 (entry 20, agent 15, coverage 20, setup 20, integrity 13, freshness 12). Categories can be **n/a** or **indeterminate**; the score renormalizes over what was actually scored, so a small well-documented library isn't punished.

## Output

A canonical JSON (`readiness.json` / `impact.json` / combined `report` JSON — findings or metrics, **never file or diff contents**), CLI text, optional Markdown / HTML reports, and a `readiness: N/100` badge SVG. Exit non-zero with `--fail-under N` for CI gates.

## Project layout

- [shipsignal/](shipsignal/README.md) — the package (module map inside)
- `tests/` — stdlib `unittest` suite
- [examples/](examples/) — a committed sample audit
- Working with an agent? See [CLAUDE.md](CLAUDE.md) / [AGENTS.md](AGENTS.md).

## License

MIT (see [pyproject.toml](pyproject.toml)).
