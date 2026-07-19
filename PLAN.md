# ShipSignal post-launch roadmap — agent handoff plan

Written 2026-07-01, just after the repo went public (v0.6.6 on PyPI, Action live at
`jpaul67/ShipSignal@v1`, external smoke test verified). Twelve work packages, grouped into six
release trains (re-planned 2026-07-02 — see the status notes). Each package is written to be
handed to a separate agent with no other context.

**Status (2026-07-01): Train 1 (Packages E, H, B) SHIPPED.** Code, tests, and docs landed on
`main`, released as **v0.7.0** (tagged, PyPI publish verified live), and the live-badge dogfood
loop is running in production — the `live-badge` workflow republishes the gist on every push to
main (`gh workflow run live-badge` to trigger manually), and the README badge renders from it.
`GIST_TOKEN` (classic PAT, `gist` scope) and `GIST_ID` are set as a repo secret/variable.

**Status (2026-07-02): Train 2 (Packages A + C) and v0.8.0 SHIPPED.** Package A (Action
PR-comment mode) merged via [PR #5](https://github.com/jpaul67/ShipSignal/pull/5) — comment
posted, upserted across 3 follow-up pushes, fork-safety degrade path confirmed live. Package C
done: README hero image, social-preview image (uploaded), Marketplace listing published (Code
quality / Continuous integration categories) at
[github.com/marketplace/actions/shipsignal-readiness-gate](https://github.com/marketplace/actions/shipsignal-readiness-gate);
CLI demo GIF explicitly skipped (Windows tooling friction, low value over the hero image).

**v0.8.0**: bundled Package A + Package C + the security-hardening pass. Tagged, pushed, PyPI
publish verified live. Floating `v1` Action tag re-pointed at the release commit and re-verified
externally via `shipsignal-smoke` (now a permanent fixture at
`C:\Users\jerem\code\shipsignal-smoke`, not a throwaway — its workflow now also covers
`pr-comment` mode via an actual PR, verified live and then closed).

**Re-planned 2026-07-02 (post-v0.8.0):** three impact-lens packages added — **J** (outcome
signals: revert pairs → time-to-correction), **K** (release cadence & lead time from tags),
**L** (AI line survival) — and the remaining work re-sequenced into Trains 3–6. Reasoning:
with no external users yet, the impact-lens differentiators ARE the user acquisition, so they
move ahead of the team-workflow features; I and F slide to a demand-triggered Train 6. One
hard dependency: L lands after D (squash recovery fixes the attribution L's comparison
depends on).

**Status (2026-07-03): Train 3 (Packages G, J, K) and v0.9.0 SHIPPED.** Package G
(`.shipsignal.toml` config file) landed first — repo-local defaults for extra AI aliases,
squash, `release_tag_pattern`, readiness `fail_under`/`exclude_modules`, and `badge_label`;
CLI flag > config file > built-in default, never crashes on a typo. Package J (Outcomes:
revert pairs & time-to-correction) and Package K (release cadence & lead time from tags) both
landed as **context-only blocks — never folded into Delivery Health.** Together with the
existing change-failure proxy, that's deploy frequency, lead time, and change-failure rate from
git history alone, zero integrations (time-to-restore stays out of scope on purpose — production
incidents aren't in git). Calibrated against crown/chalk/vitest before merge.

**v0.9.0**: tagged, pushed, PyPI publish verified live — a fresh-venv install from PyPI plus a
real scan confirmed both new blocks render correctly.

**Status (2026-07-18): Train 4 (Package D) and v0.10.0 SHIPPED.** `--pr-data` on `impact`/`report`
recovers AI `Co-Authored-By` attribution that a non-native squash/merge pipeline dropped, with
**zero network calls** — the user exports merged-PR data with one `gh` command and ShipSignal reads
the local file (new module [shipsignal/prdata.py](shipsignal/prdata.py), pure parsing, guarded by an
import-scan test asserting no `urllib`/`http`/`socket`). Squash commits match PRs by merge-commit SHA
(or the `(#NNN)` subject); recovered co-authors run through the same registry matcher as local
trailers; the result renders as a measured-vs-recovered **dual figure with coverage** that never
replaces the measured number, plus a self-advertising export recipe when a squash workflow is detected
without `--pr-data`. **Premise corrected during recipe pinning:** GitHub-native "Squash and merge"
*preserves* co-authors (it aggregates them onto the squash commit), so a squash workflow is NOT
automatically an adoption floor — calibrated across vite, prettier, cal.com, pydantic, electron, react
(all retain) vs jest (Meta internal-sync, drops). The caveat, JSON `note`, and glossary copy were
reworded to say adoption is undercounted *only if* the pipeline strips trailers. Validated end-to-end
on jest (7,248 commits): measured None 0% → recovered Emerging 0.2%, +9 hidden AI commits across
Claude/Cursor/Copilot/Cody at 88% coverage, committed as
[examples/jest-recovery.*](examples/jest-recovery.md) (the real run also caught a sub-1% display-rounding
bug, now fixed + regression-tested). Recipe gotcha: `--limit 1000` in one call trips GitHub's GraphQL
node ceiling — export in chunks of ~25. No `action.yml` change, so no `v1` retarget.

**v0.10.0** (deliberately NOT v1.0.0 — the calibration showed recovery is niche: most repos use
GitHub-native squash and need nothing, so this is a strong minor, not the 1.0 statement): merged via
[PR #6](https://github.com/jpaul67/ShipSignal/pull/6), tagged, pushed, PyPI publish verified live via a
fresh-venv install. Package L's hard dependency on D (survival consumes D's recovered attribution) is
now cleared.

**Not started: Trains 5–6** (Packages L, I, F — see the table below). Pick up Train 5
(Package L) next.

## Read-first for every agent (non-negotiable repo rules)

1. Read `CLAUDE.md` and `shipsignal/README.md` before touching code. Key constraints:
   - **Stdlib only** — no runtime dependencies, ever.
   - **Never read diff or prompt content** — only git metadata (dates, sizes, paths, trailers).
   - **Honesty is the brand**: never imply AI causation for delivery numbers; withhold numbers
     you can't back; caveats are additive, never alter displayed numbers.
   - Explanatory copy lives ONLY in `shipsignal/glossary.py` (single source for CLI lines,
     HTML tooltips, and the "How to read this" block).
2. Tests are stdlib `unittest` in `tests/`. Add tests for everything; run
   `python -m unittest discover -s tests -v` (or `make test`) before committing.
3. Dogfood gate must still pass: `python -m shipsignal.cli scan . --fail-under 90`.
4. Lint: `ruff check .` must be clean (CI enforces it).
5. Commit as `jpaul67 <5659943+jpaul67@users.noreply.github.com>` (repo-local git config is
   already set — don't override).
6. **Docs checklist applies to every package** (see "Global docs checklist" at the bottom).
   A package is not done until its docs rows are done.
7. Version bumps: keep `shipsignal/__init__.py` `__version__` in sync with `pyproject.toml`
   (this desynced once before — commit 21de140). PyPI publish fires ONLY on strict `vX.Y.Z`
   tags. The Action's floating `v1` tag must be manually retargeted after Action changes.

---

## Release train overview

| Train | Version | Packages | Theme |
|---|---|---|---|
| 1 | v0.7.0 | E (AI registry) · H (CLI color) · B (badge endpoint) | quick wins, better core number |
| 2 | v0.8.0 | A (Action PR comments) · C (marketing/visuals) | growth loops |
| 3 | v0.9.0 | G (config file) · J (outcome signals) · K (release cadence) | "DORA-shaped proxies, zero integrations" |
| 4 | v0.10.0 | D (squash recovery from exported PR data) | flagship 1 — closes the measurement gap |
| 5 | v0.11.0 | L (AI line survival) | flagship 2 — the acceptance-rate metric |
| 6 | v0.12.0 | I (compare command) · F (`fix` scaffolding) | team workflow — demand-triggered |

Rationale for ordering: Train 1 was small and sharpened the product before more eyes arrived;
Train 2 was the visibility loop, landed while launch attention existed (both shipped). The
re-sequenced tail (2026-07-02): Train 3 upgrades every scan with zero user friction and gives
the README its strongest hook — G rides along because J/K/L hang config keys off it (a soft
dependency; CLI flags and built-in defaults work without it). Train 4 is unchanged, and is now
also the prerequisite for honest survival numbers (squash misattribution would contaminate
L's comparison group). Train 5 ships the second flagship alone. Train 6 is what the first
real team will ask for — let real user signal (an issue, a star spike, someone asking)
trigger it rather than a schedule; F can be pulled forward alone as a quick win between big
trains if a demo moment is wanted.

---

## Package E — Broaden the AI-tool registry (Train 1)

**Goal:** `AI_TOOL_ALIASES` and the AI-agent-bot detection in `shipsignal/impact.py` are missing
a generation of agents, which understates the AI Adoption number.

**Steps:**
1. Read `shipsignal/impact.py`: `AI_TOOL_ALIASES` (~line 35), `_BOT_RE`, the AI-agent-bot list,
   and the matching code (~line 168: `if any(kw in low for kw in AI_TOOL_ALIASES)`).
2. **Fix the substring-match hazard first.** Matching is bare `kw in low` over the whole
   co-author line. Short aliases will false-positive (e.g. adding `"amp"` matches
   `foo@example.com`). Refactor matching to word-boundary/token-aware matching (regex with
   `\b`, or match against the parsed name/email local-part, not the raw line). Add regression
   tests proving `amp` does NOT match `example.com` and existing aliases still match.
3. Extend the registry. Candidates to research and add with correct display labels:
   Codex/OpenAI (`codex`), Windsurf, Cline, Roo Code, Amp (Sourcegraph), OpenHands, Goose
   (Block), Jules (Google), Amazon Q, Sweep, Qodo, Junie (JetBrains), Kiro (AWS), Zed agent.
   Also GitHub's `copilot-swe-agent[bot]` and `devin-ai-integration[bot]` as AI-agent bots.
   For each: verify the actual trailer/committer string the tool emits (web search; cite the
   source in the PR description). Do NOT add speculative entries — the registry is a versioned
   constant, extended deliberately.
4. Re-run calibration: `python -m shipsignal.cli impact .` on this repo and (if available)
   `../crown`; confirm adoption numbers move only for the right reasons.
5. Tests: one test per new alias (trailer form) + bot-classification tests.
6. Docs: CHANGELOG entry under Unreleased; note in `CLAUDE.md`'s registry gotcha that matching
   is token-aware. Establish the recurring habit: add a `## Registry review` line to
   CHANGELOG conventions or a quarterly issue template — pick one, document it.

**Acceptance:** new aliases detected in test fixtures; no false positives on an email-domain
corpus test; ruff + full suite green; dogfood gate passes.

---

## Package H — ANSI color in CLI output (Train 1)

**Goal:** the terminal renderer prints the three headline numbers with no styling; color/bold
makes every demo and screenshot better.

**Steps:**
1. Read the CLI text renderers in `shipsignal/report.py` (readiness + impact + trend text).
2. Add a tiny stdlib color helper (module-level in `report.py` or a new `shipsignal/ansi.py`):
   bold + a small palette keyed off the existing grade bands (reuse `GRADE_COLOR` semantics —
   green/yellow/red family, not the hex values).
3. Enablement rules: on only when `sys.stdout.isatty()`, `NO_COLOR` env unset, and
   `TERM != "dumb"`; add `--no-color` (and honor `FORCE_COLOR` for CI screenshots). On
   Windows, enable VT processing (the `os.system("")` trick or
   `ctypes`/`SetConsoleMode`) — must degrade silently if that fails.
4. Style targets (keep restrained): the three headline numbers + grades, section headers,
   flag lines (e.g. `low test discipline` in the warning color), fix payoff estimates.
   Copy text itself stays in `glossary.py` — color is presentation, applied in `report.py`.
5. Tests: renderer output with color forced off is byte-identical to today's output (protects
   downstream consumers that capture stdout); a forced-on test asserts codes are present and
   strippable.
6. Docs: CHANGELOG; README mention of `--no-color`/`NO_COLOR`; `CLAUDE.md` command list if a
   flag is added.

**Acceptance:** piped/redirected output unchanged; `NO_COLOR=1` unchanged; colored TTY output
verified on Windows (this machine) and in the Linux CI job (via `FORCE_COLOR` snapshot test).

---

## Package B — Shields endpoint badge JSON (Train 1)

**Goal:** the current `--badge FILE` SVG must be committed and goes stale. Emit a
[shields.io endpoint](https://shields.io/badges/endpoint-badge) JSON so users get a *live*
badge via a gist or Pages.

**Steps:**
1. Read the badge SVG generation in `shipsignal/report.py` and the `--badge` wiring in
   `shipsignal/cli.py`.
2. Add `--badge-json FILE` to `scan` (and `report`): writes
   `{"schemaVersion": 1, "label": "readiness", "message": "<score>/100", "color": "<grade color>"}`.
   Reuse the exact grade→color mapping the SVG badge uses.
3. Add a matching passthrough example to the Action docs: a workflow step that publishes the
   JSON to a gist (`gh gist edit`) with the shields URL to paste into a README. The Action
   itself needs no code change (`args: "--badge-json badge.json"` passes through) — but ADD an
   example workflow under `examples/workflows/` showing the gist publish + the resulting
   `img.shields.io/endpoint?url=...` snippet.
4. Tests: JSON schema/content per grade band; CLI flag test alongside the existing `--badge`
   tests in `tests/test_cli.py`.
5. Docs: README "Output" section (add the live-badge recipe — this is a marketing feature,
   write it as such); `docs/github-action.md`; CHANGELOG; `CLAUDE.md` command list.
6. Dogfood: set up the gist + live badge for ShipSignal's own README (needs a
   `gh` auth with gist scope — if unavailable, leave the exact commands in the PR description
   for the user to run).

**Acceptance:** `shipsignal scan . --badge-json b.json` produces valid endpoint JSON; the
shields URL renders (verify by fetching `https://img.shields.io/endpoint?url=<raw gist url>`
once the gist exists); docs show the full recipe end-to-end.

### Train 1 release steps (after E + H + B merge)
1. Move CHANGELOG Unreleased → `## [0.7.0]`; bump `pyproject.toml` + `__version__` to 0.7.0.
2. Tag `v0.7.0`, push — PyPI publishes via the existing OIDC workflow. Verify on PyPI.
3. `uvx shipsignal@0.7.0 report ../crown` as a post-release smoke test.

---

## Package A — Action PR-comment mode (Train 2)

**Goal:** the Action writes only to the job summary. A sticky PR comment (score, grade, top
fixes) is the growth loop — every contributor on every PR sees it.

**Steps:**
1. Read `action.yml` (composite action; already outputs `score` and `passed`) and
   `docs/github-action.md`.
2. Add input `pr-comment` (default `"false"`). When `"true"` and the event is a PR:
   - Build a compact Markdown comment: readiness score + grade, pass/fail vs `fail-under`,
     top 3 fixes with payoff estimates, and a one-line footer linking to the ShipSignal repo
     (the growth loop — keep it one line, not an ad).
   - Reuse the existing `--md` output if suitable, else add `--md-summary` upstream in the CLI
     (prefer reusing: parse/trim the existing md in bash/python inside the action).
   - Upsert semantics: find an existing comment containing a hidden marker
     (`<!-- shipsignal-report -->`) via `gh api repos/.../issues/N/comments`, PATCH it if
     found, POST otherwise. Never stack duplicate comments.
   - Use the workflow `GITHUB_TOKEN` (`GH_TOKEN` env from `github.token`); document that the
     workflow needs `permissions: pull-requests: write`.
   - Fork-PR safety: on `pull_request` from a fork the token is read-only — the step must
     detect the 403/permission case and degrade to a log notice, never fail the job.
3. **Delta vs base branch is OUT of scope for v1** of this feature (needs a second scan of the
   base ref; design it later, note it in the docs as planned).
4. Test matrix (no unit-test harness exists for composite actions — test via workflows):
   - In-repo workflow PR: comment appears, updates on second push, respects `fail-under`.
   - External repo (reuse the existing smoke-test setup): comment works from `@v1`.
   - Fork PR simulation: degrades gracefully.
5. Docs: `docs/github-action.md` (new input + permissions block + fork caveat),
   `examples/workflows/` new example, README Action snippet gains the `pr-comment` line,
   CHANGELOG.
6. Release: this is Action-only (no PyPI change needed unless CLI gained a flag). Tag a new
   patch/minor anyway if CLI changed; **retarget the floating `v1` tag** to the new commit
   (`git tag -f v1 <sha> && git push -f origin v1`) and re-verify from the external smoke repo.

**Acceptance:** sticky comment demonstrated on a real PR (screenshot in PR description);
duplicate-comment upsert proven; fork-PR path doesn't fail the job; `@v1` retargeted and
externally verified.

---

## Package C — Marketing & visuals (Train 2)

**Goal:** the README is text-only; the HTML audit is the wow artifact and it's buried. Also:
the Action isn't on the GitHub Marketplace.

**Steps:**
1. **Hero image:** generate a fresh `examples/crown-audit.html` (or use this repo's own
   report), screenshot the top of the rendered page (headline numbers + a few fixes) at
   ~1280px wide. An agent with browser tooling can render + capture; otherwise produce the
   HTML and hand the user exact instructions. Save as `docs/assets/report-hero.png` (create
   `docs/assets/`), reference it at the top of README under the tagline.
2. **CLI GIF (optional, second):** record `uvx shipsignal report ../crown` with
   [vhs](https://github.com/charmbracelet/vhs) or asciinema+agg. If tooling on Windows is
   painful, skip — the hero PNG is the must-have. If made: `docs/assets/report-demo.gif`.
3. **Social preview:** repo Settings → Social preview accepts only manual upload (no API).
   Produce a 1280×640 PNG (hero screenshot on a plain background with the name + tagline) at
   `docs/assets/social-preview.png` and hand the user a one-line instruction to upload it.
4. **Marketplace listing:** verify `action.yml` `name` is unique on the Marketplace and
   `branding` is set (it is: anchor/yellow). Create a GitHub *release* (not just a tag) for
   the current version; the "Publish this Action to the GitHub Marketplace" checkbox in the
   release UI is **user-manual** (first time requires accepting the Marketplace agreement —
   only the repo owner can). Prepare: release notes text, category suggestions
   (Continuous Integration; Code quality), and step-by-step instructions for the user.
5. **Repo metadata refresh** (agent-doable via `gh`): confirm description, homepage
   (PyPI page or docs), and topics include: `ai`, `developer-tools`, `git-analytics`,
   `code-quality`, `github-actions`, `agent-readiness`, `cli`, `python`.
6. Docs: README (hero image + any copy tightening around it), CHANGELOG (docs-only note),
   `docs/github-action.md` gains a "Find it on the Marketplace" line once listed.

**Acceptance:** README renders the hero image on GitHub; social-preview PNG delivered +
upload instructions; Marketplace listing live (after the user's manual click-through);
topics/description verified via `gh repo view`.

---

## Package G — `.shipsignal.toml` config file (Train 3)

**Goal:** teams need repo-local defaults: custom AI aliases (internal bots), module excludes,
default `fail-under`, default `--squash`.

**Steps:**
1. New `shipsignal/config.py`: load `.shipsignal.toml` from the scan target root via stdlib
   `tomllib`. Schema (all optional):
   ```toml
   [impact]
   extra_ai_aliases = { "acme-bot" = "Acme internal" }  # merged into AI_TOOL_ALIASES at runtime
   squash = true
   [readiness]
   fail_under = 80
   exclude_modules = ["vendor/legacy"]
   [report]
   badge_label = "readiness"
   ```
   Validate strictly: unknown keys → warning (not error); wrong types → clear error naming the
   key. Never crash a scan because of a config typo. Packages K and L add keys under
   `[impact]` later (`release_tag_pattern`; a `survival` block) — the warn-on-unknown-keys
   rule keeps the schema additive.
2. Precedence: CLI flag > config file > built-in default. Document this rule in one place
   (glossary or docs) and enforce it in `cli.py` wiring.
3. Wire into: `impact.py` (alias merge, squash), `scanner.py`/`modules.py` (excludes),
   `cli.py` (fail-under default), `report.py` (badge label).
4. Config file must NOT count toward or against the readiness score (check `setupcheck.py`
   doesn't accidentally grade it; decide explicitly whether its presence is worth a
   convention-file point — recommend: no, stay neutral).
5. Tests: `tests/test_config.py` — load/merge/precedence/typo handling; an end-to-end CLI test
   with a fixture repo containing a config.
6. Docs: README (new "Configuration" section), `docs/getting-started.md`, `CLAUDE.md`
   (conventions + the precedence rule), `shipsignal/README.md` module map (+`config.py`),
   CHANGELOG. Action docs: note that a repo's config is picked up automatically in CI.

**Acceptance:** all four config domains demonstrably work with CLI-override precedence;
malformed config degrades with a readable warning; suite + ruff + dogfood green.

---

## Package J — Outcome signals: revert pairs & time-to-correction (Train 3)

**Goal:** Delivery Health measures *habits* (change size, tests, knowledge distribution) but
no *outcomes*: how often changes get reverted or fixed, and how fast. Both are computable
from commit metadata alone. Together with Package K this is the "DORA-shaped proxies, zero
integrations" story.

**Steps:**
1. Read `shipsignal/impact.py` — `walk_history` already collects subjects and trailers, and a
   fix/revert share already renders as unscored context — plus the impact renderers in
   `report.py`.
2. **Solid core first: revert pairs.** Git's own revert format is an explicit edge — subject
   `Revert "<subject>"` + body `This reverts commit <sha>.` Parse the target sha, match it
   against the analyzed commit set, and compute **time-to-correction** = revert date − target
   date. Report the median + the pair count. Also honor explicit `Fixes: <sha>` /
   `Reverts: <sha>` trailers. Only count pairs whose target is inside the analyzed history;
   disclose how many reverts didn't match. Test the revert-of-a-revert edge.
3. **The change-failure proxy stays context, never scored.** Relabel the existing fix/revert
   share as the change-failure proxy and attach its caveat: it measures *commit-labeling
   discipline* as much as failure rate — a repo with honest `fix:` conventions must never
   score worse than a vague-message repo. Folding it into the delivery-health score is
   forbidden; the caveat text lives in `glossary.py`.
4. Render a new "Outcomes" block in the impact text/md/html output: revert-pair count, median
   time-to-correction, the relabeled change-failure context line. Sample floor: fewer than 3
   revert pairs → "n/a — too few revert pairs to time" (same honest-degrade style as breadth).
5. Scoring promotion is OUT of scope for this package: everything ships as displayed
   numbers/flags. Whether time-to-correction ever joins the delivery-health score is a
   separate post-calibration decision.
6. Copy in `glossary.py`: what each number measures, the labeling-discipline caveat, and the
   not-MTTR disclaimer (time-to-correction is commit-scoped; incidents aren't in git).
7. Tests: fixture histories with real `git revert` commits — happy path, revert-of-revert,
   target outside the window, trailer forms, floor behavior, renderer output.
8. Re-run the calibration trio (crown / chalk / vitest); the numbers must be explainable
   before merge.
9. Docs checklist: README (Impact section gains the Outcomes block, honest framing),
   `docs/getting-started.md`, `CLAUDE.md` (new gotcha: the change-failure proxy is never
   scored), CHANGELOG.

**Acceptance:** revert pairs + median time-to-correction render on a fixture and at least one
calibration repo; the change-failure proxy remains unscored with its caveat visible;
sub-floor repos degrade honestly; suite + ruff + dogfood green.

---

## Package K — Release cadence & lead time from tags (Train 3)

**Goal:** deploy-frequency and lead-time proxies from version tags — the other half of the
DORA story, from data already in the clone.

**Steps:**
1. Read `shipsignal/gitinfo.py` (subprocess helpers) and the impact context rendering.
2. Collect tags in one pass:
   `git for-each-ref refs/tags --format='%(refname:short)%x1f%(creatordate:unix)'` —
   `creatordate` resolves correctly for both annotated tags (tag date) and lightweight tags
   (commit date).
3. Filter to release-shaped tags: default pattern is semver-ish (`v?N.N[.N]`), overridable
   via `release_tag_pattern` under `[impact]` in `.shipsignal.toml` (coordinate the key name
   with Package G, same train). Monorepo per-package tags (`pkg@1.2.3`) are the motivating
   case for the override.
4. **Release cadence** (deploy-frequency proxy): tags-per-month + median inter-tag gap over
   the trailing 12 months; fall back to the full window when sparse, and disclose which
   window was used.
5. **Lead time** (proxy): for each consecutive tag pair (T1, T2], commits from
   `git log T1..T2 --no-merges --format=%ct` get release date = date(T2); lead time =
   date(T2) − commit date; report the median. One log call per window — linear, no
   per-commit subprocesses.
6. Honest degrade: no tags, or fewer than 3 release-shaped tags → "n/a — no release tags
   found". Tags ≠ deploys (services deploy without tagging) — the copy must say so, and an
   untagged repo is never penalized.
7. Ship as displayed context, not scored — same rule as Package J.
8. Copy in `glossary.py`: proxies-not-DORA framing.
9. Tests: fixture repo with annotated + lightweight + noise tags; pattern filter + config
   override; trailing-window fallback; the n/a path.
10. Calibration trio, then docs: README — with J landed, this is the moment to write the
    "DORA-shaped proxies from git history alone, zero integrations" framing honestly: deploy
    frequency ✓, lead time ✓, change-failure proxy ✓ (context), time-to-restore ✗ (incidents
    aren't in git — saying so is on-brand). Also `docs/getting-started.md`, CHANGELOG.

**Acceptance:** a tagged calibration repo (chalk) shows cadence + lead time; an untagged
fixture degrades to n/a; the pattern override works via config; suite + ruff + dogfood green.

### Train 3 release steps
CHANGELOG → `## [0.9.0]`; version bumps (both files); tag `v0.9.0`; verify PyPI;
`uvx shipsignal@0.9.0` smoke.
(Ship G first — J and K hang config keys off it — then J and K in either order; if one slips,
release what's ready as 0.9.0 and the straggler as 0.9.1 — don't hold the train. Nothing in
this train touches `action.yml`, so no `v1` retarget.)

---

## Package D — Squash-merge adoption recovery from exported PR data (Train 4, flagship)

**Goal:** squash merges destroy `Co-Authored-By` trailers, so the adoption number is a floor.
v0.6.6 ships the *disclosure*; this ships the *recovery* — WITHOUT ShipSignal ever touching
the network. The user exports PR data themselves (one `gh` command); ShipSignal reads the
local file.

**Decided 2026-07-01: the "nothing leaves your box" promise stays absolute. Do NOT implement
a network client — no urllib, no tokens, no gh subprocess calls from inside ShipSignal.
ShipSignal makes zero network calls, with or without this feature.**

**Steps:**
1. **Pin the export recipe + schema first.** Verify which single `gh` command yields, for
   each merged PR: PR number, merge-commit SHA, and per-commit co-author data. Likely
   candidate: `gh pr list --state merged --limit 1000 --json number,mergeCommit,mergedAt,commits`
   (GraphQL-backed; `commits[].authors` includes GitHub's own parsed co-authors, which covers
   `Co-Authored-By` trailers). Validate against a real squash-workflow repo BEFORE writing
   parsing code; record the exact command and a real sample payload as a test fixture. If one
   command can't do it, a short documented script is acceptable — but fight for one
   copy-pasteable line, because the recipe IS the UX.
2. New `shipsignal/prdata.py`: load + validate the JSON file. Support exactly one documented
   shape (the pinned recipe's output) and error clearly on anything else ("this doesn't look
   like the output of `<command>` — see <docs link>"). A second shape (REST `/pulls`) only if
   it falls out nearly free.
3. Wire `--pr-data FILE` into `impact` and `report` (`cli.py` → `impact.py`):
   - Match local squash commits to PRs by merge-commit SHA; fall back to `(#123)` subject
     parsing where SHAs don't match (e.g. rebase-merge).
   - Run recovered co-authors through the SAME registry/matching code as local trailers
     (Package E's token-aware matcher — see the dependency note below).
   - **Honesty labeling:** the recovered number NEVER silently replaces the measured one.
     Render a dual figure — "measured floor: X% · recovered from PR data (N of M squash
     commits matched): Y%" — and disclose coverage. A stale or partial export must show up
     as low coverage, not as a confident number.
4. **Self-advertising:** when the squash caveat fires and no `--pr-data` was given, the
   report appends the exact two-line recipe (export command + re-run command). This is the
   discovery mechanism — the tool teaches the feature at the moment it's relevant, so the
   two-step UX costs nothing up front.
5. Copy in `glossary.py` (floor vs recovered, coverage line, recipe text — single source).
6. Tests: fixture JSON files — no network, no mocking, that's the point. Cover: happy path,
   partial coverage, zero matches, malformed file, wrong-repo file (SHAs match nothing),
   stale file (exported before recent commits). Assert the default path (no flag) is
   byte-identical to today's output.
7. Docs:
   - README: this STRENGTHENS the promise — "zero network calls, even for squash recovery:
     you export the data, ShipSignal reads it." Add the recipe under the Impact lens section.
   - `docs/github-action.md` + `examples/workflows/`: CI recipe — an export step
     (`env: GH_TOKEN: ${{ github.token }}`) before the scan step.
   - `SECURITY.md`: one line reaffirming zero-network; `--pr-data` reads only a
     user-supplied local file.
   - `CLAUDE.md` gotchas: "no module may open a network connection — squash recovery reads a
     user-exported file"; `shipsignal/README.md` module map (+`prdata.py`); CHANGELOG.

**Acceptance:** zero network calls anywhere — add a CI/test check asserting the package never
imports `urllib.request`/`http.client`/`socket`; recovered number renders as the labeled dual
figure with coverage; the squash-caveat report prints the recipe; fixture-driven suite green;
validated end-to-end against one real squash-workflow repo using the documented export
command (crown does not qualify — it's direct-to-main; pick a real squash-merge OSS repo).

**Dependency note:** land AFTER Package E (token-aware matcher) — recovered co-authors flow
through the same matcher, and short aliases must not false-positive on PR-author emails.
Package L (line survival) depends on THIS package in turn — its recovered attribution feeds
survival's comparison groups; land D before L.

### Train 4 release steps
This is the headline release: CHANGELOG → `## [0.10.0]` with a proper narrative entry;
version bumps; tag; PyPI verify; consider whether this is actually `v1.0.0` — decide with the
user at release time (the feature completes the original honesty story, which is a defensible
1.0 line).

---

## Package L — AI line survival (Train 5, flagship 2)

**Goal:** adoption says AI was in the room; survival says the work *stuck*. Blame the current
tree, attribute surviving lines to AI-assisted vs other commits, and compare — the
acceptance-rate metric nobody else computes locally. This is the hardest package to keep
honest; the rails below are acceptance criteria, not suggestions.

**Hard dependency: land AFTER Package D.** Squash merges strip trailers and misattribute AI
lines into the "other" comparison group — worse than undercounting, it contaminates the
baseline. Survival must consume the same attribution D produces (measured trailers, plus
recovered PR data when `--pr-data` is given) and must carry the squash caveat whenever it
fires without recovery.

**Steps:**
1. Read `shipsignal/impact.py` (`walk_history` — per-commit added-line counts from numstat
   already exist, as does the AI commit set), `prdata.py` (Package D), `gitinfo.py`.
2. **Blame engine — metadata only.** New `shipsignal/survival.py` running
   `git blame --incremental -w <file>`, which emits attribution ranges (commit sha, line
   counts) and NO file content. This is the only acceptable form — parsing default
   `git blame` output reads source lines and violates the never-read-content rule. State
   that in a code comment at the parser.
3. Mechanics: `git ls-files` the current tree → skip binaries (numstat's `-` convention) →
   per-file incremental blame → surviving-line count per commit → join against the AI/other
   commit sets → per-commit survival = surviving ÷ added.
4. **Age-matching is mandatory.** AI commits are systematically younger, and young lines have
   had less time to die — the naive pooled comparison flatters AI. v1 design: restrict to
   commits ≥ 90 days old inside the shared post-adoption window, bucket by month, compare AI
   vs other survival within matched buckets (+ an age-weighted overall line). A unit test
   must prove the rendered number is NOT the naive pooled one.
5. Withholding floors: either group < 20 commits or < 500 attributed lines → withhold the
   comparison ("not enough matched history to compare") and render coverage only.
6. **Cost control:** opt-in via `--survival` on `impact` and `report` (default off — default
   output stays byte-identical). Deterministic sampling cap (e.g. 400 files / 200k blamed
   lines, stable file order) with the sampling disclosed in the output. Config keys under
   `[impact]` (additive to Package G's schema).
7. Naming + caveats in `glossary.py`: "line survival of AI-assisted commits" — attribution
   is commit-level (humans edit AI output before committing, and vice versa); reformat/rename
   caveat (`-w` only mitigates whitespace); the squash-caveat integration from the dependency
   note.
8. Tests: scripted fixture history (AI + human commits, deletions, a reformat commit);
   incremental-format parser units; the age-matching test from step 4; floors; opt-in
   byte-identity; sampling determinism.
9. Calibration trio — crown is the interesting one (Pervasive adoption). Write up whether
   the numbers are explainable BEFORE merge.
10. Docs checklist: README (flagship section — write the honest framing first, then the
    feature), `docs/getting-started.md`, `CLAUDE.md` (new gotchas: blame is `--incremental`
    only; survival is opt-in), `shipsignal/README.md` (+`survival.py`), CHANGELOG; re-read
    `SECURITY.md` to confirm the zero-network wording still holds (it should — blame is
    local git).

**Acceptance:** survival numbers on a scripted fixture are hand-checkable; the age-matched
comparison is enforced by test; default (no flag) output byte-identical; capped runtime stays
interactive on a chalk-sized repo (measure and document it); withholds below floors; suite +
ruff + dogfood green.

### Train 5 release steps
CHANGELOG → `## [0.11.0]` with a narrative entry (flagship 2 — the acceptance-rate story);
version bumps (both files); tag; PyPI verify; `uvx` smoke. No `action.yml` change — no `v1`
retarget.

---

## Package I — `compare` command: snapshot-free ref-to-ref diff (Train 6)

**Goal:** `trend` requires prior snapshots, so a new user's first delta experience is "come
back later". `shipsignal compare <ref-A> [<ref-B>]` scans two git refs of the same repo and
diffs readiness.

**Steps:**
1. Read `shipsignal/trend.py` (delta rendering to reuse), `snapshot.py` (schema), `gitinfo.py`
   (git helpers), `cli.py`.
2. New subcommand `compare`: `shipsignal compare <target> --from <ref> [--to <ref, default HEAD>]`.
   Materialize each ref read-only — `git worktree add --detach <tmp> <ref>` (clean up in
   `finally`; fall back to `git archive | tar -x` into temp if worktrees are unavailable).
   NEVER touch the user's working tree or index.
3. Run the readiness pipeline on both trees. **Scope: readiness only** — impact is inherently
   longitudinal and `trend` already owns that; say so in the docs.
4. Note: doc-freshness signals need git history; inside a detached worktree `git log` still
   works (shared object store) — verify, and mark freshness *indeterminate* if a case breaks.
5. Render: reuse/extract the trend delta view — score delta, per-category deltas, fixes
   resolved / introduced / unchanged. Text + `--md`/`--html`/`--json`.
6. Honesty rails (mirror `trend`'s): if the `--from` tree predates detectors' assumptions or a
   category flips to n/a, label it rather than implying regression.
7. Tests: fixture repo with two tagged states (one with docs added between them); assert
   deltas and fix-resolution diffs; cleanup-on-error test.
8. Docs: README (new command in Output/commands area), `docs/getting-started.md`, `CLAUDE.md`
   commands, `shipsignal/README.md` if a new module is added, CHANGELOG.

**Acceptance:** `shipsignal compare . --from v0.6.6` runs on this repo and shows real deltas;
no residue in `git worktree list` after runs (including failed ones); suite green.

---

## Package F — `shipsignal fix`: apply the quick wins (Train 6)

**Goal:** the scanner already detects the test command, modules, CI, and ranks fixes with
starter snippets (`snippets.py`). Let it *generate* the scaffolds — grader becomes fixer.

**Steps:**
1. Read `shipsignal/snippets.py`, `scanner.py`, `detectors.py`, and how fixes carry snippets
   into reports.
2. New subcommand `fix`: **dry-run by default** — prints what it would create and the payoff
   estimate per file (reuse the existing ≈+N pts machinery). `--apply` writes.
3. Scope of generatable artifacts (v1, keep tight):
   - Starter `AGENTS.md` (or `CLAUDE.md` — pick ONE default, recommend `AGENTS.md` as the
     vendor-neutral standard; `--style claude` for the other) populated from *detected facts*:
     real test command, real module list, detected CI, detected lint/format tools. No
     placeholder lorem — if a fact wasn't detected, omit the section.
   - Module README stubs for undocumented modules (title + "what/why/key files" skeleton
     seeded with the module's top-level filenames).
   - `.editorconfig` / CONTRIBUTING stub only if the corresponding fix is in the ranked list.
4. Safety rails: NEVER overwrite an existing file (skip + say why); everything written is
   plain text in the target repo; `--apply` prints a summary of files created; respect
   `.gitignore`d module exclusions same as the scanner.
5. Close the loop: after `--apply`, re-run the scorer and print before → after readiness
   (this is the demo moment — "62 → 78 in one command").
6. Tests: dry-run output, apply-once idempotency (second run creates nothing), no-overwrite
   guarantee, generated AGENTS.md contains the fixture repo's real test command.
7. Docs: README (headline feature — new section with the before→after example),
   `docs/getting-started.md`, `CLAUDE.md` commands + a new gotcha ("fix never overwrites"),
   `shipsignal/README.md` module map, CHANGELOG. Consider a README GIF of the before→after.

**Acceptance:** on a bare fixture repo, `fix --apply` measurably raises the score and a
second run is a no-op; on ShipSignal itself, `fix` reports nothing to do (dogfood).

### Train 6 release steps
CHANGELOG → `## [0.12.0]`; version bumps (both files); tag; PyPI verify; smoke.
(Demand-triggered train — let a real user signal start it. Ship I and F in either order; if
one slips, same don't-hold rule as Train 3. F can also be pulled forward as a standalone
quick win between big trains if a demo moment is wanted.)

---

## Global docs checklist (every package PRs against this)

| Artifact | When to touch |
|---|---|
| `README.md` | any user-visible flag, command, output, or promise |
| `CHANGELOG.md` | every package — Keep-a-Changelog format, under `[Unreleased]` until release |
| `CLAUDE.md` | new commands, new conventions/gotchas, changed invariants |
| `shipsignal/README.md` | any new module or pipeline change |
| `docs/getting-started.md` | anything a new user would hit in their first 10 minutes |
| `docs/github-action.md` | any Action input/output/permission change |
| `SECURITY.md` | Package D (reaffirm zero-network posture) — and check on any I/O change |
| `examples/` | regenerate `crown-audit.*` after any report-rendering change |
| GitHub repo metadata | Package C (topics/description/homepage via `gh`), Marketplace listing |
| `action.yml` descriptions | Packages A, B (passthrough examples) |
| PyPI page | auto from README on release — eyeball it after each publish |

## Release mechanics reminder (applies to every train)

1. `[Unreleased]` → versioned CHANGELOG section with date.
2. Bump `pyproject.toml` AND `shipsignal/__init__.py.__version__` (they desynced once).
3. Full suite + ruff + dogfood (`scan . --fail-under 90`) green locally and in CI.
4. Tag strict `vX.Y.Z`, push → OIDC PyPI publish. Verify the PyPI page.
5. If `action.yml` changed: force-retarget `v1` to the release commit and re-run the external
   smoke test.
6. Post-release: `uvx shipsignal@X.Y.Z report <some repo>` as a consumer smoke test.
