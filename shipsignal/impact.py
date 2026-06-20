"""Impact lens — read-only git-history analytics.

Honest by construction:
  * AI adoption is a DIRECT, measured signal (the `Co-Authored-By:` trailer
    matched against a small known-AI registry). It is reported as a *lower
    bound* because squash-merges drop trailers.
  * Delivery metrics (flow, change shape, quality, people) are GENERAL health.
    They are context, never causal evidence — see the attribution caveat that
    accompanies every report.
  * Confidence GATES the Enablement Score (it is withheld when history is too
    thin), and a repo with AI present from inception has `no_baseline=True`
    and is shown as a current-state profile, not a before/after.

No diff or prompt content is ever read — only metadata (dates, sizes, paths,
trailers). The lens is fully deterministic at a given commit SHA.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import gitinfo
from .scoring import grade_for

SCHEMA_VERSION = "impact-0.2"

# ---------------------------------------------------------------------------
# Known-AI registry — versioned constant (extend deliberately).
# A trailer is "AI" iff it is a `Co-Authored-By:` line whose value matches one
# of these tokens (case-insensitive substring match).
# ---------------------------------------------------------------------------
AI_TOOL_ALIASES: dict[str, str] = {
    "claude": "Claude",
    "anthropic": "Claude",
    "copilot": "Copilot",
    "cursor": "Cursor",
    "codeium": "Codeium",
    "gemini": "Gemini",
    "chatgpt": "GPT/ChatGPT",
    "gpt-": "GPT/ChatGPT",
    "aider": "Aider",
    "devin": "Devin",
    "cody": "Cody",
}

# ---------------------------------------------------------------------------
# Subject + path heuristics.
# ---------------------------------------------------------------------------
_FIX_RE = re.compile(
    r"^\s*(?:revert|fix|hotfix|bugfix|bug)(?:[\s(:!\-]|$)",
    re.IGNORECASE,
)
_TEST_PATH_RE = re.compile(
    r"(?:^|/)(?:tests?|__tests__|specs?)(?:/|$)|"
    r"(?:^|/)[^/]+[._-](?:test|spec)\.[a-z0-9]+$",
    re.IGNORECASE,
)
# Bot authors — excluded so cadence, change-shape, contributors, and the adoption
# denominator reflect HUMAN work (renovate alone is vitest's single biggest
# "contributor"; counting it distorts every people/flow metric). Matches the
# canonical `[bot]` marker in GitHub noreply emails plus common named bots.
_BOT_RE = re.compile(
    r"\[bot\]|(?:^|[^a-z])(?:dependabot|renovate|greenkeeper|snyk-bot|github-actions|"
    r"mergify|allcontributors|semantic-release-bot|imgbot|pyup-bot|codecov)(?:[^a-z]|$)",
    re.IGNORECASE,
)
_CODE_EXTS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".rs", ".go", ".java", ".kt", ".swift",
    ".c", ".cc", ".cpp", ".h", ".hpp",
    ".cs", ".rb", ".php", ".scala", ".m", ".mm",
}

# Confidence-gate defaults for the (conditional) before/after Enablement delta.
MIN_COMMITS_FOR_SCORE = 50
MIN_WEEKS_FOR_SCORE = 6
MIN_BASELINE_COMMITS = 20
MIN_CURRENT_COMMITS = 20
# The post-adoption window must also span enough TIME, not just enough commits —
# 20 commits crammed into a 3-week tail is a burst, not a trend, and produces a
# noisy before/after that invites the exact "AI made it worse" misread the
# attribution caveat warns against. (Found calibrating juglr-next-step: a 3.1-week
# tail scored a misleading 16/100.)
MIN_CURRENT_WEEKS = 6

# Delivery-health (snapshot) needs far less — just enough to not be pure noise.
MIN_COMMITS_FOR_HEALTH = 20

# Adoption auto-detect defaults.
ADOPTION_RATE_THRESHOLD = 0.25
ADOPTION_SUSTAINED_WEEKS = 2

# Baseline window (weeks before the adoption date).
BASELINE_WEEKS = 8


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
@dataclass
class Commit:
    sha: str
    date: date
    email: str
    subject: str
    trailers: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    lines_added: int = 0
    lines_deleted: int = 0

    @property
    def total_lines(self) -> int:
        return self.lines_added + self.lines_deleted

    @property
    def ai_authored(self) -> bool:
        for t in self.trailers:
            low = t.lower()
            if not low.startswith("co-authored-by:"):
                continue
            if any(kw in low for kw in AI_TOOL_ALIASES):
                return True
        return False

    @property
    def ai_tools(self) -> set[str]:
        out: set[str] = set()
        for t in self.trailers:
            low = t.lower()
            if not low.startswith("co-authored-by:"):
                continue
            for kw, label in AI_TOOL_ALIASES.items():
                if kw in low:
                    out.add(label)
        return out

    @property
    def is_bot(self) -> bool:
        return bool(_BOT_RE.search(self.email))

    @property
    def is_fix(self) -> bool:
        return bool(_FIX_RE.match(self.subject))

    @property
    def touches_tests(self) -> bool:
        return any(_TEST_PATH_RE.search(p) for p in self.files)

    @property
    def touches_code(self) -> bool:
        for p in self.files:
            if _TEST_PATH_RE.search(p):
                continue
            if Path(p).suffix.lower() in _CODE_EXTS:
                return True
        return False


# ---------------------------------------------------------------------------
# History walker — one `git log --numstat` pass.
# Format: __BWREC__<hash>\x1f<aI>\x1f<email>\x1f<subject>\x1f<trailers>\n\n<numstat>
# ---------------------------------------------------------------------------
_REC = "__BWREC__"
_FMT = f"{_REC}%H%x1f%aI%x1f%ae%x1f%s%x1f%(trailers:only,unfold)"


def walk_history(root: Path, timeout: int = 600) -> list[Commit]:
    """Return commits newest-first. Empty list for a non-git or empty repo.

    Default 10-minute timeout covers very large OSS histories (vitest, express,
    linux-sized). The readiness lens keeps the lower default — a single git log
    --numstat pass on a 6000-commit treeless clone is the slowest thing we do.
    """
    # --no-merges: merge commits carry no diff under --numstat, so they'd add
    # zero-line entries that dilute change-shape and inflate the commit count
    # (express is ~8% merges). Analyze actual change commits only.
    out = gitinfo._run(
        ["git", "log", "--no-merges", "--numstat", f"--format={_FMT}"], root, timeout=timeout
    )
    if not out:
        return []
    commits: list[Commit] = []
    for chunk in out.split(_REC)[1:]:
        header, _, body = chunk.partition("\n\n")
        try:
            sha, date_iso, email, subject, trailers_blob = header.split("\x1f", 4)
        except ValueError:
            continue
        try:
            d = datetime.fromisoformat(date_iso).date()
        except ValueError:
            continue
        trailers = [ln.strip() for ln in trailers_blob.splitlines() if ln.strip()]
        files: list[str] = []
        adds = dels = 0
        for ln in body.splitlines():
            if not ln.strip():
                continue
            parts = ln.split("\t")
            if len(parts) != 3:
                continue
            a, b, path = parts
            files.append(path)
            try:
                adds += int(a)
                dels += int(b)
            except ValueError:
                pass  # binary files show as "-\t-\tpath"
        commits.append(Commit(sha, d, email, subject.strip(), trailers, files, adds, dels))
    return commits


# ---------------------------------------------------------------------------
# Adoption detection (AI signal)
# ---------------------------------------------------------------------------
def _week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _by_week(commits: list[Commit]) -> dict[date, list[Commit]]:
    buckets: dict[date, list[Commit]] = defaultdict(list)
    for c in commits:
        buckets[_week_start(c.date)].append(c)
    return buckets


def detect_adoption_date(
    commits: list[Commit],
    threshold: float = ADOPTION_RATE_THRESHOLD,
    sustained_weeks: int = ADOPTION_SUSTAINED_WEEKS,
) -> date | None:
    """First Monday of a sustained window where AI-trailer rate >= threshold."""
    if not commits:
        return None
    buckets = _by_week(commits)
    weeks = sorted(buckets.keys())
    if not weeks:
        return None
    rates = {
        w: sum(1 for c in buckets[w] if c.ai_authored) / len(buckets[w])
        for w in weeks
    }
    for i, w in enumerate(weeks):
        window = weeks[i : i + sustained_weeks]
        if len(window) < sustained_weeks:
            break
        if all(rates[ww] >= threshold for ww in window):
            return w
    return None


def _per_tool_counts(commits: list[Commit]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for c in commits:
        for tool in c.ai_tools:
            counts[tool] += 1
    return dict(counts.most_common())


def _weekly_ai_series(commits: list[Commit]) -> list[tuple[str, float, int]]:
    """[(week_iso, ai_rate, commit_count)] oldest-first — for sparklines."""
    if not commits:
        return []
    buckets = _by_week(commits)
    weeks = sorted(buckets.keys())
    return [
        (
            w.isoformat(),
            round(sum(1 for c in buckets[w] if c.ai_authored) / len(buckets[w]), 3),
            len(buckets[w]),
        )
        for w in weeks
    ]


# ---------------------------------------------------------------------------
# Delivery metrics — proxies, labelled honestly.
# ---------------------------------------------------------------------------
def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round((pct / 100) * (len(s) - 1)))))
    return s[k]


def flow_metrics(commits: list[Commit]) -> dict:
    if not commits:
        return {"commits": 0}
    dates = [c.date for c in commits]
    span_days = max(1, (max(dates) - min(dates)).days + 1)
    active_days = len({c.date for c in commits})
    return {
        "commits": len(commits),
        "span_days": span_days,
        "active_day_ratio": round(active_days / span_days, 3),
        "commits_per_week": round(len(commits) / (span_days / 7), 2),
    }


def change_shape_metrics(commits: list[Commit]) -> dict:
    if not commits:
        return {"median_lines": 0, "p90_lines": 0, "large_change_rate": 0.0}
    sizes = [c.total_lines for c in commits]
    files_per = [len(c.files) for c in commits]
    large = sum(1 for s in sizes if s >= 400)  # > 400 lines is a "large change" proxy
    return {
        "median_lines": int(_percentile(sizes, 50)),
        "p90_lines": int(_percentile(sizes, 90)),
        "median_files": int(_percentile(files_per, 50)),
        "large_change_rate": round(large / len(commits), 3),
    }


def quality_metrics(commits: list[Commit]) -> dict:
    if not commits:
        return {"fix_rate": 0.0, "test_to_code_ratio": 0.0}
    fixes = sum(1 for c in commits if c.is_fix)
    code = sum(1 for c in commits if c.touches_code)
    tests = sum(1 for c in commits if c.touches_tests)
    return {
        "fix_rate": round(fixes / len(commits), 3),
        "fix_commits": fixes,
        "test_to_code_ratio": round(tests / code, 3) if code else None,
        "test_touch_commits": tests,
        "code_touch_commits": code,
    }


def people_metrics(commits: list[Commit]) -> dict:
    if not commits:
        return {"contributors": 0, "solo": True}
    by_author: Counter[str] = Counter(c.email for c in commits)
    total = sum(by_author.values())
    top_share = max(by_author.values()) / total
    # bus-factor: smallest set of authors covering >= 50% of commits.
    bus = 0
    running = 0
    for _, count in by_author.most_common():
        bus += 1
        running += count
        if running >= total / 2:
            break
    return {
        "contributors": len(by_author),
        "solo": len(by_author) == 1,
        "top_author_share": round(top_share, 3),
        "bus_factor": bus,
    }


# ---------------------------------------------------------------------------
# AI adoption LEVEL — always computable, never withheld.
# A direct measurement of uptake, banded for at-a-glance reading. This is the
# one AI-specific number the tool always stands behind (a lower bound).
# ---------------------------------------------------------------------------
def adoption_level(share: float) -> str:
    if share <= 0:
        return "None"
    if share < 0.10:
        return "Emerging"      # ambient / individual use
    if share < 0.50:
        return "Established"   # a meaningful share of work
    return "Pervasive"         # the default way the team ships


# ---------------------------------------------------------------------------
# Delivery HEALTH — a current-state snapshot scored against GENERAL engineering
# norms. NOT a before/after, NOT AI-attributed. Always available (above a small
# sample floor), so a scan is never empty.
#
# Which signals are scored vs merely described was decided from real calibration
# (chalk / vitest / crown): change-size discipline, test discipline, and (for
# teams) knowledge distribution separate healthy from unhealthy cleanly. Fix-rate
# and cadence do NOT (vitest's 34% fix-rate and crown's 26% don't rank by health;
# a mature lib's low cadence isn't ill health) — so those stay descriptive.
# Weights are v0.1 and tunable as more repos calibrate.
# ---------------------------------------------------------------------------
def _band(value: float, points: list[tuple[float, float]], lower_is_better: bool) -> float:
    """Piecewise-linear score in [0,1]. ``points`` = [(threshold, score)] ascending
    by threshold; interpolates between, clamps outside."""
    if lower_is_better:
        if value <= points[0][0]:
            return points[0][1]
        if value >= points[-1][0]:
            return points[-1][1]
    else:
        if value <= points[0][0]:
            return points[0][1]
        if value >= points[-1][0]:
            return points[-1][1]
    for (t0, s0), (t1, s1) in zip(points, points[1:]):
        if t0 <= value <= t1:
            frac = (value - t0) / (t1 - t0) if t1 != t0 else 0
            return s0 + frac * (s1 - s0)
    return points[-1][1]


def _change_size_subscore(cs: dict) -> float:
    # Small, frequent commits = healthy (trunk-based / DORA wisdom).
    median = _band(cs["median_lines"],
                   [(50, 1.0), (150, 0.5), (400, 0.2), (1000, 0.1)], lower_is_better=True)
    large = _band(cs["large_change_rate"],
                  [(0.05, 1.0), (0.15, 0.6), (0.30, 0.3), (0.60, 0.1)], lower_is_better=True)
    return 0.6 * median + 0.4 * large


def _test_subscore(ratio: float) -> float:
    return _band(ratio,
                 [(0.03, 0.10), (0.08, 0.25), (0.15, 0.45),
                  (0.25, 0.65), (0.40, 0.90), (0.60, 1.0)], lower_is_better=False)


def _knowledge_subscore(people: dict) -> float:
    # Lower author concentration + higher bus-factor = less key-person risk.
    conc = _band(people["top_author_share"],
                 [(0.30, 1.0), (0.50, 0.6), (0.70, 0.35), (0.90, 0.15)], lower_is_better=True)
    if people["bus_factor"] >= 3:
        conc = max(conc, 0.7)  # several people share the load — floor it up
    return conc


def delivery_health(commits: list[Commit], metrics: dict,
                    min_commits: int = MIN_COMMITS_FOR_HEALTH) -> dict:
    # min_commits is looser for per-period trajectory buckets (trend > any one point).
    if len(commits) < min_commits:
        return {"status": "insufficient", "score": None, "grade": None,
                "reason": f"only {len(commits)} commits (need {min_commits} "
                          "for a delivery-health snapshot)",
                "components": [], "descriptive": {}}

    cs, q, p = metrics["change_shape"], metrics["quality"], metrics["people"]
    components: list[dict] = []

    cs_frac = _change_size_subscore(cs)
    components.append({"id": "change_size_discipline", "weight": 35,
                       "score_frac": round(cs_frac, 3), "status": "scored",
                       "flag": "large commits" if cs_frac < 0.5 else None})

    t2c = q["test_to_code_ratio"]
    if t2c is None:
        components.append({"id": "test_discipline", "weight": 35, "score_frac": None,
                           "status": "n/a", "flag": None})
    else:
        t_frac = _test_subscore(t2c)
        components.append({"id": "test_discipline", "weight": 35,
                           "score_frac": round(t_frac, 3), "status": "scored",
                           "flag": "low test discipline" if t2c < 0.15 else None})

    if p["solo"]:
        components.append({"id": "knowledge_distribution", "weight": 30, "score_frac": None,
                           "status": "n/a (solo author)", "flag": None})
    else:
        k_frac = _knowledge_subscore(p)
        concentrated = p["top_author_share"] > 0.50 or p["bus_factor"] == 1
        components.append({"id": "knowledge_distribution", "weight": 30,
                           "score_frac": round(k_frac, 3), "status": "scored",
                           "flag": "concentration risk" if concentrated else None})

    scored = [c for c in components if c["score_frac"] is not None]
    denom = sum(c["weight"] for c in scored)
    num = sum(c["weight"] * c["score_frac"] for c in scored)
    score = round(100 * num / denom) if denom else None

    return {
        "status": "scored",
        "score": score,
        "grade": grade_for(score) if score is not None else None,
        "components": components,
        "descriptive": {  # shown, never scored — too noisy to rank health by
            "fix_revert_rate": q["fix_rate"],
            "commits_per_week": metrics["flow"]["commits_per_week"],
            "active_day_ratio": metrics["flow"]["active_day_ratio"],
            "contributors": p["contributors"],
        },
    }


# ---------------------------------------------------------------------------
# Confidence gate
# ---------------------------------------------------------------------------
@dataclass
class Confidence:
    sufficient_for_score: bool
    reasons: list[str]

    def as_dict(self) -> dict:
        return {"sufficient": self.sufficient_for_score, "reasons": self.reasons}


def assess_confidence(commits: list[Commit]) -> Confidence:
    reasons: list[str] = []
    if len(commits) < MIN_COMMITS_FOR_SCORE:
        reasons.append(f"only {len(commits)} commits (need {MIN_COMMITS_FOR_SCORE})")
    if commits:
        span = (max(c.date for c in commits) - min(c.date for c in commits)).days
        weeks = span / 7
        if weeks < MIN_WEEKS_FOR_SCORE:
            reasons.append(f"only {weeks:.1f} weeks of history (need {MIN_WEEKS_FOR_SCORE})")
    return Confidence(sufficient_for_score=not reasons, reasons=reasons)


# ---------------------------------------------------------------------------
# Pillar scoring (only when earned: confidence sufficient AND baseline exists).
# ---------------------------------------------------------------------------
def _direction_score(current: float, baseline: float, lower_is_better: bool,
                     target_gap: float = 0.30) -> float:
    """Improvement vs baseline as a fraction in [-1, 1]. Closes target_gap% of the gap.

    Returns 0 when current == baseline; +1 when fully closing the target gap in the
    right direction; -1 when regressing by the same magnitude.
    """
    if baseline == 0:
        return 0.0
    delta = (baseline - current) / baseline if lower_is_better else (current - baseline) / baseline
    # Cap so a wild swing on a noisy small base doesn't dominate.
    return max(-1.0, min(1.0, delta / target_gap))


def _pillar_pts(max_pts: float, improvement_frac: float) -> float:
    """Map improvement [-1, +1] -> pts [0, max] with neutral = 0.5 * max."""
    return round(max_pts * (0.5 + 0.5 * improvement_frac), 1)


def _flow_score(baseline: list[Commit], current: list[Commit]) -> float:
    b = flow_metrics(baseline)["commits_per_week"]
    c = flow_metrics(current)["commits_per_week"]
    # Cadence is a directional proxy — higher = more flow. Cap.
    return _pillar_pts(25, _direction_score(c, b, lower_is_better=False))


def _quality_score(baseline: list[Commit], current: list[Commit]) -> float:
    b = quality_metrics(baseline)["fix_rate"]
    c = quality_metrics(current)["fix_rate"]
    return _pillar_pts(20, _direction_score(c, b, lower_is_better=True))


def _risk_score(baseline: list[Commit], current: list[Commit]) -> float:
    b = change_shape_metrics(baseline)["large_change_rate"]
    c = change_shape_metrics(current)["large_change_rate"]
    return _pillar_pts(20, _direction_score(c, b, lower_is_better=True))


def baseline_gate(n_baseline: int, n_current: int, current_weeks: float) -> tuple[bool, str | None]:
    """Decide whether a before/after delta is earnable. Returns (ok, reason_if_not).

    Two hurdles: enough commits on BOTH sides, and a post-adoption window that
    spans enough TIME (so a short commit burst can't masquerade as a trend).
    """
    if n_baseline < MIN_BASELINE_COMMITS or n_current < MIN_CURRENT_COMMITS:
        return False, (f"baseline {n_baseline}c / current {n_current}c — "
                       f"need {MIN_BASELINE_COMMITS} each")
    if current_weeks < MIN_CURRENT_WEEKS:
        return False, (f"post-adoption window is only {current_weeks:.1f} weeks "
                       f"(need {MIN_CURRENT_WEEKS}) — too short to be a trend, not a burst")
    return True, None


def compute_pillars(baseline: list[Commit], current: list[Commit],
                    readiness_score: int | None = None) -> list[dict]:
    pillars: list[dict] = [
        {"id": "faster_flow", "max": 25, "pts": _flow_score(baseline, current),
         "basis": "commits/week (proxy for cadence)"},
        {"id": "better_quality", "max": 20, "pts": _quality_score(baseline, current),
         "basis": "fix/revert subject rate"},
        {"id": "knowledge_capture", "max": 20, "pts": None, "status": "indeterminate",
         "basis": "needs Phase B trajectory data"},
        {"id": "risk_control", "max": 20, "pts": _risk_score(baseline, current),
         "basis": "large-change rate (>400 lines)"},
    ]
    if readiness_score is not None:
        pillars.append({"id": "agent_readiness", "max": 15,
                        "pts": round(15 * readiness_score / 100, 1),
                        "basis": "Readiness lens score"})
    else:
        pillars.append({"id": "agent_readiness", "max": 15, "pts": None,
                        "status": "n/a", "basis": "no readiness score supplied"})
    return pillars


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
ATTRIBUTION_CAVEAT = (
    "Delivery pillars (flow, quality, risk) measure GENERAL delivery health — "
    "only AI-adoption and readiness are AI-specific. A delivery change may come "
    "from hiring, a finished migration, or a calmer quarter. The score asks "
    "whether the conditions under which AI pays off are improving — it does NOT "
    "prove AI caused any change."
)


def compute_impact(
    root: Path,
    repo_label: str | None = None,
    adoption_date_override: str | None = None,
    readiness_score: int | None = None,
) -> dict:
    result: dict = {
        "schema_version": SCHEMA_VERSION,
        "repo": repo_label or root.name,
        "commit_sha": None,
        "scanned_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "attribution_caveat": ATTRIBUTION_CAVEAT,
    }

    if not gitinfo.is_git_repo(root):
        result["error"] = "not a git repository"
        return result

    all_commits = walk_history(root)  # newest-first, merges already excluded
    if not all_commits:
        # Distinguish a truly empty repo from a failed/timed-out git log
        # (the latter happens on huge treeless clones where --numstat is slow).
        rev_count_raw = gitinfo._run(["git", "rev-list", "--count", "HEAD"], root)
        try:
            n = int(rev_count_raw.strip()) if rev_count_raw else 0
        except ValueError:
            n = 0
        if n > 0:
            result["error"] = (
                f"git log --numstat failed or timed out — repo has {n} commits but the "
                "history walk did not complete. On treeless clones (--filter=blob:none), "
                "--numstat may need to fetch blobs on demand and slow drastically on huge "
                "histories. Try cloning with full blobs."
            )
        else:
            result["error"] = "no commit history"
        return result

    # Analyze HUMAN, non-merge commits only. Bots (renovate/dependabot/CI) aren't
    # team delivery and distort cadence, change-shape, contributors, and the
    # adoption denominator. Merges were already dropped in walk_history.
    bots = [c for c in all_commits if c.is_bot]
    commits = [c for c in all_commits if not c.is_bot]
    if not commits:
        result["error"] = "no human commits to analyze (all commits are bots/merges)"
        return result

    total_with_merges_raw = gitinfo._run(["git", "rev-list", "--count", "HEAD"], root)
    try:
        total_with_merges = int(total_with_merges_raw.strip()) if total_with_merges_raw else 0
    except ValueError:
        total_with_merges = 0
    result["analysis"] = {
        "commits_analyzed": len(commits),
        "merges_excluded": max(0, total_with_merges - len(all_commits)),
        "bot_commits_excluded": len(bots),
    }

    result["commit_sha"] = gitinfo.head_sha(root)
    first_date = min(c.date for c in commits)
    last_date = max(c.date for c in commits)
    result["window"] = {
        "first_commit": first_date.isoformat(),
        "last_commit": last_date.isoformat(),
        "weeks": round(((last_date - first_date).days + 1) / 7, 1),
    }

    # --- AI adoption signal (DIRECT) ---
    adoption_dt = (
        date.fromisoformat(adoption_date_override) if adoption_date_override
        else detect_adoption_date(commits)
    )
    ai_count = sum(1 for c in commits if c.ai_authored)
    share = round(ai_count / len(commits), 3)
    result["adoption"] = {
        "ai_coauthor_share": share,
        "level": adoption_level(share),
        "ai_commits": ai_count,
        "total_commits": len(commits),
        "adoption_date": adoption_dt.isoformat() if adoption_dt else None,
        "adoption_auto_detected": adoption_date_override is None,
        "per_tool": _per_tool_counts(commits),
        "weekly_series": _weekly_ai_series(commits),
        "note": "Lower bound — squash-merges drop trailers; gh PR data could recover them.",
    }

    # --- Delivery metrics (general health, NOT causal) ---
    result["metrics"] = {
        "flow": flow_metrics(commits),
        "change_shape": change_shape_metrics(commits),
        "quality": quality_metrics(commits),
        "people": people_metrics(commits),
    }

    # --- The three always-on headline numbers ---
    # 1) AI adoption level (above), 2) delivery-health snapshot, 3) readiness.
    result["delivery_health"] = delivery_health(commits, result["metrics"])
    result["readiness"] = (
        {"score": readiness_score, "grade": grade_for(readiness_score)}
        if readiness_score is not None else None
    )

    # --- Over-time trajectory (adoption + delivery health per period) ---
    # Local import avoids a module-load cycle (timeline imports impact).
    from .timeline import build_trajectory
    result["trajectory"] = build_trajectory(commits)

    # --- Confidence + no-baseline detection ---
    conf = assess_confidence(commits)
    result["confidence"] = conf.as_dict()

    no_baseline = adoption_dt is None or adoption_dt <= first_date
    result["no_baseline"] = no_baseline
    if no_baseline:
        result["no_baseline_reason"] = (
            "no adoption date found" if adoption_dt is None
            else "AI adoption is at or before repo inception — no pre-AI window to compare"
        )

    # --- Enablement Score (withheld unless earned) ---
    score: int | None = None
    pillars: list[dict] = []
    score_status = "withheld"
    score_reason: str | None = None

    if not conf.sufficient_for_score:
        score_reason = "; ".join(conf.reasons)
    elif no_baseline:
        score_reason = result["no_baseline_reason"]
    else:
        baseline_start = adoption_dt - timedelta(weeks=BASELINE_WEEKS)
        baseline = [c for c in commits if baseline_start <= c.date < adoption_dt]
        current = [c for c in commits if c.date >= adoption_dt]
        current_weeks = (last_date - adoption_dt).days / 7
        ok, reason = baseline_gate(len(baseline), len(current), current_weeks)
        if not ok:
            score_reason = reason
        else:
            pillars = compute_pillars(baseline, current, readiness_score)
            scored = [p for p in pillars if p.get("pts") is not None]
            score = round(sum(p["pts"] for p in scored))
            score_status = "scored"
            result["window"]["baseline_start"] = baseline_start.isoformat()
            result["window"]["adoption_date"] = adoption_dt.isoformat()
            result["window"]["baseline_commits"] = len(baseline)
            result["window"]["current_commits"] = len(current)
            result["window"]["current_weeks"] = round(current_weeks, 1)

    result["score"] = score
    result["score_status"] = score_status
    if score_reason:
        result["score_withheld_reason"] = score_reason
    result["pillars"] = pillars

    return result
