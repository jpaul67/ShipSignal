# Contributing

Thanks for helping improve Bellwether.

## Dev setup

- Python 3.11+ (the scanner core is **stdlib only** — no runtime deps).
- Run a scan: `python -m bellwether.cli scan .`
- Run tests: `python -m unittest discover -s tests -v` (or `make test`).

## Before a PR

- `make test` must pass.
- The repo must pass its own scan: `python -m bellwether.cli scan . --fail-under 90` (or `make scan`).
- Keep the core stdlib-only, and preserve the false-positive guards in [bellwether/detectors.py](bellwether/detectors.py).

See [CLAUDE.md](CLAUDE.md) for architecture and conventions.
