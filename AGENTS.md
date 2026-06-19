# AGENTS.md

This repo's canonical agent guide is [CLAUDE.md](CLAUDE.md) — read it first. `AGENTS.md` exists so non-Claude agents find the same guidance; it's a short pointer, not a duplicate.

**ShipSignal** — a read-only, LLM-free agent-readiness scanner (Python 3.11+, stdlib only).

## Essential commands

- Scan: `python -m shipsignal.cli scan <path | url | owner/repo>`
- Tests: `python -m unittest discover -s tests -v`
- Self-scan gate: `python -m shipsignal.cli scan . --fail-under 80`

## Top rules (full list in [CLAUDE.md](CLAUDE.md))

- Stdlib only — no runtime dependencies in the v0 scanner.
- Detectors must never crash on bad input (catch and skip); a non-git dir still scans.
- Keep the false-positive guards in [shipsignal/detectors.py](shipsignal/detectors.py) intact.
- Clone treeless (`--filter=blob:none`), never shallow — freshness needs history.

See [CLAUDE.md](CLAUDE.md) and [shipsignal/README.md](shipsignal/README.md) for detail.
