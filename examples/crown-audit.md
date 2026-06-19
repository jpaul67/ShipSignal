# ShipSignal — AI impact: crown

**2026-02-05 → 2026-06-17 · 19.0 weeks · 726 commits**

| | Result | |
|---|---|---|
| **AI Adoption** | Pervasive · 97% | Claude 705 |
| **Delivery Health** | 55/100 · F | general eng norms, not AI-attributed |
| **Readiness** | 83/100 · B | static repo state |

## AI adoption (direct, in-repo signal)

- **Pervasive — 97.1%** (705/726 commits), a **lower bound** (squash-merges drop trailers).
- Adoption date: `2026-02-02` (auto-detected)
- Per tool: `Claude` (705)

## Delivery Health (general engineering norms — NOT AI-attributed)

**55/100 · grade F**

| Component | Score | Weight | Flag |
|---|---|---|---|
| change_size_discipline | 100% | 35 |  |
| test_discipline | 10% | 35 | low test discipline |
| knowledge_distribution | n/a (solo author) | 30 |  |

*Context (not scored — too noisy to rank health by): fix/revert 26%, 38.21 commits/wk, 1 contributors.*

## Before/after AI Enablement (bonus — needs a clean pre-AI baseline)

*n/a — AI adoption is at or before repo inception — no pre-AI window to compare. The three numbers above stand on their own.*

## Attribution caveat

> Delivery pillars (flow, quality, risk) measure GENERAL delivery health — only AI-adoption and readiness are AI-specific. A delivery change may come from hiring, a finished migration, or a calmer quarter. The score asks whether the conditions under which AI pays off are improving — it does NOT prove AI caused any change.

<sub>shipsignal v0.1.0 · 2026-06-19T20:49:45Z</sub>

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
