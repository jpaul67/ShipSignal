"""Single source of truth for the explanatory copy shown in reports.

Every self-documenting surface — inline section lines (all formats), HTML hover
tooltips, and the HTML "How to read this" block — pulls from here, so the three
never drift. Each entry has:
  * short — one line: WHAT it measures + WHY it matters (plain text, all formats)
  * tip   — precise definition + how it's computed + thresholds/caveats (HTML tooltip)

Copy is deliberately plain and honest (no causation claims, lower-bound caveats
kept) — consistent with the product's identity.
"""
from __future__ import annotations

GLOSSARY: dict[str, dict[str, str]] = {
    # --- the three headline numbers ---
    "ai_adoption": {
        "short": "The share of commits an AI tool co-authored — the one directly "
                 "measured sign AI is actually being used here, not a survey.",
        "tip": "Counts AI-driven development commits — human commits carrying an AI "
               "Co-Authored-By: trailer (Claude, Copilot, …) PLUS commits authored by an "
               "AI coding-agent bot (gpt-engineer, devin, …) — over all development "
               "commits (maintenance bots like renovate/dependabot excluded). A lower "
               "bound: squash-merges drop trailers. Banded None / Emerging (<10%) / "
               "Established (<50%) / Pervasive (≥50%).",
    },
    "adoption_breadth": {
        "short": "What fraction of active humans on the team have at least one "
                 "AI-coauthored commit — is adoption spreading or stuck with a few "
                 "early adopters? Team-level only, never per person.",
        "tip": "Aggregate: (humans with ≥1 AI commit) ÷ (humans with any commit) in "
               "the window. n/a below 3 active contributors (not meaningful and would "
               "risk de-anonymization). Trend compares first-half vs second-half "
               "breadth (growing/flat/shrinking, ±10pp threshold). HARD non-goal: "
               "ShipSignal does NOT score, rank, or list individual developers — the "
               "function structurally returns only aggregates.",
    },
    "delivery_health": {
        "short": "How sound the team's shipping habits are by general engineering "
                 "norms — deliberately NOT credited to AI. High adoption means little "
                 "if delivery health is poor.",
        "tip": "0–100 from change-size discipline (35), test discipline (35), and "
               "knowledge distribution (30); solo repos drop the last and renormalize. "
               "Scored against general norms, never an AI-causation claim. Withheld "
               "below 20 commits.",
    },
    "readiness": {
        "short": "Whether the repo is set up so an AI agent (or a new human) can "
                 "navigate it and trust what it reads — the conditions that decide "
                 "whether AI adoption actually pays off.",
        "tip": "0–100 static-state score: entry-point README, agent instructions, "
               "module README coverage, setup & convention files, link integrity, and "
               "doc freshness. Renormalizes over whatever applies.",
    },
    "outcomes": {
        "short": "How often changes get reverted or fixed, and how fast — outcome "
                 "signals to complement the habit-based numbers above. Always "
                 "context, never part of any score.",
        "tip": "Revert pairs: a commit whose body matches git's own `git revert` "
               "format (`Revert \"...\"` + `This reverts commit <sha>.`) or an "
               "explicit `Fixes:`/`Reverts:` trailer, matched by sha against the "
               "analyzed commit set — a revert-of-a-revert is just another pair. "
               "Median time-to-correction = revert date − target date, over "
               "matched pairs only; unmatched reverts (target outside the "
               "window) are disclosed, not hidden. n/a below 3 matched pairs. "
               "Not MTTR — this is commit-scoped; production incidents aren't "
               "in git.",
    },
    "change_failure_proxy": {
        "short": "Share of commits whose subject reads as a fix, hotfix, bug, or "
                 "revert — a rough proxy for how often work needed correcting. "
                 "Context only, never scored.",
        "tip": "Subject-only heuristic (revert/fix/hotfix/bugfix/bug). Measures "
               "commit-labeling discipline as much as failure rate: a repo with "
               "honest `fix:` conventions must never score worse than one with "
               "vague messages, so this never feeds Delivery Health.",
    },
    "release_cadence": {
        "short": "How often the repo tags releases, and how long a commit "
                 "waits between landing and its release tag — deploy-frequency "
                 "and lead-time proxies from data already in the clone. Always "
                 "context, never part of any score.",
        "tip": "Tags filtered to release-shaped ones (default `v?N.N[.N]`, "
               "overridable via `.shipsignal.toml`'s `release_tag_pattern` for "
               "monorepo tags like `pkg@1.2.3`). Cadence = tags/month + median "
               "gap between tags, over the trailing 12 months (falls back to "
               "the full tag history when sparse — the window used is "
               "disclosed). Lead time = median(release-tag date − commit date) "
               "over every commit in each consecutive tag pair. n/a below 3 "
               "matched tags. Tags are NOT deploys — a service can deploy "
               "without tagging, so an untagged repo is never penalized, only "
               "shown n/a.",
    },
    # --- conditional / over-time ---
    "before_after": {
        "short": "When a clean pre-AI baseline exists, how delivery metrics shifted "
                 "after adoption — shown as context, never proof AI caused the change.",
        "tip": "Computed only with a real adoption transition: ≥50 commits, ≥6 weeks, "
               "≥20 commits each side, and a post-adoption window ≥6 weeks. Pillars "
               "score improvement vs the pre-adoption baseline. Withheld (not zero) "
               "when unearned.",
    },
    "trajectory": {
        "short": "How AI adoption and delivery health moved over the repo's history — "
                 "two parallel timelines, correlation only, never proof one caused the "
                 "other.",
        "tip": "Commits bucketed into ~8–14 time periods; each shows adoption % and a "
               "delivery-health score. Quiet or thin periods are shown as gaps, never "
               "zero-filled. Needs ≥40 commits and ≥8 weeks.",
    },
    # --- delivery-health components ---
    "change_size_discipline": {
        "short": "Small, frequent commits (safe to review, test, revert) vs large "
                 "risky ones.",
        "tip": "From median lines and files per commit and the rate of large "
               "(≥400-line) changes. Smaller is healthier. Weight 35.",
    },
    "test_discipline": {
        "short": "How often commits that touch code also touch tests — low means "
                 "changes shipping without coverage.",
        "tip": "Ratio of commits touching test paths to commits touching code. Flagged "
               "below 15%. n/a if no code-touching commits. Weight 35.",
    },
    "knowledge_distribution": {
        "short": "Whether knowledge is spread across the team or concentrated in one "
                 "person (key-person / bus-factor risk).",
        "tip": "From top-author commit share and bus-factor (authors covering ≥50% of "
               "commits). Flagged when one author dominates. n/a for solo repos. "
               "Weight 30.",
    },
    # --- readiness categories ---
    "entry_point": {
        "short": "A substantial root README — the first thing an agent or newcomer reads.",
        "tip": "Checks for a root README with real content. Missing costs the whole "
               "category (20 pts) but does not cap the grade.",
    },
    "agent_instructions": {
        "short": "An agent guide (AGENTS.md / CLAUDE.md / .cursor/rules / "
                 ".cursorrules / .windsurfrules / .clinerules / copilot-instructions) "
                 "that tells tools how to build, test, orient, or follow conventions.",
        "tip": "Root or nested agent files, size-scaled (optional on very small repos) "
               "and depth-graded on three vendor-neutral signals: build/test "
               "**commands**, **structure** pointer (architecture / where things live), "
               "and **rules** / conventions (always-never style guidance — what a "
               ".cursorrules / .windsurfrules file legitimately carries instead of "
               "markdown headings). 2-of-3 signals = full credit; 1-of-3 = partial; "
               "0 = thin. Heuristic, disclosed as such. 15 pts.",
    },
    "module_coverage": {
        "short": "Each detected module/package has a README, so an agent can orient "
                 "within subtrees.",
        "tip": "% of detected (non-waived) modules with a README. Ecosystem-aware "
               "detection (npm/pnpm/Cargo workspaces, then directory fallback). 20 pts.",
    },
    "setup_tooling": {
        "short": "The practical files an agent needs to actually work: discoverable "
                 "test command, CI, deps, lint/type config, conventions, license, "
                 "and (on multi-module repos) an architecture overview.",
        "tip": "Weighted checklist: test command, CI, dependency manifest + lockfile, "
               "lint/format/type config, .editorconfig, CONTRIBUTING, LICENSE, "
               "architecture doc (expected on repos with ≥4 modules), and MCP "
               "path-resolution when present. 20 pts.",
    },
    "doc_integrity": {
        "short": "Documentation links actually resolve — no dead pointers an agent "
                 "will chase.",
        "tip": "Proportional to the share of markdown links that resolve, with "
               "false-positive guards (skips http/anchors/doc-site routes). 13 pts.",
    },
    "doc_freshness": {
        "short": "Docs haven't drifted behind the code they describe, and aren't "
                 "obviously desynced (dead references, predates new modules, "
                 "never-revised across hundreds of commits).",
        "tip": "Per-doc graded drift: full credit when fresh, less as the lag past "
               "the staleness threshold (180d strict / 365d gentle for agent files) "
               "grows — 0–3mo past = 85%, 3–6mo = 50%, 6–12mo = 20%, 12mo+ = 0%. "
               "Also surfaces (as fixes, not score) referenced-but-missing paths, "
               "agent files that predate later modules, and any living doc — module "
               "READMEs, agent files, or standalone markdown (CHANGELOG, docs/…) — "
               "left untouched while ≥100 commits landed after it. Never flags age "
               "alone. Needs git history. 12 pts.",
    },
}

# Display names + order for the HTML "How to read this" block.
HOWTO_ORDER = [
    ("AI Adoption", "ai_adoption"),
    ("Delivery Health", "delivery_health"),
    ("Outcomes", "outcomes"),
    ("Release cadence", "release_cadence"),
    ("Readiness", "readiness"),
    ("Before/after AI Enablement", "before_after"),
    ("Trajectory", "trajectory"),
]


def short(key: str) -> str:
    return GLOSSARY.get(key, {}).get("short", "")


def tip(key: str) -> str:
    return GLOSSARY.get(key, {}).get("tip", "")
