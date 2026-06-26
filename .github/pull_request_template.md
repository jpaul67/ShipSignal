## What & why

<!-- What does this change, and why? For non-trivial changes, link the issue you opened first. -->

Closes #

## Checklist

- [ ] For non-trivial changes, I opened an issue first to align on approach (see [CONTRIBUTING.md](../CONTRIBUTING.md)).
- [ ] `make test` passes.
- [ ] `make scan` passes (self-scan stays ≥ 90).
- [ ] The scanner core stays **stdlib-only**, and the false-positive guards in `shipsignal/detectors.py` are preserved.
- [ ] Updated `CHANGELOG.md` (`[Unreleased]`) if this is user-facing.
- [ ] Updated docs (README / `docs/`) if behavior changed.
