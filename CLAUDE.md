# CLAUDE.md

Guidance for AI agents working in the ShipSignal repo. Human overview: [README.md](README.md). Package map: [shipsignal/README.md](shipsignal/README.md).

## What this is

ShipSignal — a read-only, LLM-free CLI with **two lenses**. Positioned Impact-first (the differentiator), with Readiness as the supporting third number:
- **Impact** (built, Phase C) — `git log` analytics. Every scan headlines with three always-on numbers: **AI Adoption** (the one direct AI signal — `Co-Authored-By:` trailers, lower bound, banded into None/Emerging/Established/Pervasive), **Delivery Health** (a 0–100 snapshot scored against general engineering norms, NOT AI-attributed — change-size discipline + test discipline + knowledge distribution, with surfaced flags), and **Readiness** (the static score). A fourth before/after AI Enablement delta appears only when a clean pre-AI baseline exists.
- **Readiness** (built, v0 + Phase A) — grades a repo 0–100 on whether it's set up for coding agents (READMEs, agent files, setup tooling, doc integrity/freshness) and lists the fixes.

Pure Python stdlib, no runtime dependencies. Both lenses share architecture and dogfood the same repo.

## Commands

- **Unified audit** (recommended for deliverables): `python -m shipsignal.cli report <path | url | owner/repo>`
  - Reports: `--json FILE` · `--md FILE` · `--html FILE`; `--adoption-date YYYY-MM-DD`
  - Runs both lenses; one combined document; the canonical audit form.
- Readiness only: `python -m shipsignal.cli scan <path | url | owner/repo>` — `--json FILE` · `--md FILE` · `--html FILE` · `--badge FILE` · `--badge-json FILE` (live shields.io endpoint badge — see README); CI gate: `--fail-under N`
- CLI text output is colored on a real terminal (`--no-color` / `NO_COLOR` / `FORCE_COLOR` control it — [shipsignal/ansi.py](shipsignal/ansi.py)); default (piped/non-TTY) output is unstyled.
- Impact only: `python -m shipsignal.cli impact <path | url | owner/repo>` — `--json FILE` · `--md FILE` · `--html FILE`; `--adoption-date YYYY-MM-DD`; `--no-readiness` to skip the embedded readiness number; `--timeline` to show the over-time trajectory.
- A `.shipsignal.toml` at the scan target's root is picked up automatically by every subcommand (including in CI) — see the config gotcha below for the schema and precedence rule.
- Tests: `python -m unittest discover -s tests -v` (or `make test`)
- Dogfood (the repo passes its own scan): `python -m shipsignal.cli scan . --fail-under 90` (or `make scan`)

## Architecture

Pipelines:
- Readiness: `cli` → `scanner` → (`modules` → `detectors` + `setupcheck` → `scoring`) → `report`
- Impact: `cli` → `impact.compute_impact` (→ `timeline.build_trajectory`) → `report.render_impact*`

- [shipsignal/modules.py](shipsignal/modules.py) — module detection + exclusions. **Ecosystem-aware first** (npm/pnpm/Cargo workspaces, anywhere in the tree), directory heuristic only as fallback. This is the part that most affects accuracy.
- [shipsignal/detectors.py](shipsignal/detectors.py) — doc/agent detectors and their false-positive guards.
- [shipsignal/setupcheck.py](shipsignal/setupcheck.py) — setup & convention detectors (build/test discoverability, lint/type config, MCP resolution).
- [shipsignal/scoring.py](shipsignal/scoring.py) — the 0–100 model.
- [shipsignal/impact.py](shipsignal/impact.py) — Impact lens: `walk_history` (single `git log --no-merges --numstat` pass, `\x1f`-separated), AI-trailer registry, **bot/merge exclusion** (`is_bot`/`_BOT_RE`), adoption detection, confidence gate, no-baseline path, pillar scoring.
- [shipsignal/timeline.py](shipsignal/timeline.py) — over-time trajectory: tumbling-window bucketing + per-period adoption % and delivery health; honest gaps for thin/empty periods. Imports from `impact` (one-way; `compute_impact` calls it via a local import to avoid a cycle).
- [shipsignal/glossary.py](shipsignal/glossary.py) — explanatory copy (single source of truth for inline section lines, HTML hover tooltips, and the "How to read this" block; keep the three in sync by editing here only).
- [shipsignal/gitinfo.py](shipsignal/gitinfo.py) — git via subprocess.

## Conventions & gotchas (read before editing)

- **Stdlib only.** No runtime dependencies (uses `tomllib`, `json`, `subprocess`, `pathlib`, `re`). Don't add deps without good reason.
- **Detectors must degrade gracefully.** A non-git directory still scans (freshness becomes *indeterminate*, not zero). Impact lens returns an `error` field on a non-git or empty repo, not a crash.
- **False-positive guards are load-bearing** (learned from real-repo calibration): skip `http`/`mailto`/anchor/absolute links, strip `#anchors`, ignore links that escape the repo, and treat agent-file freshness gently (`gentle=True`). Don't regress these.
- **n/a vs indeterminate vs scored** are distinct in [scoring.py](shipsignal/scoring.py) — preserve the distinction; the readiness score renormalizes over scored categories only.
- **Impact lens is honest by construction.** Three always-on numbers + one conditional bonus: AI Adoption (the only *direct* AI signal — lower bound), Delivery Health (general eng norms, NOT AI-attributed — never imply causation), Readiness (static). The before/after Enablement delta is the bonus, withheld unless a clean pre-AI baseline exists. Delivery-Health *flags* are blunt (`low test discipline`) on purpose — actionable, not score-padding. **Never read diff or prompt content** — only metadata (dates, sizes, paths, trailers).
- **The known-AI registry** ([impact.py](shipsignal/impact.py): `AI_TOOL_ALIASES`) is a versioned constant — extend deliberately, like the Readiness `SCORE_CAPS`. Matching is **exact-token**, not substring (`_tokens`/`_alias_key`): a short alias like `"amp"` must match the whole word `amp`, never a fragment of an unrelated one (`example.com`). Verify a tool's real trailer/account form against its own docs/commits before adding it — cite the source in the PR/CHANGELOG.
- **CLI color** ([ansi.py](shipsignal/ansi.py)) is the only place that emits ANSI codes; renderers in [report.py](shipsignal/report.py) stay pure by taking an explicit `color: bool` param rather than reading terminal state themselves. `ansi.resolve_enabled()` is the single on/off decision (flag > `NO_COLOR` > `FORCE_COLOR` > TTY probe) — don't duplicate that logic elsewhere.
- **Clones are full-history, never `--depth`** (freshness, adoption detection, and the before/after delta need the whole graph). Readiness clones **treeless** (`--filter=blob:none`); Impact/`report` clone **with blobs** (`treeless=False`) because `git log --numstat` triggers a per-commit blob fetch on a treeless clone and crawls on big repos.
- **Tests are stdlib `unittest`** in `tests/`. Run them before committing.
- **Commit identity.** Author commits as `jpaul67 <5659943+jpaul67@users.noreply.github.com>`, the project's canonical GitHub identity. The repo's local git config is already set to this — don't override it with a global or per-machine identity.
- **Repo-local config** ([config.py](shipsignal/config.py)): `.shipsignal.toml` at the scan target's root can override `extra_ai_aliases`, `squash` (`[impact]`), `fail_under`, `exclude_modules` (`[readiness]`), and `badge_label` (`[report]`). Precedence is **CLI flag > config file > built-in default** — enforce that order in `cli.py`, not in `config.py` itself. `load_config()` never raises: unknown keys and wrong-typed values become warnings (printed to stderr, default kept), a malformed file is skipped entirely. The schema is additive — future keys should warn-on-unknown too, not error, so old configs keep working. Alias-registry keys (built-in or config-supplied) must still be a single alnum token — matching is exact-token (see the AI-tool-registry gotcha above), so a hyphenated `extra_ai_aliases` key can never match anything and is rejected with a warning.
- **The change-failure proxy is never scored** ([impact.py](shipsignal/impact.py) `compute_outcomes`, rendered as part of the Outcomes block). The fix/revert subject rate measures commit-labeling discipline as much as failure rate — a repo with honest `fix:` conventions must never score worse than one with vague messages. Don't fold it into `delivery_health()`; it stays context, same rule as revert-pair time-to-correction (also commit-scoped, NOT MTTR — production incidents aren't in git). Revert-pair matching only trusts git's own `git revert` body line (`This reverts commit <sha>`) or explicit `Fixes:`/`Reverts:` trailers, matched by sha against the analyzed commit set; unmatched reverts (target outside the window) are disclosed via `unmatched`, never dropped silently. `walk_history`'s git-log format uses a `\x1e` sentinel (not `\n\n`) to split the commit header from the `--numstat` body, because a raw commit body (`%b`) can itself contain blank lines that would confuse a naive split.

## Where to read next

- [shipsignal/README.md](shipsignal/README.md) — package module map
- [README.md](README.md) — user-facing overview and scoring summary
