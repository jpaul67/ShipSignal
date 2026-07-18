"""`shipsignal <scan|impact> <path | url | owner/repo>` — the CLI."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

from . import ansi, config, gitinfo, impact, prdata, report, scanner, snapshot, trend

_SHORTHAND = re.compile(r"^[\w.-]+/[\w.-]+$")

# Sentinel value for argparse: --snapshot with no PATH arg uses the default
# location; --snapshot PATH uses the given file; flag absent => no snapshot.
_SNAPSHOT_DEFAULT = "__SHIPSIGNAL_SNAPSHOT_DEFAULT__"


def _maybe_write_snapshot(args_value, *, readiness=None, impact_result=None,
                          repo_label: str | None = None, root: Path | None = None) -> None:
    """Translate the --snapshot CLI value into an actual file write, if requested."""
    if args_value is None:
        return
    snap = snapshot.build_snapshot(
        readiness=readiness, impact=impact_result,
        repo_label=repo_label, root=root,
    )
    if args_value == _SNAPSHOT_DEFAULT:
        assert root is not None
        out_path = snapshot.default_snapshot_path(
            root, snap.get("commit_sha"), snap.get("commit_date"),
        )
    else:
        out_path = Path(args_value)
    snapshot.write_snapshot(snap, out_path)
    print(f"  wrote snapshot {out_path}")


def _load_config(root: Path) -> config.Config:
    """Load `.shipsignal.toml` and print any warnings (unknown/mistyped keys,
    a malformed file) to stderr. Never raises — a config typo degrades to
    defaults, it never blocks a scan."""
    cfg, warnings = config.load_config(root)
    for w in warnings:
        print(f"  config: {w}", file=sys.stderr)
    return cfg


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
        cfg = _load_config(root)
        fail_under = args.fail_under if args.fail_under is not None else cfg.readiness.fail_under
        result = scanner.scan(root, repo_label=label, exclude_modules=cfg.readiness.exclude_modules)
        print(report.render(result, color=ansi.resolve_enabled(args.no_color)))
        for path, payload in (
            (args.json, lambda: json.dumps(result, indent=2)),
            (args.md, lambda: report.render_markdown(result)),
            (args.html, lambda: report.render_html(result)),
            (args.badge, lambda: report.render_badge(result, label=cfg.report.badge_label)),
            (args.badge_json,
             lambda: report.render_badge_json(result, label=cfg.report.badge_label)),
        ):
            if path:
                Path(path).write_text(payload(), encoding="utf-8")
                print(f"  wrote {path}")
        _maybe_write_snapshot(args.snapshot, readiness=result,
                              repo_label=label, root=root)
        if fail_under is not None and result["score"] < fail_under:
            print(f"  FAIL: score {result['score']} < --fail-under {fail_under}",
                  file=sys.stderr)
            return 1
        return 0
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


def _load_pr_data(args: argparse.Namespace) -> tuple[prdata.PRData | None, int | None]:
    """Load --pr-data (Package D squash-recovery) if given. Returns
    (pr_data, exit_code): a malformed file the user explicitly passed is a usage
    error — print it and exit 2, never degrade to a silent zero."""
    path = getattr(args, "pr_data", None)
    if not path:
        return None, None
    try:
        return prdata.load_pr_data(Path(path)), None
    except prdata.PRDataError as exc:
        print(f"  error: {exc}", file=sys.stderr)
        return None, 2


def _cmd_impact(args: argparse.Namespace) -> int:
    # Impact needs blobs for `git log --numstat` → full clone for remote targets.
    root, label, tmp, err = _resolve_target(args.target, treeless=False)
    if err:
        print(f"  {err}", file=sys.stderr)
        return 2
    assert root is not None
    try:
        cfg = _load_config(root)
        squash_override = args.squash if args.squash is not None else bool(cfg.impact.squash)
        pr_data, prd_err = _load_pr_data(args)
        if prd_err is not None:
            return prd_err
        # Readiness runs by default so the three-number header is always complete.
        # --no-readiness skips it (e.g. to save a few seconds on a huge repo).
        readiness_score: int | None = None
        if not args.no_readiness:
            try:
                readiness_score = scanner.scan(
                    root, repo_label=label, exclude_modules=cfg.readiness.exclude_modules
                )["score"]
            except Exception as exc:  # pragma: no cover
                print(f"  warning: readiness scan failed ({exc}); readiness will show n/a",
                      file=sys.stderr)
        with impact.extra_aliases(cfg.impact.extra_ai_aliases):
            result = impact.compute_impact(
                root,
                repo_label=label,
                adoption_date_override=args.adoption_date,
                readiness_score=readiness_score,
                squash_override=squash_override,
                release_tag_pattern=cfg.impact.release_tag_pattern,
                pr_data=pr_data,
            )
        print(report.render_impact(result, color=ansi.resolve_enabled(args.no_color)))
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
        _maybe_write_snapshot(args.snapshot, impact_result=result,
                              repo_label=label, root=root)
        return 0
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


def _cmd_trend(args: argparse.Namespace) -> int:
    """Visual snapshot viewer (S2). Reads .shipsignal/snapshots/, renders
    the delta view. Never re-scans — strictly local, offline, fast."""
    target = Path(args.target)
    if not target.exists():
        print(f"  not a path: {args.target}", file=sys.stderr)
        return 2
    snapshots = snapshot.load_snapshots(target)
    snapshots = snapshot.filter_snapshots(snapshots, since=args.since, limit=args.limit)
    trend_result = trend.compute_trend(snapshots)
    print(report.render_trend(trend_result))
    for path, payload in (
        (args.json, lambda: json.dumps(trend_result, indent=2, default=str)),
        (args.md, lambda: report.render_trend_markdown(trend_result)),
        (args.html, lambda: report.render_trend_html(trend_result)),
    ):
        if path:
            Path(path).write_text(payload(), encoding="utf-8")
            print(f"  wrote {path}")
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    """Unified audit: run both lenses, emit one combined deliverable."""
    # Report runs the Impact lens too → full clone for remote targets.
    root, label, tmp, err = _resolve_target(args.target, treeless=False)
    if err:
        print(f"  {err}", file=sys.stderr)
        return 2
    assert root is not None
    try:
        cfg = _load_config(root)
        squash_override = args.squash if args.squash is not None else bool(cfg.impact.squash)
        pr_data, prd_err = _load_pr_data(args)
        if prd_err is not None:
            return prd_err
        readiness_result = scanner.scan(
            root, repo_label=label, exclude_modules=cfg.readiness.exclude_modules
        )
        with impact.extra_aliases(cfg.impact.extra_ai_aliases):
            impact_result = impact.compute_impact(
                root,
                repo_label=label,
                adoption_date_override=args.adoption_date,
                readiness_score=readiness_result.get("score"),
                squash_override=squash_override,
                release_tag_pattern=cfg.impact.release_tag_pattern,
                pr_data=pr_data,
            )
        print(report.render_unified(impact_result, readiness_result,
                                    color=ansi.resolve_enabled(args.no_color)))
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
            (args.badge_json, lambda: report.render_badge_json(readiness_result,
                                                                label=cfg.report.badge_label)),
        ):
            if path:
                Path(path).write_text(payload(), encoding="utf-8")
                print(f"  wrote {path}")
        _maybe_write_snapshot(args.snapshot, readiness=readiness_result,
                              impact_result=impact_result, repo_label=label, root=root)
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
    try:
        _version = importlib.metadata.version("shipsignal")
    except importlib.metadata.PackageNotFoundError:
        _version = "0+unknown"
    parser.add_argument("--version", action="version", version=f"shipsignal {_version}")
    sub = parser.add_subparsers(dest="cmd")

    scan_p = sub.add_parser("scan", help="readiness lens — is the repo set up for agents?")
    scan_p.add_argument("target", help="local path, https git URL, or owner/repo")
    scan_p.add_argument("--json", metavar="FILE", help="write readiness.json to FILE")
    scan_p.add_argument("--md", metavar="FILE", help="write a Markdown report to FILE")
    scan_p.add_argument("--html", metavar="FILE", help="write an HTML report to FILE")
    scan_p.add_argument("--badge", metavar="FILE", help="write a readiness badge SVG to FILE")
    scan_p.add_argument("--badge-json", metavar="FILE",
                        help="write a shields.io endpoint-badge JSON to FILE — publish it "
                             "(e.g. to a gist) for a live README badge that never goes stale")
    scan_p.add_argument("--snapshot", nargs="?", const=_SNAPSHOT_DEFAULT, default=None,
                        metavar="PATH",
                        help="persist a small JSON snapshot for `shipsignal trend` "
                             "(default location: .shipsignal/snapshots/YYYY-MM-DD-<sha>.json)")
    scan_p.add_argument("--fail-under", type=int, default=None, metavar="N",
                        help="exit non-zero if the score is below N "
                             "(default: .shipsignal.toml's [readiness].fail_under, else no gate)")
    scan_p.add_argument("--no-color", action="store_true",
                        help="disable ANSI color in terminal output (also honors NO_COLOR)")

    impact_p = sub.add_parser("impact", help="impact lens — is AI changing how the team ships?")
    impact_p.add_argument("target", help="local path, https git URL, or owner/repo")
    impact_p.add_argument("--json", metavar="FILE", help="write impact.json to FILE")
    impact_p.add_argument("--md", metavar="FILE", help="write a Markdown report to FILE")
    impact_p.add_argument("--html", metavar="FILE", help="write an HTML report to FILE")
    impact_p.add_argument("--adoption-date", metavar="YYYY-MM-DD", default=None,
                          help="override the auto-detected adoption date")
    impact_p.add_argument("--no-readiness", action="store_true",
                          help="skip the readiness scan (the Readiness number shows n/a)")
    impact_p.add_argument("--squash", action="store_true", default=None,
                          help="treat the history as squash-merged — flag AI adoption as a "
                               "floor (for workflows whose squash commits lack a (#NNN) subject) "
                               "(default: .shipsignal.toml's [impact].squash, else off)")
    impact_p.add_argument("--pr-data", metavar="FILE", default=None,
                          help="recover AI attribution dropped by a squash/merge pipeline from an "
                               "exported PR-data file (zero network: you run the gh export, "
                               "ShipSignal reads the local file) — see docs/getting-started.md")
    impact_p.add_argument("--timeline", action="store_true",
                          help="show the over-time trajectory (adoption + delivery health)")
    impact_p.add_argument("--snapshot", nargs="?", const=_SNAPSHOT_DEFAULT, default=None,
                          metavar="PATH",
                          help="persist a small JSON snapshot for `shipsignal trend` "
                               "(default: .shipsignal/snapshots/YYYY-MM-DD-<sha>.json)")
    impact_p.add_argument("--no-color", action="store_true",
                          help="disable ANSI color in terminal output (also honors NO_COLOR)")

    report_p = sub.add_parser("report", help="unified audit: both lenses, one deliverable")
    report_p.add_argument("target", help="local path, https git URL, or owner/repo")
    report_p.add_argument("--json", metavar="FILE", help="write the combined JSON to FILE")
    report_p.add_argument("--md", metavar="FILE", help="write a unified Markdown report to FILE")
    report_p.add_argument("--html", metavar="FILE", help="write a unified HTML report to FILE")
    report_p.add_argument("--badge-json", metavar="FILE",
                          help="write a shields.io endpoint-badge JSON (readiness score) to "
                               "FILE — publish it (e.g. to a gist) for a live README badge")
    report_p.add_argument("--adoption-date", metavar="YYYY-MM-DD", default=None,
                          help="override the auto-detected adoption date")
    report_p.add_argument("--timeline", action="store_true",
                          help="show the over-time trajectory (adoption + delivery health)")
    report_p.add_argument("--squash", action="store_true", default=None,
                          help="treat the history as squash-merged — flag AI adoption as a "
                               "floor (for workflows whose squash commits lack a (#NNN) subject) "
                               "(default: .shipsignal.toml's [impact].squash, else off)")
    report_p.add_argument("--pr-data", metavar="FILE", default=None,
                          help="recover AI attribution dropped by a squash/merge pipeline from an "
                               "exported PR-data file (zero network: you run the gh export, "
                               "ShipSignal reads the local file) — see docs/getting-started.md")
    report_p.add_argument("--snapshot", nargs="?", const=_SNAPSHOT_DEFAULT, default=None,
                          metavar="PATH",
                          help="persist a small JSON snapshot for `shipsignal trend` "
                               "(default: .shipsignal/snapshots/YYYY-MM-DD-<sha>.json)")
    report_p.add_argument("--no-color", action="store_true",
                          help="disable ANSI color in terminal output (also honors NO_COLOR)")

    trend_p = sub.add_parser(
        "trend",
        help="view the trend across snapshots (no re-scan; reads .shipsignal/snapshots/)",
    )
    trend_p.add_argument("target", nargs="?", default=".",
                         help="repo root containing .shipsignal/snapshots/ (default: .)")
    trend_p.add_argument("--limit", type=int, default=4, metavar="N",
                         help="show the most-recent N snapshots (default: 4)")
    trend_p.add_argument("--since", default=None, metavar="YYYY-MM-DD",
                         help="only snapshots whose commit_date is on/after this date")
    trend_p.add_argument("--json", metavar="FILE", help="write the trend payload to FILE")
    trend_p.add_argument("--md", metavar="FILE", help="write a Markdown trend report to FILE")
    trend_p.add_argument("--html", metavar="FILE", help="write an HTML trend view to FILE")

    args = parser.parse_args(argv)
    if args.cmd == "scan":
        return _cmd_scan(args)
    if args.cmd == "impact":
        return _cmd_impact(args)
    if args.cmd == "report":
        return _cmd_report(args)
    if args.cmd == "trend":
        return _cmd_trend(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
