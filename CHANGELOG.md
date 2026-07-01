# Changelog

All notable changes to ShipSignal are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Dates and pre-`0.6.4` version numbers are reconstructed from the commit history (only `0.6.4`+
are git-tagged).

## [Unreleased]

### Added
- **GitHub Action** (composite) wrapping `shipsignal scan` — gates the readiness score
  (`fail-under`) and posts the Markdown report to the run's job summary. Pin via the floating
  `@v1` tag. See [docs/github-action.md](docs/github-action.md). The PyPI release trigger was
  tightened to strict `vX.Y.Z` tags so the `v1` Action tag never fires a publish.
- Community health: `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1), GitHub issue forms
  (bug / feature) and a pull-request template.
- **AI-tool registry additions**, each verified against the tool's own docs/commits: Codex
  (`Co-authored-by: Codex <noreply@openai.com>`), Amp
  (`Co-authored-by: Amp <amp@ampcode.com>`), Roo Code
  (`Co-authored-by: Roo Code <roomote@roocode.com>`), and Jules's bot account
  (`google-labs-jules[bot]`). Candidates without a confirmed trailer/account form (Windsurf,
  Cline, OpenHands, Goose, Amazon Q, Junie, Kiro, Qodo) were deliberately left out rather than
  guessed — add them once their real form is verified.
- **Colored CLI output** ([shipsignal/ansi.py](shipsignal/ansi.py)): the three Impact headline
  numbers, readiness score/grade, and flag lines are colored on a real terminal. Off by default
  when piped; respects `--no-color`, `NO_COLOR`, and `FORCE_COLOR`.
- `--badge-json FILE` (on `scan` and `report`): a [shields.io endpoint
  payload](https://shields.io/badges/endpoint-badge) for a *live* README badge that updates
  without a new commit — see [examples/workflows/live-badge.yml](examples/workflows/live-badge.yml).

### Fixed
- CI flake: hardened the test git helpers with `gc.auto=0` / `maintenance.auto=false` (mirroring
  the scanner's own git flags) so background auto-gc can't abort a commit during many-commit test
  loops.
- **AI-adoption false positives**: `AI_TOOL_ALIASES` matching was a bare substring test, so a
  short alias could match inside an unrelated word (e.g. a hypothetical `"amp"` alias would have
  matched `example.com`). Matching is now exact-token (`shipsignal/impact.py: _tokens`), fixed
  before any short aliases were added to the registry.

## [0.6.6] — 2026-06-26

### Added
- **Squash-merge detection for the Impact lens.** When a repo's history looks squash-merged
  *and* measured AI adoption is low, the report flags that `Co-Authored-By` trailers are likely
  undercounted and labels the number a *floor*, not a measurement. Adds a `--squash` override
  for `impact` and `report` (for workflows whose squash subjects don't carry `(#123)`). The
  displayed adoption level is never altered — the caveat is purely additive.
- `SECURITY.md` (security policy + threat model) and this `CHANGELOG.md`.
- CI matrix: 3 OS × Python 3.11–3.13 with ruff lint gate (package cleaned from 47 lint errors to 0).

### Fixed
- HTML report renders the full styled page when git history is unavailable (was falling back to a bare text block).

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
