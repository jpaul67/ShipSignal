# Getting started with ShipSignal

> **Is AI actually changing how your team ships — and can you prove it without overclaiming?**

ShipSignal is a read-only CLI that points at any git repo and tells you three things in seconds:

1. **AI Adoption** — how much AI your team is *actually* using (measured from commit trailers, not a survey).
2. **Delivery Health** — whether shipping habits are sound, graded against general engineering norms and *never* attributed to AI.
3. **Readiness** — whether the repo is set up for AI agents to succeed, with a ranked fix list.

Pure Python stdlib, no dependencies, fully local. Nothing leaves your machine.

## Install

```bash
# Zero-install via uv (recommended)
uvx shipsignal report <repo>

# Or install normally
pip install shipsignal
```

Requires Python 3.11+. No runtime dependencies.

## Run your first audit

The `report` command is the starting point — it runs both lenses and produces one combined deliverable:

```bash
shipsignal report /path/to/repo --html audit.html
```

Open `audit.html` in any browser. You'll see:

- A **header** with the repo name, date range, commit count, and a run timestamp.
- **Three headline cards** — AI Adoption level, Delivery Health score, and Readiness score.
- **Delivery Health breakdown** — change-size discipline, test discipline, knowledge distribution, each with a bar and percentage. If any component is flagged, a "Where to focus" section shows what to work on with concrete numbers.
- **Before/after AI Enablement** — appears only when the data supports it (a clean pre-AI baseline). Withheld otherwise, because ShipSignal refuses to overclaim.
- **Readiness breakdown** — six scored categories (entry point, agent instructions, module coverage, setup & conventions, link integrity, doc freshness) with a ranked fix list showing `+N pts`, effort, and `file:line`.

## The four commands

| Command | What it answers | When to use it |
|---|---|---|
| `shipsignal report <repo>` | All three numbers + fixes | **Start here** — the full audit |
| `shipsignal impact <repo>` | Is AI changing how we ship? | You only want adoption + delivery health |
| `shipsignal scan <repo>` | Is the repo agent-ready? | You only want readiness + ranked fixes |
| `shipsignal trend .` | How are we moving over time? | You've saved `--snapshot`s and want deltas |

## Output formats

Every command supports multiple output formats via flags:

| Flag | Format | Best for |
|---|---|---|
| *(none)* | CLI text | A quick look in your terminal |
| `--html FILE` | HTML one-pager | Sharing — email it, open in any browser |
| `--md FILE` | Markdown | Dropping into a PR, issue, or wiki |
| `--json FILE` | JSON | Dashboards, scripts, automation |
| `--badge FILE` | SVG badge (scan only) | A `readiness: N/100` shield in your README |

Combine them freely:

```bash
shipsignal report ./my-repo --html audit.html --md audit.md --json audit.json
```

## Reading the three numbers

### AI Adoption

Counts commits with an AI `Co-Authored-By:` trailer (Claude, Copilot, etc.) plus commits authored by AI coding-agent bots (Devin, gpt-engineer, etc.), over all development commits (maintenance bots excluded). Reported as a **lower bound** — squash-merges drop trailers.

Banded: **None** / **Emerging** (<10%) / **Established** (<50%) / **Pervasive** (>=50%).

Also shows **breadth** — the share of active contributors with at least one AI commit. Team-level only; ShipSignal never scores, ranks, or lists individual developers.

### Delivery Health

A 0-100 score from three components:

- **Change-size discipline** (weight 35) — small, frequent commits vs large risky ones.
- **Test discipline** (weight 35) — how often code-touching commits also touch tests.
- **Knowledge distribution** (weight 30) — whether knowledge is spread across the team or concentrated in one person.

Scored against general engineering norms. **Deliberately not credited to AI** — a delivery change may come from hiring, a finished migration, or a calmer quarter. The "Where to focus" section maps flagged components to specific observations with concrete numbers from the repo's own metrics.

### Readiness

A 0-100 static-state score across six categories:

| Category | Points | What it checks |
|---|---|---|
| Entry point | 20 | Root README present and substantial |
| Agent instructions | 15 | CLAUDE.md / AGENTS.md / .cursor/rules / equivalent |
| Module coverage | 20 | Each detected module has a README |
| Setup & conventions | 20 | Test command, CI, deps, lint config, LICENSE, etc. |
| Doc integrity | 13 | Markdown links actually resolve |
| Doc freshness | 12 | Docs haven't drifted behind their code |

Fixes are ranked by payoff (`+N pts`) with an effort tag and `file:line` location. Categories that don't apply are excluded and the score renormalizes, so a small library isn't punished.

## CI gate

Add a readiness floor to your pipeline:

```bash
shipsignal scan . --fail-under 80
```

Exits non-zero if the readiness score drops below the threshold.

## Tracking progress over time

Add `--snapshot` to any command to persist a small JSON record:

```bash
shipsignal report . --snapshot                    # saves to .shipsignal/snapshots/
shipsignal report . --snapshot path/to/snap.json  # explicit path
```

Then view the trend:

```bash
shipsignal trend . --html trend.html
shipsignal trend . --limit 8 --since 2026-01-01
```

The trend view reads only saved snapshots — no re-scan, fully offline.

## Remote repos

Point at any GitHub repo without cloning it first:

```bash
shipsignal report owner/repo --html audit.html
shipsignal report https://github.com/owner/repo --html audit.html
```

ShipSignal clones into a temp directory (cleaned up automatically).

## What ShipSignal will not do

These are design constraints, not missing features:

- **No individual scoring** — adoption breadth is a team aggregate. ShipSignal structurally cannot rank or list individual developers.
- **No AI causation claims** — delivery health measures general engineering norms. The tool never states or implies that AI caused a delivery improvement.
- **No file contents** — it reads commit metadata (trailers, timestamps, paths touched) and the file tree structure, never diffs or source code.
- **No network calls** — everything runs locally. Nothing is sent anywhere.
- **No fabricated numbers** — before/after analysis is withheld (not zeroed) when the data doesn't support it. An "n/a" is more honest than a guess.
