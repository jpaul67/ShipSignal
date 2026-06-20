"""`shipsignal <scan|impact> <path | url | owner/repo>` — the CLI."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

from . import gitinfo, impact, report, scanner

_SHORTHAND = re.compile(r"^[\w.-]+/[\w.-]+$")


def _looks_like_url(s: str) -> bool:
    return "://" in s or s.startswith("git@") or bool(_SHORTHAND.match(s))


def _resolve_url(target: str) -> str:
    if _SHORTHAND.match(target) and "://" not in target:
        return f"https://github.com/{target}"
    return target


def _resolve_target(
    target: str, treeless: bool = True
) -> tuple[Path | None, str, Path | None, str | None]:
    """Return (root, label, tmp_dir_to_cleanup, error). root is None on error.

    ``treeless`` controls remote clones: Readiness uses a treeless clone; the Impact
    lens passes ``treeless=False`` so ``git log --numstat`` has local blobs.
    """
    local = Path(target)
    if local.exists():
        resolved = local.resolve()
        return resolved, resolved.name, None, None
    if _looks_like_url(target):
        url = _resolve_url(target)
        tmp = Path(tempfile.mkdtemp(prefix="bw_"))
        root = tmp / "repo"
        print(f"  cloning {'(full) ' if not treeless else ''}{url} …")
        ok, err = gitinfo.clone(url, root, treeless=treeless)
        if not ok:
            shutil.rmtree(tmp, ignore_errors=True)
            return None, "", None, f"clone failed: {err.strip()[:200]}"
        return root, target, tmp, None
    return None, "", None, f"not a path or recognizable repo: {target}"


def _cmd_scan(args: argparse.Namespace) -> int:
    root, label, tmp, err = _resolve_target(args.target)
    if err:
        print(f"  {err}", file=sys.stderr)
        return 2
    assert root is not None
    try:
        result = scanner.scan(root, repo_label=label)
        print(report.render(result))
        for path, payload in (
            (args.json, lambda: json.dumps(result, indent=2)),
            (args.md, lambda: report.render_markdown(result)),
            (args.html, lambda: report.render_html(result)),
            (args.badge, lambda: report.render_badge(result)),
        ):
            if path:
                Path(path).write_text(payload(), encoding="utf-8")
                print(f"  wrote {path}")
        if args.fail_under is not None and result["score"] < args.fail_under:
            print(f"  FAIL: score {result['score']} < --fail-under {args.fail_under}",
                  file=sys.stderr)
            return 1
        return 0
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


def _cmd_impact(args: argparse.Namespace) -> int:
    # Impact needs blobs for `git log --numstat` → full clone for remote targets.
    root, label, tmp, err = _resolve_target(args.target, treeless=False)
    if err:
        print(f"  {err}", file=sys.stderr)
        return 2
    assert root is not None
    try:
        # Readiness runs by default so the three-number header is always complete.
        # --no-readiness skips it (e.g. to save a few seconds on a huge repo).
        readiness_score: int | None = None
        if not args.no_readiness:
            try:
                readiness_score = scanner.scan(root, repo_label=label)["score"]
            except Exception as exc:  # pragma: no cover
                print(f"  warning: readiness scan failed ({exc}); readiness will show n/a",
                      file=sys.stderr)
        result = impact.compute_impact(
            root,
            repo_label=label,
            adoption_date_override=args.adoption_date,
            readiness_score=readiness_score,
        )
        print(report.render_impact(result))
        if args.timeline:
            print(report.render_trajectory_cli(result))
        for path, payload in (
            (args.json, lambda: json.dumps(result, indent=2, default=str)),
            (args.md, lambda: report.render_impact_markdown(result)),
            (args.html, lambda: report.render_impact_html(result)),
        ):
            if path:
                Path(path).write_text(payload(), encoding="utf-8")
                print(f"  wrote {path}")
        return 0
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


def _cmd_report(args: argparse.Namespace) -> int:
    """Unified audit: run both lenses, emit one combined deliverable."""
    # Report runs the Impact lens too → full clone for remote targets.
    root, label, tmp, err = _resolve_target(args.target, treeless=False)
    if err:
        print(f"  {err}", file=sys.stderr)
        return 2
    assert root is not None
    try:
        readiness_result = scanner.scan(root, repo_label=label)
        impact_result = impact.compute_impact(
            root,
            repo_label=label,
            adoption_date_override=args.adoption_date,
            readiness_score=readiness_result.get("score"),
        )
        print(report.render_unified(impact_result, readiness_result))
        if args.timeline:
            print(report.render_trajectory_cli(impact_result))

        combined = {
            "schema_version": "report-0.1",
            "repo": label,
            "impact": impact_result,
            "readiness": readiness_result,
        }
        for path, payload in (
            (args.json, lambda: json.dumps(combined, indent=2, default=str)),
            (args.md, lambda: report.render_unified_markdown(impact_result, readiness_result)),
            (args.html, lambda: report.render_unified_html(impact_result, readiness_result)),
        ):
            if path:
                Path(path).write_text(payload(), encoding="utf-8")
                print(f"  wrote {path}")
        return 0
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # avoid cp1252 crashes on Windows
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        prog="shipsignal",
        description="AI readiness & impact scanner — local, read-only.",
    )
    sub = parser.add_subparsers(dest="cmd")

    scan_p = sub.add_parser("scan", help="readiness lens — is the repo set up for agents?")
    scan_p.add_argument("target", help="local path, https git URL, or owner/repo")
    scan_p.add_argument("--json", metavar="FILE", help="write readiness.json to FILE")
    scan_p.add_argument("--md", metavar="FILE", help="write a Markdown report to FILE")
    scan_p.add_argument("--html", metavar="FILE", help="write an HTML report to FILE")
    scan_p.add_argument("--badge", metavar="FILE", help="write a readiness badge SVG to FILE")
    scan_p.add_argument("--fail-under", type=int, default=None, metavar="N",
                        help="exit non-zero if the score is below N")

    impact_p = sub.add_parser("impact", help="impact lens — is AI changing how the team ships?")
    impact_p.add_argument("target", help="local path, https git URL, or owner/repo")
    impact_p.add_argument("--json", metavar="FILE", help="write impact.json to FILE")
    impact_p.add_argument("--md", metavar="FILE", help="write a Markdown report to FILE")
    impact_p.add_argument("--html", metavar="FILE", help="write an HTML report to FILE")
    impact_p.add_argument("--adoption-date", metavar="YYYY-MM-DD", default=None,
                          help="override the auto-detected adoption date")
    impact_p.add_argument("--no-readiness", action="store_true",
                          help="skip the readiness scan (the Readiness number shows n/a)")
    impact_p.add_argument("--timeline", action="store_true",
                          help="show the over-time trajectory (adoption + delivery health)")

    report_p = sub.add_parser("report", help="unified audit: both lenses, one deliverable")
    report_p.add_argument("target", help="local path, https git URL, or owner/repo")
    report_p.add_argument("--json", metavar="FILE", help="write the combined JSON to FILE")
    report_p.add_argument("--md", metavar="FILE", help="write a unified Markdown report to FILE")
    report_p.add_argument("--html", metavar="FILE", help="write a unified HTML report to FILE")
    report_p.add_argument("--adoption-date", metavar="YYYY-MM-DD", default=None,
                          help="override the auto-detected adoption date")
    report_p.add_argument("--timeline", action="store_true",
                          help="show the over-time trajectory (adoption + delivery health)")

    args = parser.parse_args(argv)
    if args.cmd == "scan":
        return _cmd_scan(args)
    if args.cmd == "impact":
        return _cmd_impact(args)
    if args.cmd == "report":
        return _cmd_report(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
