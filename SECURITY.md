# Security Policy

## Supported versions

ShipSignal is pre-1.0 and ships from a single active line. Security fixes land on the latest
release — please upgrade to the newest version before reporting.

| Version | Supported |
|---------|-----------|
| 0.6.x   | ✅        |
| < 0.6   | ❌        |

## Reporting a vulnerability

Please report security issues **privately** — don't open a public issue for anything
exploitable.

- **Preferred:** GitHub's private vulnerability reporting on this repo — the **Security** tab →
  **Report a vulnerability**.
- You'll get an acknowledgement as soon as I can manage, and a fix or mitigation plan for
  confirmed issues. ShipSignal is solo-maintained, so response is best-effort — but security
  reports are taken seriously and prioritized.

Low-severity, non-exploitable hardening suggestions are fine to raise as a normal issue.

## Security model

ShipSignal is designed to be safe to point at any repository, including untrusted ones. The
guarantees below are what the "read-only, local, nothing leaves your box" promise actually
means.

**It does:**

- Run **read-only** git commands (`git log`, `git ls-files`, `git rev-list`, and an optional
  `git clone`) as argument lists — never through a shell, so there is no shell-injection
  surface. Git invocations carry `gc.auto=0` / `maintenance.auto=false` so the tool can't even
  incidentally mutate the repo it scans.
- Optionally `git clone` a URL **you explicitly pass** on the command line. That clone is the
  only outbound network action in the entire tool, and it only happens when you point
  ShipSignal at a remote instead of a local path.
- Write output only where you ask (`--json` / `--md` / `--html` / `--badge`) and, with
  `--snapshot`, small JSON records under `.shipsignal/` (gitignored by default).

**It does not:**

- Transmit your code, diffs, findings, or any telemetry anywhere. The package makes **no
  network calls of its own** — no analytics, no phone-home, no `urllib` / `http` / sockets.
- Execute the target repository's code, build scripts, git hooks, or dependencies. It reads
  files and git metadata and *parses* config files (e.g. `package.json`, `pyproject.toml`); it
  never runs them or anything they reference.
- Read credentials, environment secrets, or anything outside the repo path you point it at.

Reports contain findings, metrics, file **paths**, and generated scaffold snippets (skeletons
with `<fill-in>` markers) — **never the contents of your source files or diff text**.
