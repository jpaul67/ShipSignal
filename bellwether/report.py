"""Rendering: CLI text, Markdown/HTML reports, and a badge SVG."""
from __future__ import annotations

from html import escape as _esc

from . import __version__

GRADE_COLOR = {"A": "#4c1", "B": "#97ca00", "C": "#dfb317", "D": "#fe7d37", "F": "#e05d44"}


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


def _cat_rows(result):
    for c in result["categories"]:
        if c["status"] == "scored":
            yield c["id"], f"{c['points']:g}/{c['max']:g}", 100 * c["points"] / c["max"] if c["max"] else 0
        else:
            yield c["id"], c["status"], None


def render_markdown(result: dict) -> str:
    L = [f"# Bellwether — AI readiness: {result['repo']}", "",
         f"**Score: {result['score']}/100 — grade {result['grade']}**", "",
         "| Category | Score |", "|---|---|"]
    for cid, val, _pct in _cat_rows(result):
        L.append(f"| {cid} | {val} |")
    warns = [f for f in result["findings"] if f["severity"] != "info"]
    infos = [f for f in result["findings"] if f["severity"] == "info"]
    if warns:
        L += ["", "## Fixes", ""]
        L += [f"- **{f['path']}** — {f['evidence']}  \n  → {f['fix']}" for f in warns]
    if infos:
        L += ["", "## Optional", ""]
        L += [f"- {f['path']} — {f['evidence']}" for f in infos]
    L += ["", f"<sub>bellwether v{__version__} · {result['scanned_at']}</sub>", ""]
    return "\n".join(L)


def render_html(result: dict) -> str:
    color = GRADE_COLOR.get(result["grade"], "#9f9f9f")
    rows = ""
    for cid, val, pct in _cat_rows(result):
        if pct is None:
            rows += (f'<div class="row"><div class="cat">{_esc(cid)}</div>'
                     f'<div class="bar na"></div><div class="num">{_esc(val)}</div></div>')
        else:
            rows += (f'<div class="row"><div class="cat">{_esc(cid)}</div>'
                     f'<div class="bar"><span style="width:{pct:.0f}%"></span></div>'
                     f'<div class="num">{_esc(val)}</div></div>')
    warns = [f for f in result["findings"] if f["severity"] != "info"]
    fixes = "".join(
        f'<li><b>{_esc(f["path"])}</b> — {_esc(f["evidence"])}'
        f'<br><span class="fix">→ {_esc(f["fix"])}</span></li>' for f in warns
    ) or "<li>None — nicely set up. ✓</li>"
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>AI readiness — {_esc(result['repo'])}</title><style>
body{{font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;max-width:760px;margin:40px auto;padding:0 20px;color:#1a1a1a}}
h1{{font-size:18px;margin-bottom:2px}}.sub{{color:#888;margin-bottom:18px}}
.score{{font-size:48px;font-weight:700}}.slash{{color:#bbb;font-size:24px}}
.grade{{display:inline-block;color:#fff;background:{color};border-radius:6px;padding:2px 12px;font-size:20px;vertical-align:middle;margin-left:10px}}
.row{{display:flex;align-items:center;margin:6px 0}}.cat{{width:170px;color:#555}}
.bar{{flex:1;background:#eee;border-radius:4px;height:14px;overflow:hidden;margin:0 10px}}
.bar span{{display:block;height:100%;background:{color}}}
.bar.na{{background:repeating-linear-gradient(45deg,#eee,#eee 4px,#f6f6f6 4px,#f6f6f6 8px)}}
.num{{width:74px;text-align:right;color:#333}}h2{{font-size:15px;margin-top:28px}}
ul{{padding-left:18px}}li{{margin:8px 0}}.fix{{color:#666}}sub{{color:#aaa}}
</style></head><body>
<h1>Bellwether — AI readiness</h1><div class="sub">{_esc(result['repo'])}</div>
<p><span class="score">{result['score']}</span><span class="slash">/100</span>
<span class="grade">{_esc(result['grade'])}</span></p>
{rows}
<h2>Top fixes ({len(warns)})</h2><ul>{fixes}</ul>
<p><sub>bellwether v{__version__} · {_esc(result['scanned_at'])}</sub></p>
</body></html>"""


def render_badge(result: dict) -> str:
    label, value = "AI readiness", f"{result['score']}/100"
    color = GRADE_COLOR.get(result["grade"], "#9f9f9f")
    lw, rw = int(len(label) * 6.5) + 12, int(len(value) * 6.5) + 12
    w = lw + rw
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="20" role="img" aria-label="{label}: {value}">
<linearGradient id="s" x2="0" y2="100%"><stop offset="0" stop-color="#bbb" stop-opacity=".1"/><stop offset="1" stop-opacity=".1"/></linearGradient>
<rect rx="3" width="{w}" height="20" fill="#555"/>
<rect rx="3" x="{lw}" width="{rw}" height="20" fill="{color}"/>
<rect rx="3" width="{w}" height="20" fill="url(#s)"/>
<g fill="#fff" text-anchor="middle" font-family="Verdana,DejaVu Sans,sans-serif" font-size="11">
<text x="{lw / 2:.0f}" y="14">{label}</text>
<text x="{lw + rw / 2:.0f}" y="14">{value}</text>
</g></svg>"""
