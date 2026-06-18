"""`bellwether scan <path | url | owner/repo>` — the v0 CLI."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

from . import gitinfo, report, scanner

_SHORTHAND = re.compile(r"^[\w.-]+/[\w.-]+$")


def _looks_like_url(s: str) -> bool:
    return "://" in s or s.startswith("git@") or bool(_SHORTHAND.match(s))


def _resolve_url(target: str) -> str:
    if _SHORTHAND.match(target) and "://" not in target:
        return f"https://github.com/{target}"
    return target


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # avoid cp1252 crashes on Windows
        except Exception:
            pass

    parser = argparse.ArgumentParser(prog="bellwether", description="Agent-readiness scanner")
    sub = parser.add_subparsers(dest="cmd")
    scan_p = sub.add_parser("scan", help="scan a local path or a public repo")
    scan_p.add_argument("target", help="local path, https git URL, or owner/repo")
    scan_p.add_argument("--json", metavar="FILE", help="write readiness.json to FILE")
    scan_p.add_argument("--md", metavar="FILE", help="write a Markdown report to FILE")
    scan_p.add_argument("--html", metavar="FILE", help="write an HTML report to FILE")
    scan_p.add_argument("--badge", metavar="FILE", help="write a readiness badge SVG to FILE")
    scan_p.add_argument("--fail-under", type=int, default=None, metavar="N",
                        help="exit non-zero if the score is below N")
    args = parser.parse_args(argv)

    if args.cmd != "scan":
        parser.print_help()
        return 2

    target = args.target
    tmp: Path | None = None
    try:
        local = Path(target)
        if local.exists():
            root, label = local.resolve(), local.resolve().name
        elif _looks_like_url(target):
            url = _resolve_url(target)
            tmp = Path(tempfile.mkdtemp(prefix="bw_"))
            root = tmp / "repo"
            print(f"  cloning {url} …")
            ok, err = gitinfo.clone(url, root)
            if not ok:
                print(f"  clone failed: {err.strip()[:200]}", file=sys.stderr)
                return 2
            label = target
        else:
            print(f"  not a path or recognizable repo: {target}", file=sys.stderr)
            return 2

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
            print(f"  FAIL: score {result['score']} < --fail-under {args.fail_under}", file=sys.stderr)
            return 1
        return 0
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
