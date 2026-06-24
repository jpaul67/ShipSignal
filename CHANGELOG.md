# Changelog

All notable changes to ShipSignal are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Dates and pre-`0.6.4` version numbers are reconstructed from the commit history (only `0.6.4`+
are git-tagged).

## [Unreleased]

### Added
- **Squash-merge detection for the Impact lens.** When a repo's history looks squash-merged
  *and* measured AI adoption is low, the report flags that `Co-Authored-By` trailers are likely
  undercounted and labels the number a *floor*, not a measurement. Adds a `--squash` override
  for `impact` and `report` (for workflows whose squash subjects don't carry `(#123)`). The
  displayed adoption level is never altered — the caveat is purely additive.
- `SECURITY.md` (security policy + threat model) and this `CHANGELOG.md`.

## [0.6.5] — 2026-06-23

### Added
- `--version` flag.

## [0.6.4] — 2026-06-23

### Added
- PyPI release workflow (Trusted Publishing via OIDC); Python-version and topic classifiers.

### Changed
- Project URLs point at `jpaul67/ShipSignal`; added a getting-started guide.

### Fixed
- CI: Linux case-sensitive-filesystem and `PATH` failures; preserve `PATH` in test git-helpers.

## [0.6.3] — 2026-06-22

### Changed
- Readiness fixes: cross-detector specificity, copy-pasteable starter snippets, and a grouped
  finding renderer.

## [0.6.2] — 2026-06-22

### Changed
- Readiness fixes ranked by payoff and effort, with `file:line` locations.

## [0.6.1] — 2026-06-22

### Changed
- Detector accuracy: rules-aware grading, B3 newness handling, language floor, more concrete
  prose.

## [0.6.0] — 2026-06-22

### Added
- `trend` command: a visual snapshot viewer with a delta view and SVG line chart (offline, no
  re-scan).

## [0.5.0] — 2026-06-21

### Added
- `--snapshot`: persist a small (<8 KB) JSON record per scan under `.shipsignal/snapshots/`.

## [0.4.0] — 2026-06-21

### Added
- Impact: team-level AI-adoption breadth (aggregate only — never per-person).

## [0.3.0] — 2026-06-20

### Added
- Readiness: documentation tech-debt depth (doc freshness / staleness).

## [0.2.0] — 2026-06-20

### Added
- Readiness: agent-context enrichment.

## [0.1.0] — 2026-06-19

### Added
- Initial release. Readiness lens (agent-readiness scanner) with setup/convention detectors and
  Markdown / HTML / badge reports; Impact lens (git-history analytics) with three always-on
  numbers and a conditional before/after delta; unified `report` command. Published to PyPI as
  `shipsignal` (renamed from the original working name "bellwether").
