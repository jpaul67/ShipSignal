# ShipSignal GitHub Action

Gate your repo's **agent-readiness** score in CI and post the readiness report to each run's
summary. The Action is a thin composite wrapper around `shipsignal scan` — it installs ShipSignal
from PyPI and runs it, so it inherits the same read-only, no-network behaviour as the CLI.

## Quick start

```yaml
# .github/workflows/shipsignal.yml
name: readiness
on: [push, pull_request]
jobs:
  shipsignal:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: jpaul67/ShipSignal@v1
        with:
          fail-under: "80"
```

A ready-to-copy version lives at [examples/workflows/shipsignal.yml](../examples/workflows/shipsignal.yml).

## What it does

1. Sets up Python and `pip install`s `shipsignal`.
2. Runs `shipsignal scan` on your repo, producing JSON + Markdown.
3. Writes the Markdown report to the run's **Summary** tab (see the job page on GitHub).
4. Exposes the score as a step output.
5. If `fail-under` is set and the score is below it, fails the job (non-zero exit).

The gate is enforced by the Action itself (not the CLI's `--fail-under`), so the summary and outputs
are always produced — even on a failing score.

## Inputs

| Input | Default | Description |
|---|---|---|
| `path` | `.` | Path to the repo or subdirectory to scan. |
| `fail-under` | *(empty)* | Fail the job if the score is below this number (0–100). Empty = report only, never fail. |
| `version` | *(empty)* | Pin the ShipSignal version from PyPI (e.g. `0.6.6`). Empty installs the latest. |
| `python-version` | `3.12` | Python version used to run ShipSignal. |
| `summary` | `true` | Write the Markdown report to the job summary. Set `false` to skip. |
| `args` | *(empty)* | Extra arguments passed through to `shipsignal scan` (e.g. `--badge badge.svg`, `--badge-json badge.json`). |
| `pr-comment` | `false` | Post (and keep updated) a sticky PR comment with the score, grade, and top 3 fixes. Only fires on `pull_request`/`pull_request_target` events — see [PR comments](#pr-comments) below. |

## Outputs

| Output | Description |
|---|---|
| `score` | The readiness score (0–100). |
| `passed` | `true` if the score met the threshold (or none was set), else `false`. |

## Examples

**Report only (never fails the build):**

```yaml
      - uses: jpaul67/ShipSignal@v1   # no fail-under → informational
```

**Pin the ShipSignal version for reproducible runs:**

```yaml
      - uses: jpaul67/ShipSignal@v1
        with:
          fail-under: "80"
          version: "0.6.6"
```

**Scan a subdirectory and use the score in a later step:**

```yaml
      - id: ship
        uses: jpaul67/ShipSignal@v1
        with:
          path: packages/core
          fail-under: "75"
      - run: echo "Readiness was ${{ steps.ship.outputs.score }}"
```

**Publish a live badge** (`--badge-json` passed through via `args`, then republished to a gist so a
README badge updates without a new commit every time the score changes — full recipe in
[examples/workflows/live-badge.yml](../examples/workflows/live-badge.yml)):

```yaml
      - uses: jpaul67/ShipSignal@v1
        with:
          args: "--badge-json badge.json"
      - env:
          GH_TOKEN: ${{ secrets.GIST_TOKEN }}
          GIST_ID: ${{ vars.GIST_ID }}
        run: gh gist edit "$GIST_ID" badge.json
```

## PR comments

Every job summary is easy to miss — nobody browses the Summary tab by habit. Setting
`pr-comment: "true"` posts a compact comment directly on the pull request instead: score, grade,
pass/fail against `fail-under`, and the top 3 fixes by payoff. The comment is **sticky** — a
hidden `<!-- shipsignal-report -->` marker lets the Action find and update its own comment on
every subsequent push, instead of stacking a new one each time.

```yaml
# .github/workflows/shipsignal.yml
name: readiness
on: [push, pull_request]
permissions:
  pull-requests: write   # required for the Action to post/update the comment
jobs:
  shipsignal:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: jpaul67/ShipSignal@v1
        with:
          fail-under: "80"
          pr-comment: "true"
```

Requirements and caveats:

- The calling workflow needs `permissions: pull-requests: write` for the default
  `GITHUB_TOKEN` to be able to post/update comments. Without it, GitHub still runs the step but
  the API calls are rejected — see the fork caveat below for what that looks like.
- Only fires when the triggering event carries a pull-request number (`pull_request` or
  `pull_request_target`). On a plain `push`, the input is silently ignored.
- **Fork PRs**: for `pull_request` (not `_target`) events from a fork, GitHub always issues a
  read-only token regardless of the workflow's declared permissions. The Action detects the
  failed write, logs an `::notice::` in the run log, and continues — it never fails the job over
  a comment it couldn't post.
- Delta-vs-base-branch (e.g. "readiness dropped 4 points from `main`") is **out of scope** for
  this version — it would need a second scan of the base ref. Noted here as a planned follow-up,
  not implemented.
- The comment is built directly from the same JSON the job summary uses, so it always matches —
  there's no separate rendering path to drift.

## Versioning

Pin to the floating major tag **`@v1`** — it always points at the latest backwards-compatible
release of the Action. To pin exactly, reference a full tag or commit SHA instead.

> Note for maintainers: `v1` is re-pointed on each Action release. The PyPI release workflow only
> triggers on strict `vX.Y.Z` tags, so moving `v1` never publishes a package.

## Marketplace

The Action is currently consumed by repo reference (`jpaul67/ShipSignal@v1`) and is not listed on the
GitHub Marketplace. The `action.yml` already carries a `branding` block, so listing it later is a
one-checkbox step when drafting a release.
