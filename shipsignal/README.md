# shipsignal/ — package module map

Pure static analysis (Readiness) + git-history analytics (Impact), stdlib only. Conventions are in [../CLAUDE.md](../CLAUDE.md).

Pipelines:
- Readiness: `cli` → `scanner` → (`modules` → `detectors` + `setupcheck` → `scoring`) → `report`
- Impact:    `cli` → `impact.compute_impact` → `report.render_impact*`

- `cli.py` — argument parsing; resolves a local path, git URL, or `owner/repo`; clones URLs to a temp dir (treeless) and cleans up; emits json/md/html/badge. Two subcommands: `scan` (readiness) and `impact`.
- `scanner.py` — orchestrates one readiness scan and assembles the `readiness.json` result.
- `modules.py` — module detection + exclusion rules (ecosystem-aware: npm/pnpm/Cargo workspaces, then a directory fallback).
- `gitinfo.py` — git helpers: tracked-file listing, commit dates, treeless clone.
- `detectors.py` — doc/agent detectors (entry point, agent files, module README coverage, broken links, doc freshness) + false-positive guards.
- `setupcheck.py` — setup & convention detectors (test command, CI, deps, lint/format/type config, convention files, MCP resolution).
- `scoring.py` — the 0–100 readiness model with n/a + indeterminate handling and grade bands.
- `impact.py` — Impact lens: single `git log --numstat` pass; AI-co-author registry; adoption auto-detection; confidence gate; no-baseline path; pillar scoring + attribution caveat.
- `report.py` — CLI text + Markdown/HTML reports + badge SVG; separate render functions for readiness vs impact.
