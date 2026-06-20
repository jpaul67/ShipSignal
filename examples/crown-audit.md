# ShipSignal — AI impact: crown

**2026-02-05 → 2026-06-17 · 19.0 weeks · 723 dev commits** *(excluded 3 merges + 0 maintenance-bot commits)*

| | Result | |
|---|---|---|
| **AI Adoption** | Pervasive · 97% | Claude 704 |
| **Delivery Health** | 55/100 · F | general eng norms, not AI-attributed |
| **Readiness** | 83/100 · B | static repo state |

## How to read this

- **AI Adoption** — The share of commits an AI tool co-authored — the one directly measured sign AI is actually being used here, not a survey.
- **Delivery Health** — How sound the team's shipping habits are by general engineering norms — deliberately NOT credited to AI. High adoption means little if delivery health is poor.
- **Readiness** — Whether the repo is set up so an AI agent (or a new human) can navigate it and trust what it reads — the conditions that decide whether AI adoption actually pays off.
- **Before/after AI Enablement** — When a clean pre-AI baseline exists, how delivery metrics shifted after adoption — shown as context, never proof AI caused the change.
- **Trajectory** — How AI adoption and delivery health moved over the repo's history — two parallel timelines, correlation only, never proof one caused the other.

## AI adoption (direct, in-repo signal)

- **Pervasive — 97.4%** (704/723 commits), a **lower bound** (squash-merges drop trailers).
- Adoption date: `2026-02-02` (auto-detected)
- Per tool: `Claude` (704)

## Delivery Health (general engineering norms — NOT AI-attributed)

**55/100 · grade F**

| Component | Score | Weight | Flag |
|---|---|---|---|
| change_size_discipline | 100% | 35 |  |
| test_discipline | 10% | 35 | low test discipline |
| knowledge_distribution | n/a (solo author) | 30 |  |

*Context (not scored — too noisy to rank health by): fix/revert 26%, 38.05 commits/wk, 1 contributors.*

## Trajectory — over time *(parallel timelines, NOT a causal link)*

*14 periods, ~10d each.*

| Period | Commits | Adoption | Health |
|---|---|---|---|
| 2026-02-05 | 40 | 100% | 31 |
| 2026-02-15 | 83 | 100% | 55 |
| 2026-02-25 | 16 | 88% | 55 |
| 2026-03-07 | 1 | 100% | — |
| 2026-03-17 | 141 | 99% | 55 |
| 2026-03-27 | 65 | 100% | 55 |
| 2026-04-06 | 22 | 100% | 55 |
| 2026-04-16 | 36 | 100% | 55 |
| 2026-04-26 | 53 | 100% | 57 |
| 2026-05-06 | 80 | 100% | 55 |
| 2026-05-16 | 139 | 89% | 55 |
| 2026-05-26 | 29 | 100% | 78 |
| 2026-06-05 | 17 | 100% | 78 |
| 2026-06-15 | 1 | 100% | — |

## Before/after AI Enablement (bonus — needs a clean pre-AI baseline)

*n/a — AI adoption is at or before repo inception — no pre-AI window to compare. The three numbers above stand on their own.*

## Attribution caveat

> Delivery pillars (flow, quality, risk) measure GENERAL delivery health — only AI-adoption and readiness are AI-specific. A delivery change may come from hiring, a finished migration, or a calmer quarter. The score asks whether the conditions under which AI pays off are improving — it does NOT prove AI caused any change.

<sub>shipsignal v0.1.6 · 2026-06-20T22:19:22Z</sub>

## Readiness — 83/100 · grade B

| Category | Score |
|---|---|
| entry_point | 20/20 |
| agent_instructions | 15/15 |
| module_coverage | 13.3/20 |
| setup_tooling | 9.4/20 |
| doc_integrity | 13/13 |
| doc_freshness | 12/12 |

### Top Readiness fixes (4 total)

- **scripts** — Module 'scripts' (dir) has no README  
  → Add scripts/README.md describing this module
- **src/scenes** — Module 'src/scenes' (dir) has no README  
  → Add src/scenes/README.md describing this module
- **.** — Missing CI configuration  
  → Add CI (e.g. .github/workflows) so agents can see how it's built and tested
- **.** — Missing type config  
  → Add type config (tsconfig.json / mypy / pyright / py.typed)
