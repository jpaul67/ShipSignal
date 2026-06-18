# CLAUDE.md

Guidance for AI agents working in the Bellwether repo. Human overview: [README.md](README.md). Package map: [bellwether/README.md](bellwether/README.md).

## What this is

Bellwether — a read-only, LLM-free CLI with **two lenses**:
- **Readiness** (built, v0 + Phase A) — grades a repo 0–100 on whether it's set up for coding agents (READMEs, agent files, setup tooling, doc integrity/freshness) and lists the fixes.
- **Impact** (built, Phase C) — `git log` analytics. Every scan headlines with three always-on numbers: **AI Adoption** (the one direct AI signal — `Co-Authored-By:` trailers, lower bound, banded into None/Emerging/Established/Pervasive), **Delivery Health** (a 0–100 snapshot scored against general engineering norms, NOT AI-attributed — change-size discipline + test discipline + knowledge distribution, with surfaced flags), and **Readiness** (the static score). A fourth before/after AI Enablement delta appears only when a clean pre-AI baseline exists.

Pure Python stdlib, no runtime dependencies. Both lenses share architecture and dogfood the same repo.

## Commands

- **Unified audit** (recommended for deliverables): `python -m bellwether.cli report <path | url | owner/repo>`
  - Reports: `--json FILE` · `--md FILE` · `--html FILE`; `--adoption-date YYYY-MM-DD`
  - Runs both lenses; one combined document; the canonical audit form.
- Readiness only: `python -m bellwether.cli scan <path | url | owner/repo>` — `--json FILE` · `--md FILE` · `--html FILE` · `--badge FILE`; CI gate: `--fail-under N`
- Impact only: `python -m bellwether.cli impact <path | url | owner/repo>` — `--json FILE` · `--md FILE` · `--html FILE`; `--adoption-date YYYY-MM-DD`; `--no-readiness` to skip the embedded readiness number.
- Tests: `python -m unittest discover -s tests -v` (or `make test`)
- Dogfood (the repo passes its own scan): `python -m bellwether.cli scan . --fail-under 90` (or `make scan`)

## Architecture

Pipelines:
- Readiness: `cli` → `scanner` → (`modules` → `detectors` + `setupcheck` → `scoring`) → `report`
- Impact: `cli` → `impact.compute_impact` → `report.render_impact*`

- [bellwether/modules.py](bellwether/modules.py) — module detection + exclusions. **Ecosystem-aware first** (npm/pnpm/Cargo workspaces, anywhere in the tree), directory heuristic only as fallback. This is the part that most affects accuracy.
- [bellwether/detectors.py](bellwether/detectors.py) — doc/agent detectors and their false-positive guards.
- [bellwether/setupcheck.py](bellwether/setupcheck.py) — setup & convention detectors (build/test discoverability, lint/type config, MCP resolution).
- [bellwether/scoring.py](bellwether/scoring.py) — the 0–100 model.
- [bellwether/impact.py](bellwether/impact.py) — Impact lens: `walk_history` (single `git log --numstat` pass, `\x1f`-separated), AI-trailer registry, adoption detection, confidence gate, no-baseline path, pillar scoring.
- [bellwether/gitinfo.py](bellwether/gitinfo.py) — git via subprocess.

## Conventions & gotchas (read before editing)

- **Stdlib only.** No runtime dependencies (uses `tomllib`, `json`, `subprocess`, `pathlib`, `re`). Don't add deps without good reason.
- **Detectors must degrade gracefully.** A non-git directory still scans (freshness becomes *indeterminate*, not zero). Impact lens returns an `error` field on a non-git or empty repo, not a crash.
- **False-positive guards are load-bearing** (learned from real-repo calibration): skip `http`/`mailto`/anchor/absolute links, strip `#anchors`, ignore links that escape the repo, and treat agent-file freshness gently (`gentle=True`). Don't regress these.
- **n/a vs indeterminate vs scored** are distinct in [scoring.py](bellwether/scoring.py) — preserve the distinction; the readiness score renormalizes over scored categories only.
- **Impact lens is honest by construction.** Three always-on numbers + one conditional bonus: AI Adoption (the only *direct* AI signal — lower bound), Delivery Health (general eng norms, NOT AI-attributed — never imply causation), Readiness (static). The before/after Enablement delta is the bonus, withheld unless a clean pre-AI baseline exists. Delivery-Health *flags* are blunt (`low test discipline`) on purpose — actionable, not score-padding. **Never read diff or prompt content** — only metadata (dates, sizes, paths, trailers).
- **The known-AI registry** ([impact.py](bellwether/impact.py): `AI_TOOL_ALIASES`) is a versioned constant — extend deliberately, like the Readiness `SCORE_CAPS`.
- **Clone is treeless** (`--filter=blob:none`), never `--depth=1` — freshness *and* impact-history need git history.
- **Tests are stdlib `unittest`** in `tests/`. Run them before committing.

## Where to read next

- [bellwether/README.md](bellwether/README.md) — package module map
- [README.md](README.md) — user-facing overview and scoring summary
