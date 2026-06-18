"""Rendering: CLI text, Markdown/HTML reports, and a badge SVG."""
from __future__ import annotations

from html import escape as _esc

from . import __version__

GRADE_COLOR = {"A": "#4c1", "B": "#97ca00", "C": "#dfb317", "D": "#fe7d37", "F": "#e05d44"}

_SPARK = "▁▂▃▄▅▆▇█"


def _bar(points, maximum, width: int = 16) -> str:
    filled = int(round(width * (points / maximum))) if maximum else 0
    filled = max(0, min(width, filled))
    return "█" * filled + "░" * (width - filled)


def _sparkline(values: list[float], max_val: float | None = None) -> str:
    if not values:
        return ""
    mx = max_val if max_val is not None else max(values)
    if mx <= 0:
        return _SPARK[0] * len(values)
    return "".join(_SPARK[min(7, int(v / mx * 7))] for v in values)


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


# ---------------------------------------------------------------------------
# Impact lens renderers
# ---------------------------------------------------------------------------
def _adoption_headline(adoption: dict) -> str:
    pct = adoption["ai_coauthor_share"] * 100
    return (f"AI co-author share: {pct:.1f}% "
            f"({adoption['ai_commits']}/{adoption['total_commits']} commits, lower bound)")


def render_impact(result: dict) -> str:
    L: list[str] = ["", f"  Bellwether impact lens — {result['repo']}"]
    if result.get("error"):
        L += [f"  error: {result['error']}", ""]
        return "\n".join(L)

    w = result["window"]
    L.append(f"  Window: {w['first_commit']} → {w['last_commit']}  ({w['weeks']} weeks)")
    L.append("")

    # AI adoption — the direct, AI-specific signal.
    ad = result["adoption"]
    L.append(f"  {_adoption_headline(ad)}")
    if ad.get("adoption_date"):
        L.append(f"  Adoption date: {ad['adoption_date']}"
                 f"  ({'auto' if ad['adoption_auto_detected'] else 'override'})")
    if ad.get("per_tool"):
        tools = ", ".join(f"{k} {v}" for k, v in ad["per_tool"].items())
        L.append(f"  Per tool: {tools}")
    series = ad.get("weekly_series", [])
    if series:
        rates = [s[1] for s in series]
        L.append(f"  AI rate / week: {_sparkline(rates, max_val=1.0)}  (0–100%, {len(series)} wks)")
    L.append("")

    # Enablement Score (when earned).
    status = result.get("score_status")
    if status == "scored":
        L.append(f"  Enablement Score: {result['score']}/100")
        for p in result.get("pillars", []):
            if p.get("pts") is None:
                L.append(f"   {p['id']:<20} {'·' * 16} {p.get('status','n/a')}  ({p['basis']})")
            else:
                L.append(f"   {p['id']:<20} {_bar(p['pts'], p['max'])} "
                         f"{p['pts']:g}/{p['max']:g}  ({p['basis']})")
    else:
        reason = result.get("score_withheld_reason") or "see confidence"
        L.append(f"  Enablement Score: WITHHELD — {reason}")
    L.append("")

    # Delivery profile (general health, NOT causal).
    m = result["metrics"]
    f, cs, q, p = m["flow"], m["change_shape"], m["quality"], m["people"]
    L.append("  Delivery profile (general health, not causal):")
    L.append(f"   flow         commits/wk {f['commits_per_week']:g},  "
             f"active-day ratio {f['active_day_ratio']:g}")
    L.append(f"   change-shape median {cs['median_lines']} lines / "
             f"{cs['median_files']} files,  large-change rate {cs['large_change_rate']:.1%}")
    t2c = q['test_to_code_ratio']
    t2c_s = f"{t2c:.1%}" if t2c is not None else "n/a (no code-touching commits)"
    L.append(f"   quality      fix/revert rate {q['fix_rate']:.1%},  "
             f"test-to-code co-change {t2c_s}")
    if p["solo"]:
        L.append(f"   people       SOLO author — concentration/bus-factor metrics suppressed")
    else:
        L.append(f"   people       {p['contributors']} contributors, "
                 f"top share {p['top_author_share']:.1%},  bus-factor {p['bus_factor']}")
    L.append("")

    L.append(f"  Attribution caveat: {result['attribution_caveat']}")
    L.append("")
    return "\n".join(L)


def render_impact_markdown(result: dict) -> str:
    if result.get("error"):
        return f"# Bellwether impact — {result['repo']}\n\n**Error:** {result['error']}\n"
    w = result["window"]
    ad = result["adoption"]
    m = result["metrics"]
    f, cs, q, p = m["flow"], m["change_shape"], m["quality"], m["people"]

    L = [f"# Bellwether — AI impact lens: {result['repo']}", "",
         f"**Window:** {w['first_commit']} → {w['last_commit']} ({w['weeks']} weeks)", ""]

    L += ["## AI adoption (direct, in-repo signal)", "",
          f"- **{_adoption_headline(ad)}**",
          f"- Reported as a **lower bound** — squash-merges drop trailers."]
    if ad.get("adoption_date"):
        L.append(f"- Adoption date: `{ad['adoption_date']}` "
                 f"({'auto-detected' if ad['adoption_auto_detected'] else 'override'})")
    if ad.get("per_tool"):
        L.append("- Per tool: " + ", ".join(f"`{k}` ({v})" for k, v in ad["per_tool"].items()))
    L.append("")

    L += ["## Enablement Score", ""]
    if result.get("score_status") == "scored":
        L.append(f"**Score: {result['score']}/100**")
        L += ["", "| Pillar | Score | Basis |", "|---|---|---|"]
        for pl in result.get("pillars", []):
            val = f"{pl['pts']:g}/{pl['max']:g}" if pl.get("pts") is not None else pl.get("status","n/a")
            L.append(f"| {pl['id']} | {val} | {pl['basis']} |")
    else:
        L.append(f"**Withheld** — {result.get('score_withheld_reason','see confidence')}")
        L.append("")
        L.append("The lens refuses to score when history is too thin or AI was present from "
                 "inception (no pre-AI baseline). The adoption signal and delivery profile "
                 "below are still informative; they are not a verdict.")
    L.append("")

    t2c = q["test_to_code_ratio"]
    t2c_md = "n/a" if t2c is None else f"{t2c:.1%}"
    solo_note = "(solo — pillar metrics suppressed)" if p["solo"] else ""
    L += ["## Delivery profile (general health — NOT causal)", "",
          "| Family | Metric | Value |", "|---|---|---|",
          f"| Flow | commits / week | {f['commits_per_week']:g} |",
          f"| Flow | active-day ratio | {f['active_day_ratio']:g} |",
          f"| Change shape | median lines / commit | {cs['median_lines']} |",
          f"| Change shape | p90 lines / commit | {cs['p90_lines']} |",
          f"| Change shape | large-change rate (>400 lines) | {cs['large_change_rate']:.1%} |",
          f"| Quality | fix/revert subject rate | {q['fix_rate']:.1%} |",
          f"| Quality | test-to-code co-change | {t2c_md} |",
          f"| People | contributors | {p['contributors']} {solo_note} |"]
    if not p["solo"]:
        L += [f"| People | top-author share | {p['top_author_share']:.1%} |",
              f"| People | bus-factor (50% coverage) | {p['bus_factor']} |"]
    L.append("")

    L += ["## Attribution caveat", "", f"> {result['attribution_caveat']}", "",
          f"<sub>bellwether v{__version__} · {result['scanned_at']}</sub>", ""]
    return "\n".join(L)


def render_impact_html(result: dict) -> str:
    if result.get("error"):
        return (f"<!doctype html><meta charset='utf-8'><title>impact error</title>"
                f"<h1>Bellwether impact — {_esc(result['repo'])}</h1>"
                f"<p><b>Error:</b> {_esc(result['error'])}</p>")
    w = result["window"]
    ad = result["adoption"]
    m = result["metrics"]
    f, cs, q, p = m["flow"], m["change_shape"], m["quality"], m["people"]
    pct = ad["ai_coauthor_share"] * 100
    series_rates = [s[1] for s in ad.get("weekly_series", [])]
    spark = _esc(_sparkline(series_rates, max_val=1.0)) if series_rates else ""

    if result.get("score_status") == "scored":
        rows = "".join(
            f"<div class='row'><div class='cat'>{_esc(p['id'])}</div>"
            f"<div class='bar'><span style='width:{100*p['pts']/p['max']:.0f}%'></span></div>"
            f"<div class='num'>{p['pts']:g}/{p['max']:g}</div></div>"
            if p.get("pts") is not None else
            f"<div class='row'><div class='cat'>{_esc(p['id'])}</div>"
            f"<div class='bar na'></div><div class='num'>{_esc(p.get('status','n/a'))}</div></div>"
            for p in result.get("pillars", [])
        )
        score_block = (f"<p><span class='score'>{result['score']}</span>"
                       f"<span class='slash'>/100</span></p>{rows}")
    else:
        score_block = (f"<div class='withheld'><b>Score withheld</b> — "
                       f"{_esc(result.get('score_withheld_reason','see confidence'))}<br>"
                       f"<span class='hint'>The lens refuses to score when history is too thin "
                       f"or AI was present from inception (no pre-AI baseline).</span></div>")

    people_row = (f"SOLO author — pillar metrics suppressed" if p["solo"] else
                  f"{p['contributors']} contributors · top {p['top_author_share']:.1%} · "
                  f"bus-factor {p['bus_factor']}")
    t2c = q['test_to_code_ratio']
    t2c_s = "n/a" if t2c is None else f"{t2c:.1%}"

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>AI impact — {_esc(result['repo'])}</title><style>
body{{font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;max-width:760px;margin:40px auto;padding:0 20px;color:#1a1a1a}}
h1{{font-size:18px;margin-bottom:2px}}.sub{{color:#888;margin-bottom:18px}}
.score{{font-size:48px;font-weight:700}}.slash{{color:#bbb;font-size:24px}}
.row{{display:flex;align-items:center;margin:6px 0}}.cat{{width:180px;color:#555}}
.bar{{flex:1;background:#eee;border-radius:4px;height:14px;overflow:hidden;margin:0 10px}}
.bar span{{display:block;height:100%;background:#4c1}}
.bar.na{{background:repeating-linear-gradient(45deg,#eee,#eee 4px,#f6f6f6 4px,#f6f6f6 8px)}}
.num{{width:90px;text-align:right;color:#333}}
.headline{{background:#f4f8ff;border-left:4px solid #4477dd;padding:12px 16px;border-radius:0 6px 6px 0;margin:14px 0}}
.headline b{{font-size:18px}}
.spark{{font-family:Consolas,Menlo,monospace;color:#4477dd;letter-spacing:1px}}
.withheld{{background:#fff8e1;border-left:4px solid #f0b400;padding:12px 16px;border-radius:0 6px 6px 0;margin:14px 0}}
.hint{{color:#666;font-size:13px}}
.profile{{margin:10px 0;padding:10px 16px;background:#fafafa;border-radius:6px}}
.profile .label{{color:#888;display:inline-block;min-width:140px}}
.caveat{{background:#fbf4ee;border-left:4px solid #b86a2c;padding:12px 16px;border-radius:0 6px 6px 0;margin:24px 0;color:#444}}
h2{{font-size:15px;margin-top:28px}}sub{{color:#aaa}}
</style></head><body>
<h1>Bellwether — AI impact lens</h1>
<div class="sub">{_esc(result['repo'])} · {_esc(w['first_commit'])} → {_esc(w['last_commit'])} ({w['weeks']} weeks)</div>

<div class="headline">
  <b>AI co-author share: {pct:.1f}%</b>
  <span class="hint">({ad['ai_commits']}/{ad['total_commits']} commits — lower bound)</span><br>
  {("Adoption date: <code>" + _esc(ad['adoption_date']) + "</code>") if ad.get('adoption_date') else "<span class='hint'>No sustained adoption window detected.</span>"}
  {("<br>Per tool: " + ", ".join(_esc(k)+" ("+str(v)+")" for k,v in ad['per_tool'].items())) if ad.get('per_tool') else ""}
  {("<br>Rate / week: <span class='spark'>" + spark + "</span>") if spark else ""}
</div>

<h2>Enablement Score</h2>
{score_block}

<h2>Delivery profile <span class="hint">(general health, NOT causal)</span></h2>
<div class="profile">
  <div><span class="label">Flow</span> commits/wk {f['commits_per_week']:g} · active-day ratio {f['active_day_ratio']:g}</div>
  <div><span class="label">Change shape</span> median {cs['median_lines']} lines / {cs['median_files']} files · large-change rate {cs['large_change_rate']:.1%}</div>
  <div><span class="label">Quality</span> fix/revert {q['fix_rate']:.1%} · test-to-code co-change {t2c_s}</div>
  <div><span class="label">People</span> {_esc(people_row)}</div>
</div>

<div class="caveat"><b>Attribution caveat.</b> {_esc(result['attribution_caveat'])}</div>
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
