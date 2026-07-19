"""Squash-merge attribution recovery from a user-exported PR-data file.

ShipSignal makes **zero network calls** — that promise is absolute, and this
module does not weaken it. The user exports their own PR data with one `gh`
command and ShipSignal *reads the local file*; nothing here opens a socket.

The pinned export recipe (validated against real squash-workflow repos):

    gh pr list --repo <owner/repo> --state merged \\
      --limit 25 --json number,mergeCommit,mergedAt,commits

(`--limit 1000` in a single call trips GitHub's GraphQL 500k-node ceiling on
repos with large PRs — the export must chunk, see docs/getting-started.md.)

Why this recovers anything at all — the calibrated finding behind Package D:
GitHub-native "Squash and merge" *preserves* co-authors (it aggregates every
squashed commit's authors into `Co-authored-by:` trailers on the squash commit),
so for most repos the local scan already sees them and there is nothing to
recover. But some pipelines **drop** the trailers — internal-monorepo sync bots
(e.g. jest's), some merge queues, manual local squashes, pre-2019 history. For
those, `mergeCommit.oid` names a squash commit whose local message carries no
trailer, while the PR's own commit records still list the AI co-author. This
module parses that PR data; `impact.py` matches it back by merge-commit SHA and
runs the recovered authors through the *same* registry matcher as local
trailers, so the recovered figure never silently replaces the measured one.

Parsing only — no registry/impact knowledge lives here (impact.py imports
prdata, one-way, mirroring timeline.py's dependency direction). Unlike
`config.py` (optional, never raises), a `--pr-data` file the user explicitly
passed is validated strictly: a shape that isn't the recipe's output raises
`PRDataError` naming the recipe, rather than degrading to a confusing zero.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

# The exact command whose output this module consumes. Surfaced in error
# messages and (via glossary.py) in the self-advertising recipe the report
# prints when a squash workflow is suspected and no --pr-data was given.
EXPORT_COMMAND = (
    "gh pr list --state merged --limit 25 "
    "--json number,mergeCommit,mergedAt,commits"
)


class PRDataError(ValueError):
    """A --pr-data file that doesn't match the pinned export recipe's shape."""


@dataclass(frozen=True)
class PRAuthor:
    """One author or co-author of a PR commit, as GitHub parsed it from the
    `Co-Authored-By:` trailers (primary author + co-authors, flattened)."""
    name: str
    email: str
    login: str = ""

    def as_trailer(self) -> str:
        """Synthesize the `Co-authored-by: Name <email>` trailer form so
        recovered authors flow through impact.py's existing trailer matcher —
        the same code path as locally-measured trailers, by construction."""
        return f"Co-authored-by: {self.name} <{self.email}>"


@dataclass
class PRRecord:
    number: int
    merge_oid: str | None          # SHA-join key against local squash commits
    merged_at: date | None
    authors: list[PRAuthor] = field(default_factory=list)  # distinct across the PR's commits


@dataclass
class PRData:
    records: list[PRRecord] = field(default_factory=list)

    @property
    def by_merge_oid(self) -> dict[str, PRRecord]:
        """Non-null merge SHAs -> record. GitHub squash/merge always populates
        mergeCommit for a merged PR; the empty case is the rebase-merge fallback
        (match by `(#123)` subject) impact.py owns."""
        return {r.merge_oid: r for r in self.records if r.merge_oid}

    @property
    def by_number(self) -> dict[int, PRRecord]:
        return {r.number: r for r in self.records}


def _parse_date(value: object) -> date | None:
    # mergedAt is "2026-06-21T12:13:06Z"; it's disclosure-only (matching is by
    # SHA), so an odd/absent value degrades to None rather than raising.
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _authors_of(pr: dict) -> list[PRAuthor]:
    """Distinct authors across all of a PR's commits, order-stable. Dedup key is
    login when present (GitHub's stable identity) else the lowercased email."""
    seen: set[str] = set()
    out: list[PRAuthor] = []
    for commit in pr.get("commits") or []:
        if not isinstance(commit, dict):
            continue
        for a in commit.get("authors") or []:
            if not isinstance(a, dict):
                continue
            name = str(a.get("name") or "")
            email = str(a.get("email") or "")
            login = str(a.get("login") or "")
            if not (name or email or login):
                continue
            key = login.lower() or email.lower() or name.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(PRAuthor(name=name, email=email, login=login))
    return out


def _looks_like_pr(item: object) -> bool:
    return isinstance(item, dict) and "number" in item and "commits" in item


def load_pr_data(path: Path) -> PRData:
    """Load + validate a `--pr-data` export. Raises PRDataError on a shape that
    isn't the recipe's output (top-level not a list, or items missing
    `number`/`commits`); an empty list is valid (a repo with no merged PRs).

    Optional fields degrade quietly: a null `mergeCommit` -> merge_oid None, an
    unparseable `mergedAt` -> None, a missing `login` -> "".
    """
    hint = f"expected the JSON array from `{EXPORT_COMMAND}`"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise PRDataError(f"--pr-data file not found: {path}") from None
    except (OSError, json.JSONDecodeError) as exc:
        raise PRDataError(f"could not read {path}: {exc} — {hint}") from exc

    if not isinstance(raw, list):
        raise PRDataError(
            f"{path} is a JSON {type(raw).__name__}, not an array — {hint}"
        )
    if raw and not any(_looks_like_pr(item) for item in raw):
        raise PRDataError(
            f"{path} doesn't look like PR data (no item has both 'number' and "
            f"'commits') — {hint}"
        )

    records: list[PRRecord] = []
    for item in raw:
        if not _looks_like_pr(item):
            # A stray non-PR element among valid ones: skip it rather than fail
            # the whole export (a mixed/edited file still yields real records).
            continue
        try:
            number = int(item["number"])
        except (TypeError, ValueError):
            continue
        merge = item.get("mergeCommit")
        merge_oid = merge.get("oid") if isinstance(merge, dict) else None
        records.append(PRRecord(
            number=number,
            merge_oid=merge_oid or None,
            merged_at=_parse_date(item.get("mergedAt")),
            authors=_authors_of(item),
        ))
    return PRData(records=records)
