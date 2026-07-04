# ShipSignal — AI impact: crown

**2026-02-05 → 2026-06-22 · 19.7 weeks · 724 dev commits** *(excluded 3 merges + 0 maintenance-bot commits)*

| | Result | |
|---|---|---|
| **AI Adoption** | Pervasive · 97% | Claude 705 |
| **Delivery Health** | 55/100 · F | general eng norms, not AI-attributed |
| **Readiness** | 85/100 · B | static repo state |

## How to read this

- **AI Adoption** — The share of commits an AI tool co-authored — the one directly measured sign AI is actually being used here, not a survey.
- **Delivery Health** — How sound the team's shipping habits are by general engineering norms — deliberately NOT credited to AI. High adoption means little if delivery health is poor.
- **Outcomes** — How often changes get reverted or fixed, and how fast — outcome signals to complement the habit-based numbers above. Always context, never part of any score.
- **Readiness** — Whether the repo is set up so an AI agent (or a new human) can navigate it and trust what it reads — the conditions that decide whether AI adoption actually pays off.
- **Before/after AI Enablement** — When a clean pre-AI baseline exists, how delivery metrics shifted after adoption — shown as context, never proof AI caused the change.
- **Trajectory** — How AI adoption and delivery health moved over the repo's history — two parallel timelines, correlation only, never proof one caused the other.

## AI adoption (direct, in-repo signal)

- **Pervasive — 97.4%** (705/724 commits), a **lower bound** (squash-merges drop trailers).
- Adoption date: `2026-02-02` (auto-detected)
- Per tool: `Claude` (705)
- *Breadth: n/a — only 1 active contributor(s) — breadth needs ≥3 to be meaningful and to avoid de-anonymization on small teams.*

## Delivery Health (general engineering norms — NOT AI-attributed)

**55/100 · grade F**

| Component | Score | Weight | Flag |
|---|---|---|---|
| change_size_discipline | 100% | 35 |  |
| test_discipline | 10% | 35 | low test discipline |
| knowledge_distribution | n/a (solo author) | 30 |  |

*Context (not scored — too noisy to rank health by): 36.72 commits/wk, 1 contributors.*

### Where to focus (1)

- **Test discipline** — Only 2% of code-touching commits also touch tests. Pairing changes with tests keeps coverage moving with the code.

_<sub>General engineering norms — not AI-attributed; where delivery health has the most headroom, not a defect list.</sub>_

## Outcomes (context — never scored)

- **Revert pairs:** 4 · median time-to-correction **0d**
- **Change-failure proxy:** 26% (189 commits)

_<sub>How often changes get reverted or fixed, and how fast — outcome signals to complement the habit-based numbers above. Always context, never part of any score.</sub>_

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
| 2026-06-15 | 2 | 100% | — |

## Before/after AI Enablement (bonus — needs a clean pre-AI baseline)

*n/a — AI adoption is at or before repo inception — no pre-AI window to compare. The three numbers above stand on their own.*

## Attribution caveat

> Delivery pillars (flow, quality, risk) measure GENERAL delivery health — only AI-adoption and readiness are AI-specific. A delivery change may come from hiring, a finished migration, or a calmer quarter. The score asks whether the conditions under which AI pays off are improving — it does NOT prove AI caused any change.

<sub>shipsignal v0.8.0 · 2026-07-04T00:51:42Z</sub>

## Readiness — 85/100 · grade B

| Category | Score |
|---|---|
| entry_point | 20/20 |
| agent_instructions | 15/15 |
| module_coverage | 13.3/20 |
| setup_tooling | 11.8/20 |
| doc_integrity | 13/13 |
| doc_freshness | 12/12 |

### Top Readiness fixes (4 total, grouped by area, highest payoff first)

**Module docs**

- **scripts** — Module 'scripts' (dir) has no README (2 .js files: genIcon.js, make_icon.py)  · ≈+3 pts · moderate  
  → Add scripts/README.md — say what these 2 files do, how they fit together, and which is the entry point

  <details><summary>Starter — copy + fill in placeholders</summary>

  ```markdown
  # scripts

  <one-paragraph: what this directory does and when an agent should read it>

  ## Files

  - `genIcon.js` — <one-line role>
  - `make_icon.py` — <one-line role>

  ## Entry point

  `<file>` — <how an agent should start reading>
  ```
  </details>

- **src/scenes** — Module 'src/scenes' (dir) has no README (5 .js files: CreditsScene.js, GameOverScene.js, LoadingScene.js, …)  · ≈+3 pts · moderate  
  → Add src/scenes/README.md — say what these 5 files do, how they fit together, and which is the entry point

  <details><summary>Starter — copy + fill in placeholders</summary>

  ```markdown
  # scenes

  <one-paragraph: what this directory does and when an agent should read it>

  ## Files

  - `CreditsScene.js` — <one-line role>
  - `GameOverScene.js` — <one-line role>
  - `LoadingScene.js` — <one-line role>
  - `…` — <one-line role>

  ## Entry point

  `<file>` — <how an agent should start reading>
  ```
  </details>


**Setup**

- **.** — Missing CI configuration  · ≈+4 pts · moderate  
  → Add CI (e.g. .github/workflows) so agents can see how it's built and tested
- Missing 4 convention items: formatter config (+1), .editorconfig (+1), CONTRIBUTING (+1), LICENSE (+1) — _quick_  
  → Drop these in — each is small but they add up to ≈+4 pts

**Freshness**

- **src/complete_tactical_trpg_rulebook.md** — complete_tactical_trpg_rulebook.md last updated 2026-05-14; 206 commits have landed since — likely behind the current code  · informational · moderate  
  → Skim complete_tactical_trpg_rulebook.md and refresh anything the code has outgrown

_<sub>≈ marks each fix's marginal payoff (resolving it alone). Renormalization means totals aren't additive — fixing several won't equal the sum.</sub>_
