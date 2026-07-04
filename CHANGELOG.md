# Changelog

All notable changes to ShipSignal are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Dates and pre-`0.6.4` version numbers are reconstructed from the commit history (only `0.6.4`+
are git-tagged).

## [Unreleased]

## [0.9.0] — 2026-07-03

### Added
- **Release cadence & lead time from tags** (Package K). A new block reports tags-per-month +
  median gap between tags (trailing 12 months, falling back to the full tag history when sparse —
  the window used is disclosed), and median lead time (days from a commit landing to the release
  tag that shipped it, over every consecutive tag pair — one `git log` call per pair, never per
  commit). Tags are filtered to release-shaped ones (default `v?N.N[.N]`, overridable via
  `.shipsignal.toml`'s `[impact].release_tag_pattern` for monorepo tags like `pkg@1.2.3`). Reports
  `n/a` below 3 matched tags — tags aren't deploys, so an untagged repo is never penalized.
  Context only, same as Package J's Outcomes block — never folded into Delivery Health. With both
  landed, that's deploy frequency, lead time, and the change-failure proxy from git history alone,
  zero integrations (time-to-restore stays `✗` — production incidents aren't in git).
- **Outcomes: revert pairs & time-to-correction** (Package J). A new Outcomes block in the impact
  text/Markdown/HTML output reports revert-pair count + median time-to-correction, matched by sha
  against the analyzed history — git's own `git revert` body format (`Revert "..."` + `This
  reverts commit <sha>`), or an explicit `Fixes:`/`Reverts:` trailer. A revert-of-a-revert is just
  another pair; reverts whose target falls outside the analyzed window are disclosed as
  `unmatched`, never dropped silently. Reports `n/a` below 3 matched pairs. Commit-scoped by
  construction — not MTTR, since production incidents aren't in git. The existing fix/revert
  subject rate is relabeled as the **change-failure proxy** and rendered alongside it: a
  labeling-discipline signal, not a failure rate, and — like time-to-correction — forbidden from
  ever feeding the Delivery Health score.
- **`.shipsignal.toml` config file** (Package G). Repo-local defaults, picked up automatically
  by every command (including in CI): `extra_ai_aliases` and `squash` under `[impact]`;
  `fail_under` and `exclude_modules` under `[readiness]`; `badge_label` under `[report]`.
  Precedence is CLI flag > config file > built-in default. Validation never crashes a scan — an
  unknown key or wrong-typed value degrades to a warning (printed to stderr) plus the built-in
  default; a malformed file is skipped entirely. `extra_ai_aliases` keys must be a single alnum
  word (matching is exact-token, like the built-in registry) — a hyphenated key is rejected with
  a warning rather than silently matching nothing. The Action (`action.yml`) always passes
  `--fail-under 0` internally so a scanned repo's own `fail_under` can never hijack the job's
  pass/fail decision, which stays controlled solely by the `fail-under` input.

## [0.8.0] — 2026-07-02

### Added
- **README hero image + social-preview card.** The README now leads with a screenshot of a
  rendered report instead of another paragraph of prose (`docs/assets/report-hero.png`), and the
  repo has a 1280×640 social-preview image (`docs/assets/social-preview.png`) for link previews.
- **GitHub Action: sticky PR comments.** New `pr-comment` input posts a compact Markdown comment
  (score, grade, pass/fail, top 3 fixes by payoff) on the triggering pull request, and keeps it
  updated in place via a hidden `<!-- shipsignal-report -->` marker rather than stacking
  duplicates. Requires `permissions: pull-requests: write` on the calling workflow. Degrades to
  an `::notice::` log line (never fails the job) when the token can't write comments — the case
  for `pull_request` events from a fork, where GitHub always issues a read-only token regardless
  of declared permissions. Base-branch delta reporting is explicitly out of scope for this
  version. `ci.yml`'s own `action` dogfood job now runs with `pr-comment: "true"`, so every PR to
  this repo demonstrates the feature on itself. (Caught live on the dogfood PR: `gh api`'s
  `-f`/`--raw-field` always sends a literal string — only `-F`/`--field` reads `@path` as file
  content — so the comment body is posted with `-F`.)

### Fixed
- **Security hardening from a repo audit**: `gitinfo.clone` now puts a `--` separator before the
  URL argument, so a hostile target string starting with `-` can never be parsed as a `git`
  option (argument injection, not shell injection — clone was already argv-based). Added
  `permissions: contents: read` to `ci.yml` and `live-badge.yml` (least-privilege for the
  default `GITHUB_TOKEN`). `SECURITY.md`'s supported-versions table now tracks `0.7.x`.
- All third-party Actions (`actions/checkout`, `actions/setup-python`, `actions/upload-artifact`,
  `actions/download-artifact`, `pypa/gh-action-pypi-publish`) are now pinned to commit SHAs
  instead of floating tags, with `.github/dependabot.yml` added to keep them current. Repo-side:
  enabled secret scanning + push protection + Dependabot security updates, added a tag-scoped
  (`v*.*.*`) deployment policy on the `pypi` environment, and minimal `main` branch protection
  (blocks force-push/deletion only — no PR requirement, so direct pushes still work).
- **CI**: `ci.yml`'s `test` job now checks out full history (`fetch-depth: 0`). The self-scan
  dogfood tests (`TestSelfImpact` et al.) walk this repo's own git log; a shallow depth-1
  checkout leaves only whatever single commit triggered the run, which on a `pull_request` event
  is the synthetic PR-merge commit — surfaced the first time this repo got a real PR (Dependabot's
  first bump), where that commit was bot-attributed and got misclassified as "no development
  commits to analyze."

## [0.7.0] — 2026-07-01

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
