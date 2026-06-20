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
- Readiness only: `python -m shipsignal.cli scan <path | url | owner/repo>` — `--json FILE` · `--md FILE` · `--html FILE` · `--badge FILE`; CI gate: `--fail-under N`
- Impact only: `python -m shipsignal.cli impact <path | url | owner/repo>` — `--json FILE` · `--md FILE` · `--html FILE`; `--adoption-date YYYY-MM-DD`; `--no-readiness` to skip the embedded readiness number; `--timeline` to show the over-time trajectory.
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
- [shipsignal/gitinfo.py](shipsignal/gitinfo.py) — git via subprocess.

## Conventions & gotchas (read before editing)

- **Stdlib only.** No runtime dependencies (uses `tomllib`, `json`, `subprocess`, `pathlib`, `re`). Don't add deps without good reason.
- **Detectors must degrade gracefully.** A non-git directory still scans (freshness becomes *indeterminate*, not zero). Impact lens returns an `error` field on a non-git or empty repo, not a crash.
- **False-positive guards are load-bearing** (learned from real-repo calibration): skip `http`/`mailto`/anchor/absolute links, strip `#anchors`, ignore links that escape the repo, and treat agent-file freshness gently (`gentle=True`). Don't regress these.
- **n/a vs indeterminate vs scored** are distinct in [scoring.py](shipsignal/scoring.py) — preserve the distinction; the readiness score renormalizes over scored categories only.
- **Impact lens is honest by construction.** Three always-on numbers + one conditional bonus: AI Adoption (the only *direct* AI signal — lower bound), Delivery Health (general eng norms, NOT AI-attributed — never imply causation), Readiness (static). The before/after Enablement delta is the bonus, withheld unless a clean pre-AI baseline exists. Delivery-Health *flags* are blunt (`low test discipline`) on purpose — actionable, not score-padding. **Never read diff or prompt content** — only metadata (dates, sizes, paths, trailers).
- **The known-AI registry** ([impact.py](shipsignal/impact.py): `AI_TOOL_ALIASES`) is a versioned constant — extend deliberately, like the Readiness `SCORE_CAPS`.
- **Clones are full-history, never `--depth`** (freshness, adoption detection, and the before/after delta need the whole graph). Readiness clones **treeless** (`--filter=blob:none`); Impact/`report` clone **with blobs** (`treeless=False`) because `git log --numstat` triggers a per-commit blob fetch on a treeless clone and crawls on big repos.
- **Tests are stdlib `unittest`** in `tests/`. Run them before committing.

## Where to read next

- [shipsignal/README.md](shipsignal/README.md) — package module map
- [README.md](README.md) — user-facing overview and scoring summary
