# ShipSignal — AI impact: jest

**2014-05-14 → 2026-06-24 · 632.1 weeks · 7248 dev commits** *(excluded 259 merges + 166 maintenance-bot commits)*

| | Result | |
|---|---|---|
| **AI Adoption** | None · 0% → Emerging 0.2% recovered | Claude 1, Cody 1 |
| **Delivery Health** | 96/100 · A | general eng norms, not AI-attributed |
| **Readiness** | — | static repo state |

## How to read this

- **AI Adoption** — The share of commits an AI tool co-authored — the one directly measured sign AI is actually being used here, not a survey.
- **Delivery Health** — How sound the team's shipping habits are by general engineering norms — deliberately NOT credited to AI. High adoption means little if delivery health is poor.
- **Outcomes** — How often changes get reverted or fixed, and how fast — outcome signals to complement the habit-based numbers above. Always context, never part of any score.
- **Release cadence** — How often the repo tags releases, and how long a commit waits between landing and its release tag — deploy-frequency and lead-time proxies from data already in the clone. Always context, never part of any score.
- **Readiness** — Whether the repo is set up so an AI agent (or a new human) can navigate it and trust what it reads — the conditions that decide whether AI adoption actually pays off.
- **Before/after AI Enablement** — When a clean pre-AI baseline exists, how delivery metrics shifted after adoption — shown as context, never proof AI caused the change.
- **Trajectory** — How AI adoption and delivery health moved over the repo's history — two parallel timelines, correlation only, never proof one caused the other.

## AI adoption (direct, in-repo signal)

- **None — 0.0%** (2/7248 commits), a **lower bound** (some squash/merge pipelines strip trailers; GitHub-native squash keeps them).
- **Recovery:** recovered Emerging 0.2% from PR data — +9 squash commit(s) re-attributed (Claude, Cody, Copilot, Cursor); measured 0% · 4782/5429 matched · coverage 88% — partial export, so the recovered figure is itself a lower bound.
- Per tool: `Claude` (1), `Cody` (1)
- **Breadth:** 0% — 2 of 1766 active contributors · trend: **flat**.  
  *Team-level only — ShipSignal does not score individuals.*

## Delivery Health (general engineering norms — NOT AI-attributed)

**96/100 · grade A**

| Component | Score | Weight | Flag |
|---|---|---|---|
| change_size_discipline | 90% | 35 |  |
| test_discipline | 100% | 35 |  |
| knowledge_distribution | 100% | 30 |  |

*Context (not scored — too noisy to rank health by): 11.47 commits/wk, 1766 contributors.*

## Outcomes (context — never scored)

- **Revert pairs:** 27 · median time-to-correction **0d** (19 unmatched)
- **Change-failure proxy:** 16% (1180 commits)

_<sub>How often changes get reverted or fixed, and how fast — outcome signals to complement the habit-based numbers above. Always context, never part of any score.</sub>_

## Release cadence & lead time (context — never scored)

- **Cadence:** 1.35 tags/mo · median gap **5.6d** (trailing 12 months, 252 tags)
- **Lead time:** median **13.3d** (7421 commits)

_<sub>How often the repo tags releases, and how long a commit waits between landing and its release tag — deploy-frequency and lead-time proxies from data already in the clone. Always context, never part of any score.</sub>_

## Trajectory — over time *(parallel timelines, NOT a causal link)*

*14 periods, ~317d each.*

| Period | Commits | Adoption | Health |
|---|---|---|---|
| 2014-05-14 | 224 | 0% | 92 |
| 2015-03-27 | 343 | 0% | 88 |
| 2016-02-07 | 852 | 0% | 93 |
| 2016-12-20 | 1098 | 0% | 97 |
| 2017-11-02 | 845 | 0% | 99 |
| 2018-09-15 | 757 | 0% | 95 |
| 2019-07-29 | 531 | 0% | 84 |
| 2020-06-10 | 480 | 0% | 81 |
| 2021-04-23 | 608 | 0% | 81 |
| 2022-03-06 | 634 | 0% | 88 |
| 2023-01-17 | 349 | 0% | 87 |
| 2023-11-30 | 182 | 0% | 88 |
| 2024-10-12 | 163 | 0% | 95 |
| 2025-08-25 | 182 | 0% | 85 |

## Before/after AI Enablement (bonus — needs a clean pre-AI baseline)

*n/a — no adoption date found. The three numbers above stand on their own.*

## Attribution caveat

> Delivery pillars (flow, quality, risk) measure GENERAL delivery health — only AI-adoption and readiness are AI-specific. A delivery change may come from hiring, a finished migration, or a calmer quarter. The score asks whether the conditions under which AI pays off are improving — it does NOT prove AI caused any change.

<sub>shipsignal v0.9.0 · 2026-07-18T21:14:37Z</sub>
