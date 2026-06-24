# Contributing

Thanks for helping improve ShipSignal.

## Project status

ShipSignal is maintained as a solo project. **Issues and bug reports are very welcome** — they're the most useful contribution right now, especially scan results that look wrong on a real repo. Pull requests are reviewed as time allows; for anything non-trivial, please open an issue first so we can align on the approach before you invest in a PR.

## Dev setup

- Python 3.11+ (the scanner core is **stdlib only** — no runtime deps).
- Run a scan: `python -m shipsignal.cli scan .`
- Run tests: `python -m unittest discover -s tests -v` (or `make test`).

## Before a PR

- `make test` must pass.
- The repo must pass its own scan: `python -m shipsignal.cli scan . --fail-under 90` (or `make scan`).
- Keep the core stdlib-only, and preserve the false-positive guards in [shipsignal/detectors.py](shipsignal/detectors.py).

See [CLAUDE.md](CLAUDE.md) for architecture and conventions.
