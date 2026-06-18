# bellwether/ — package module map

The v0 agent-readiness scanner. Pure static analysis, stdlib only. Conventions are in [../CLAUDE.md](../CLAUDE.md).

Pipeline: `cli` → `scanner` → (`modules` → `detectors` + `setupcheck` → `scoring`) → `report`.

- `cli.py` — argument parsing; resolves a local path, git URL, or `owner/repo`; clones URLs to a temp dir (treeless) and cleans up; emits json/md/html/badge.
- `scanner.py` — orchestrates one scan and assembles the `readiness.json` result.
- `modules.py` — module detection + exclusion rules (ecosystem-aware: npm/pnpm/Cargo workspaces, then a directory fallback).
- `gitinfo.py` — git helpers: tracked-file listing, commit dates, treeless clone.
- `detectors.py` — doc/agent detectors (entry point, agent files, module README coverage, broken links, doc freshness) + false-positive guards.
- `setupcheck.py` — setup & convention detectors (test command, CI, deps, lint/format/type config, convention files, MCP resolution).
- `scoring.py` — the 0–100 model with n/a + indeterminate handling and grade bands.
- `report.py` — CLI text + Markdown/HTML report + badge SVG rendering.
