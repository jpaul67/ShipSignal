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

## Reading the numbers

### AI Adoption

Counts commits with an AI `Co-Authored-By:` trailer (Claude, Copilot, etc.) plus commits authored by AI coding-agent bots (Devin, gpt-engineer, etc.), over all development commits (maintenance bots excluded). Reported as a **lower bound**: GitHub-native squash keeps co-authors, but some pipelines (internal-sync bots, some merge queues) strip them — `--pr-data` recovers those (below).

Banded: **None** / **Emerging** (<10%) / **Established** (<50%) / **Pervasive** (>=50%).

Also shows **breadth** — the share of active contributors with at least one AI commit. Team-level only; ShipSignal never scores, ranks, or lists individual developers.

**Recovering squash-dropped attribution (`--pr-data`).** If your merge pipeline strips `Co-Authored-By` trailers — internal-monorepo sync bots, some merge queues, manual local squashes — the local adoption number undercounts AI. Recover it with **zero network calls**: you export the PR data, ShipSignal reads the local file.

```bash
gh pr list --state merged --limit 25 --json number,mergeCommit,mergedAt,commits > pr.json
shipsignal impact <repo> --pr-data pr.json
```

ShipSignal matches each squash commit to its PR by merge-commit SHA (or `(#NNN)` subject) and shows a dual figure — `measured X% · recovered Y%` with match coverage — never replacing the measured number. Coverage discloses staleness: a partial export reads as low coverage, not a confident number. On repos with many or large PRs, `--limit 1000` in one call hits GitHub's GraphQL node ceiling, so export in chunks of ~25. **Most GitHub repos need nothing here** — native squash already preserves co-authors, and the report only nudges you toward `--pr-data` when it detects a squash workflow that might be undercounting.

### Delivery Health

A 0-100 score from three components:

- **Change-size discipline** (weight 35) — small, frequent commits vs large risky ones.
- **Test discipline** (weight 35) — how often code-touching commits also touch tests.
- **Knowledge distribution** (weight 30) — whether knowledge is spread across the team or concentrated in one person.

Scored against general engineering norms. **Deliberately not credited to AI** — a delivery change may come from hiring, a finished migration, or a calmer quarter. The "Where to focus" section maps flagged components to specific observations with concrete numbers from the repo's own metrics.

### Outcomes (context, never scored)

Alongside Delivery Health, an **Outcomes** block reports two more numbers — always displayed, never folded into any score:

- **Revert pairs + median time-to-correction** — a commit whose body matches git's own `git revert` format (subject `Revert "..."` + body `This reverts commit <sha>`), or carries an explicit `Fixes:`/`Reverts:` trailer, is matched by sha against the analyzed history. A revert-of-a-revert is just another pair. Reverts whose target isn't in the analyzed window are disclosed as unmatched, never hidden. Reports `n/a` below 3 matched pairs. **Not MTTR** — this is commit-scoped; production incidents aren't in git.
- **Change-failure proxy** — the fix/revert subject rate, relabeled honestly: it measures commit-labeling discipline as much as failure rate, so a repo with honest `fix:` conventions must never score worse than one with vague commit messages. Context only — it's forbidden from ever feeding Delivery Health.

### Release cadence & lead time (context, never scored)

Two more numbers from version tags, always displayed, never scored:

- **Release cadence** — tags-per-month + median gap between tags, over the trailing 12 months (falling back to the full tag history when that window is sparse — the window used is disclosed). Tags are filtered to release-shaped ones: default `v?N.N[.N]`, overridable per repo via `.shipsignal.toml`'s `release_tag_pattern` (for monorepo tags like `pkg@1.2.3`).
- **Lead time** — median days from a commit landing to the release tag that shipped it, over every consecutive tag pair (one `git log` call per pair, never per commit).

Reports `n/a` below 3 matched release-shaped tags. **Tags aren't deploys** — a service can deploy without tagging — so an untagged repo is never penalized, only shown `n/a`. Together with Outcomes above, this is the DORA-shaped story from git history alone: deploy frequency ✓, lead time ✓, change-failure proxy ✓ (context), time-to-restore ✗ (incidents aren't in git).

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

## Configuration

Drop a `.shipsignal.toml` in the repo root for team-wide defaults, picked up automatically by every command (local or CI):

```toml
[impact]
extra_ai_aliases = { "acmebot" = "Acme internal" }
squash = true
release_tag_pattern = "^pkg@\\d+\\.\\d+\\.\\d+$"

[readiness]
fail_under = 80
exclude_modules = ["vendor/legacy"]

[report]
badge_label = "readiness"
```

Precedence is CLI flag > config file > built-in default, so `--fail-under` on the command line always wins. A typo never breaks a scan — an unknown key or wrong-typed value prints a warning and falls back to the default.

## CI gate

Add a readiness floor to your pipeline:

```bash
shipsignal scan . --fail-under 80
```

Exits non-zero if the readiness score drops below the threshold.

On GitHub Actions, use the first-party Action instead — same gate, plus the report in the run summary:

```yaml
# .github/workflows/shipsignal.yml
name: readiness
on: [push, pull_request]
jobs:
  shipsignal:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: jpaul67/ShipSignal@v1
        with:
          fail-under: "80"
```

See [github-action.md](github-action.md) for all inputs/outputs and more examples.

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
