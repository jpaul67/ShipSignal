# Sample audits

Real `bellwether report` output, committed for reference / case-study use.

## crown — Jeremy's "crownhunter" Phaser 4 game

A 97%-AI-built solo game. Generated with:

```bash
python -m bellwether.cli report ../crown --html crown-audit.html --md crown-audit.md --json crown-audit.json
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
