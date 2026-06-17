# CLAUDE.md

Guidance for AI agents working in the Bellwether repo. Human overview: [README.md](README.md). Package map: [bellwether/README.md](bellwether/README.md).

## What this is

Bellwether v0 — a read-only, LLM-free **agent-readiness scanner**. It grades a repo (0–100) on how ready it is for coding agents and lists the fixes. Pure Python stdlib, no runtime dependencies. It is the seed of the larger Bellwether AI-enablement tool, so keep it consistent with that (Python) stack.

## Commands

- Run a scan: `python -m bellwether.cli scan <path | url | owner/repo>`
- JSON + CI gate: `python -m bellwether.cli scan . --json readiness.json --fail-under 80`
- Tests: `python -m unittest discover -s tests -v`
- Dogfood (the repo should pass its own scan): `python -m bellwether.cli scan . --fail-under 80`

## Architecture

Pipeline: `cli` → `scanner` → (`modules` → `detectors` → `scoring`) → `report`.

- [bellwether/modules.py](bellwether/modules.py) — module detection + exclusions. **Ecosystem-aware first** (npm/pnpm/Cargo workspaces, anywhere in the tree), directory heuristic only as fallback. This is the part that most affects accuracy.
- [bellwether/detectors.py](bellwether/detectors.py) — the static detectors and their false-positive guards.
- [bellwether/scoring.py](bellwether/scoring.py) — the 0–100 model.
- [bellwether/gitinfo.py](bellwether/gitinfo.py) — git via subprocess.

## Conventions & gotchas (read before editing)

- **Stdlib only.** No runtime dependencies (uses `tomllib`, `json`, `subprocess`, `pathlib`, `re`). Don't add deps to the v0 scanner without good reason.
- **Detectors must degrade gracefully.** A non-git directory still scans (freshness becomes *indeterminate*, not zero). Never crash on a malformed manifest — catch and skip.
- **False-positive guards are load-bearing** (learned from real-repo calibration): skip `http`/`mailto`/anchor/absolute links, strip `#anchors`, ignore links that escape the repo, and treat agent-file freshness gently (`gentle=True`). Don't regress these.
- **n/a vs indeterminate vs scored** are distinct in [scoring.py](bellwether/scoring.py) — preserve the distinction; the score renormalizes over scored categories only.
- **Clone is treeless** (`--filter=blob:none`), never `--depth=1` — freshness needs git history.
- **Tests are stdlib `unittest`** in `tests/`. Run them before committing.

## Where to read next

- [bellwether/README.md](bellwether/README.md) — package module map
- [README.md](README.md) — user-facing overview and scoring summary
