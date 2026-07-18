# Sample audits

Real `shipsignal report` output, committed for reference / case-study use.

## crown — Jeremy's "crownhunter" Phaser 4 game

A 97%-AI-built solo game. Generated with:

```bash
python -m shipsignal.cli report ../crown --html crown-audit.html --md crown-audit.md --json crown-audit.json
```

- [crown-audit.html](crown-audit.html) — the one-page audit deliverable (open in a browser)
- [crown-audit.md](crown-audit.md) — same content, Markdown
- [crown-audit.json](crown-audit.json) — canonical machine-readable form

What it surfaces:

- **AI Adoption:** Pervasive 97% (Claude 705 commits) — adoption date 2026-02-02
- **Delivery Health: 55/F** with a `low test discipline` flag (2.5% test-to-code co-change)
- **Readiness: 83/B** with 4 actionable fixes (missing module READMEs, no CI, no type config)
- **Before/after AI Enablement:** n/a — AI from inception, no pre-AI baseline (the lens refuses to fabricate a delta)

The headline is what the *Impact lens* refuses to do (no fake "+X% from AI" number) combined with what the *Readiness lens* surfaces (a 4-item fix backlog). One scan, one document — exactly what the productized audit ships.

## jest — recovering AI attribution a squash pipeline hid (`--pr-data`)

[jestjs/jest](https://github.com/jestjs/jest) syncs from Meta's internal monorepo, and that pipeline strips `Co-Authored-By` trailers on the way out — so a local scan reads **None / 0% AI**. Exported PR data recovers what was erased, **with zero network calls** (you run the `gh` export; ShipSignal reads the file):

```bash
# Page all merged PRs over full history (chunked ~25/call around the GraphQL node ceiling) → jest-prs.json
python -m shipsignal.cli impact ../jest --pr-data jest-prs.json --md jest-recovery.md --html jest-recovery.html --json jest-recovery.json
```

- [jest-recovery.html](jest-recovery.html) — the rendered audit with the recovery block (open in a browser)
- [jest-recovery.md](jest-recovery.md) — same content, Markdown
- [jest-recovery.json](jest-recovery.json) — canonical machine-readable form

What it surfaces:

- **Measured: None · 0%** (2 of 7,248 commits) — the trailers were stripped on squash, so a local scan sees almost nothing.
- **Recovered: Emerging · 0.2%** — **+9 hidden AI-assisted commits** across **Claude, Cursor, Copilot, and Cody**, at **88% coverage** (4,782 of 5,429 squash commits matched to a PR).
- Coverage discloses that the export was partial (rate-limited at 4,975 of ~5,845 PRs — though every AI-bearing PR was captured), so the recovered figure is itself labelled a lower bound.

The point isn't the *size* of the number — it's that a repo that reads **0% AI** locally actually has named, real AI contributions its pipeline erased, and the recovered figure never silently replaces the measured one. This is the honest counterpart to the squash caveat: the number is either accurate (GitHub-native squash) or recoverable (`--pr-data`), and the tool tells you which.
