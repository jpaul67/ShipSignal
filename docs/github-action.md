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
| `args` | *(empty)* | Extra arguments passed through to `shipsignal scan` (e.g. `--badge badge.svg`). |

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

## Versioning

Pin to the floating major tag **`@v1`** — it always points at the latest backwards-compatible
release of the Action. To pin exactly, reference a full tag or commit SHA instead.

> Note for maintainers: `v1` is re-pointed on each Action release. The PyPI release workflow only
> triggers on strict `vX.Y.Z` tags, so moving `v1` never publishes a package.

## Marketplace

The Action is currently consumed by repo reference (`jpaul67/ShipSignal@v1`) and is not listed on the
GitHub Marketplace. The `action.yml` already carries a `branding` block, so listing it later is a
one-checkbox step when drafting a release.
