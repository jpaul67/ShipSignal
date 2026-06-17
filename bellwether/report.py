"""Human-readable CLI rendering of a scan result."""
from __future__ import annotations


def _bar(points, maximum, width: int = 16) -> str:
    filled = int(round(width * (points / maximum))) if maximum else 0
    filled = max(0, min(width, filled))
    return "█" * filled + "░" * (width - filled)


def render(result: dict) -> str:
    out = []
    out.append("")
    out.append(f"  Bellwether agent-readiness — {result['repo']}")
    out.append(f"  Score: {result['score']}/100   (grade {result['grade']})")
    out.append("")
    for c in result["categories"]:
        cid = c["id"]
        if c["status"] == "scored":
            pts, mx = c["points"], c["max"]
            out.append(f"  {cid:<20} {_bar(pts, mx)} {pts:g}/{mx:g}")
        else:
            out.append(f"  {cid:<20} {'·' * 16} {c['status']}")

    findings = result.get("findings", [])
    warns = [f for f in findings if f["severity"] != "info"]
    if warns:
        out.append("")
        out.append(f"  Top fixes ({len(warns)} issues):")
        for f in warns[:8]:
            out.append(f"   • [{f['severity']}] {f['path']}: {f['evidence']}")
            out.append(f"       → {f['fix']}")
        if len(warns) > 8:
            out.append(f"   … and {len(warns) - 8} more")
    out.append("")
    return "\n".join(out)
