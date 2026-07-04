# shipsignal/ — package module map

Pure static analysis (Readiness) + git-history analytics (Impact), stdlib only. Conventions are in [../CLAUDE.md](../CLAUDE.md).

Pipelines:
- Readiness: `cli` → `scanner` → (`modules` → `detectors` + `setupcheck` → `scoring`) → `report`
- Impact:    `cli` → `impact.compute_impact` (→ `timeline.build_trajectory`) → `report.render_impact*`

- `cli.py` — argument parsing; resolves a local path, git URL, or `owner/repo`; clones URLs to a temp dir (treeless for readiness, full for impact) and cleans up; emits json/md/html/badge. Subcommands: `scan` (readiness), `impact`, `report` (unified).
- `config.py` — loads repo-local `.shipsignal.toml` defaults (extra AI aliases, squash, release-tag pattern, fail-under, module excludes, badge label). Never raises — unknown keys and wrong types degrade to a warning + built-in default.
- `scanner.py` — orchestrates one readiness scan and assembles the `readiness.json` result.
- `modules.py` — module detection + exclusion rules (ecosystem-aware: npm/pnpm/Cargo workspaces, then a directory fallback; `.shipsignal.toml`'s `exclude_modules` waives matching paths from the README requirement).
- `gitinfo.py` — git helpers: tracked-file listing, commit dates, treeless clone, tag listing (`list_tags`) and per-tag-pair commit timestamps (`commits_between_tags`, one `git log` call per pair).
- `detectors.py` — doc/agent detectors (entry point, agent files, module README coverage, broken links, doc freshness) + false-positive guards.
- `setupcheck.py` — setup & convention detectors (test command, CI, deps, lint/format/type config, convention files, MCP resolution).
- `scoring.py` — the 0–100 readiness model with n/a + indeterminate handling and grade bands.
- `impact.py` — Impact lens: single `git log --no-merges --numstat` pass; bot/merge exclusion; AI-co-author registry; adoption auto-detection; confidence gate; no-baseline path; pillar scoring + attribution caveat. `extra_aliases()` temporarily merges `.shipsignal.toml`'s extra AI aliases into the registry for one scan. `compute_outcomes()` (Package J) matches revert pairs by sha (git's own revert body line, or `Fixes:`/`Reverts:` trailers) for median time-to-correction, plus the relabeled change-failure proxy — displayed context only, never scored. `compute_release_cadence()` (Package K) derives tags-per-month, median inter-tag gap, and median lead-time-to-release from version tags (filtered to release-shaped ones, overridable via `.shipsignal.toml`'s `release_tag_pattern`) — also context only, never scored.
- `timeline.py` — over-time trajectory: per-period adoption % + delivery health (tumbling windows, honest gaps).
- `glossary.py` — explanatory copy (single source for inline lines, HTML tooltips, the "How to read this" block).
- `report.py` — CLI text + Markdown/HTML reports (incl. SVG trajectory chart) + badge SVG/JSON (static + live shields.io endpoint); separate render functions for readiness vs impact.
- `ansi.py` — CLI color helpers (`resolve_enabled`/`paint`/`bold`/`grade`/`warn`/`strip`); the only module that emits ANSI escapes, so `report.py` renderers stay pure.
