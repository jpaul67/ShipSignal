"""AI line survival (Package L, slices 1–2): metadata-only blame aggregation.

Slice 1 is the incremental-blame parser + per-sha aggregator; slice 2 adds the
age-matched survival comparison (``matched_survival`` / ``compute_survival``).
There is still no CLI, report, or config wiring here — that is a later slice.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from shipsignal.gitinfo import blame_incremental, tracked_files
from shipsignal.impact import _CODE_EXTS

# Slice 2 — age-matched survival scoring.
# Caps and floors (honesty rails #2 and #4):
MAX_SURVIVAL_FILES = 400
MAX_SURVIVAL_LINES = 200_000
MIN_SURVIVAL_AGE_DAYS = 90
MIN_GROUP_COMMITS = 20
MIN_GROUP_LINES = 500


def parse_incremental_blame(text: str) -> dict[str, int]:
    """Count surviving lines per commit sha from ``git blame --incremental`` output.

    The incremental format is a sequence of blocks. Each block STARTS with a
    header line:

        <40-hex-sha> <orig-lineno> <final-lineno> <num-lines>

    followed by key/value metadata lines (``author``, ``author-time``,
    ``filename``, ...). The parser reads ONLY the header's sha and num-lines and
    SKIPS every metadata line.

    NOTE: the ``--incremental`` format carries NO source content by construction
    (no file lines are ever emitted), which is precisely why it is the only
    permitted blame form here. NEVER parse default ``git blame`` output — that
    form interleaves the file's actual source lines with each header, and reading
    them would amount to reading repo content.
    """
    surviving: dict[str, int] = {}
    for ln in text.splitlines():
        if not ln:
            continue
        parts = ln.split(" ")
        # A blame header has exactly 4 whitespace-separated numeric/hex fields;
        # metadata lines are "key value" (2 fields) or "key" (1 field), so the
        # 4-field check cleanly distinguishes headers from metadata without us
        # ever inspecting the metadata content itself.
        if len(parts) != 4:
            continue
        sha, _orig_lineno, _final_lineno, num_lines = parts
        if len(sha) != 40 or not _is_hex(sha):
            continue
        try:
            n = int(num_lines)
        except ValueError:
            continue
        try:
            int(_orig_lineno)
            int(_final_lineno)
        except ValueError:
            continue
        surviving[sha] = surviving.get(sha, 0) + n
    return surviving


def _is_hex(s: str) -> bool:
    for c in s:
        if c not in "0123456789abcdef":
            return False
    return True


def surviving_lines_by_sha(root: Path, paths: list[str]) -> dict[str, int]:
    """Merge surviving-line counts across the given source-file ``paths``.

    A path is included only if its lowercase suffix is in ``impact._CODE_EXTS``.
    Paths that ``blame_incremental`` returns None/empty for (e.g. binaries,
    untracked, or deleted files) are skipped. Paths are de-duplicated and sorted:
    a repeated path would otherwise blame the same file twice and double-count its
    lines, and sorting keeps the output deterministic. Returns a sha ->
    surviving-line-count dict.
    """
    result: dict[str, int] = {}
    for path in sorted(set(paths)):
        if Path(path).suffix.lower() not in _CODE_EXTS:
            continue
        out = blame_incremental(root, path)
        if not out:
            continue
        for sha, n in parse_incremental_blame(out).items():
            result[sha] = result.get(sha, 0) + n
    return result


def matched_survival(
    commits,
    surviving_lines: dict[str, int],
    ai_shas: set[str],
    adoption_dt: date,
    today: date,
    *,
    min_group_commits: int = MIN_GROUP_COMMITS,
    min_group_lines: int = MIN_GROUP_LINES,
) -> dict:
    """Age-matched survival comparison between AI and other commits.

    PURE: no git, no I/O. The mandatory age-matching (honesty rail #2) lives here:
    a month contributes to the overall figures ONLY if it contains at least one
    eligible AI commit AND at least one eligible other commit. Months with a single
    group are excluded — including them would reproduce the naive pooled comparison
    that flatters younger AI lines.

    An eligible commit has ``date >= adoption_dt``, age >= MIN_SURVIVAL_AGE_DAYS,
    and ``lines_added > 0`` (delete-only commits have nothing to survive).
    AI attribution is solely ``commit.sha in ai_shas`` (no per-commit flag).
    """
    eligible: list = []
    for c in commits:
        if c.date < adoption_dt:
            continue
        if (today - c.date).days < MIN_SURVIVAL_AGE_DAYS:
            continue
        if c.lines_added <= 0:
            continue
        eligible.append(c)

    # Bucket eligible commits by (month, group). group ∈ {"ai","other"}.
    # month key: f"{year:04d}-{month:02d}".
    buckets: dict[str, dict[str, list]] = {}
    for c in eligible:
        month = f"{c.date.year:04d}-{c.date.month:02d}"
        group = "ai" if c.sha in ai_shas else "other"
        buckets.setdefault(month, {"ai": [], "other": []})
        buckets[month][group].append(c)

    matched_months = [m for m, g in buckets.items() if g["ai"] and g["other"]]

    def _group_stats(commits_list) -> tuple[int, int, int]:
        added = sum(c.lines_added for c in commits_list)
        surv = sum(surviving_lines.get(c.sha, 0) for c in commits_list)
        return added, surv, len(commits_list)

    coverage = {"ai_commits": 0, "other_commits": 0,
                "ai_lines": 0, "other_lines": 0}
    overall_added = {"ai": 0, "other": 0}
    overall_surv = {"ai": 0, "other": 0}
    overall_commits = {"ai": 0, "other": 0}

    for m in matched_months:
        for g in ("ai", "other"):
            added, surv, cnt = _group_stats(buckets[m][g])
            overall_added[g] += added
            overall_surv[g] += surv
            overall_commits[g] += cnt

    coverage["ai_commits"] = overall_commits["ai"]
    coverage["other_commits"] = overall_commits["other"]
    coverage["ai_lines"] = overall_added["ai"]
    coverage["other_lines"] = overall_added["other"]

    # Floors (honesty rail #4).
    if not matched_months:
        return {"status": "withheld",
                "reason": "no matched months (no month has both AI and other "
                          "eligible commits)",
                "coverage": coverage}
    for g in ("ai", "other"):
        if overall_commits[g] < min_group_commits:
            return {"status": "withheld",
                    "reason": f"{g} group has {overall_commits[g]} committed "
                              f"< min_group_commits={min_group_commits} over "
                              f"matched months",
                    "coverage": coverage}
        if overall_added[g] < min_group_lines:
            return {"status": "withheld",
                    "reason": f"{g} group has {overall_added[g]} added lines "
                              f"< min_group_lines={min_group_lines} over "
                              f"matched months",
                    "coverage": coverage}

    def _surv_rate(g: str) -> float:
        return overall_surv[g] / overall_added[g] if overall_added[g] else 0.0

    bucket_rows = []
    for m in sorted(matched_months):
        ai_added, ai_surv, _ = _group_stats(buckets[m]["ai"])
        ot_added, ot_surv, _ = _group_stats(buckets[m]["other"])
        bucket_rows.append({
            "month": m,
            "ai_survival": ai_surv / ai_added if ai_added else 0.0,
            "other_survival": ot_surv / ot_added if ot_added else 0.0,
            "ai_lines": ai_added,
            "other_lines": ot_added,
        })

    return {
        "status": "scored",
        "ai_survival": _surv_rate("ai"),
        "other_survival": _surv_rate("other"),
        "buckets": bucket_rows,
        "age_floor_days": MIN_SURVIVAL_AGE_DAYS,
        "coverage": coverage,
    }


def compute_survival(
    root: Path,
    commits,
    ai_shas: set[str],
    adoption_dt: date,
    today: date | None = None,
    *,
    max_files: int = MAX_SURVIVAL_FILES,
    max_lines: int = MAX_SURVIVAL_LINES,
) -> dict:
    """Blame-driven survival wrapper around :func:`matched_survival`.

    Enumerates tracked source files, applies a deterministic cap (sorted file list,
    stop after ``max_files`` files or once cumulative surviving lines reach
    ``max_lines``), blames each kept file, merges into one {sha: surviving} dict,
    and delegates to :func:`matched_survival`. Sampling disclosure is added to the
    result regardless of status.
    """
    today = today or date.today()

    source_files = sorted(
        p for p in tracked_files(root) if Path(p).suffix.lower() in _CODE_EXTS
    )
    files_total = len(source_files)

    merged: dict[str, int] = {}
    kept = 0
    cumulative = 0
    sampled = False
    for p in source_files:
        if kept >= max_files:
            sampled = True
            break
        if cumulative >= max_lines:
            sampled = True
            break
        out = blame_incremental(root, p)
        if not out:
            continue
        per_file = parse_incremental_blame(out)
        for sha, n in per_file.items():
            merged[sha] = merged.get(sha, 0) + n
        cumulative += sum(per_file.values())
        kept += 1
    # Cap tripped only if we stopped before consuming every source file.
    if kept < files_total and (kept >= max_files or cumulative >= max_lines):
        sampled = True

    result = matched_survival(commits, merged, ai_shas, adoption_dt, today)
    result["sampled"] = sampled
    result["files_blamed"] = kept
    result["files_total"] = files_total
    return result
