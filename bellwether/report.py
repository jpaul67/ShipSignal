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
    L: list[str] = ["", f"  Bellwether impact — {result['repo']}"]
    if result.get("error"):
        L += [f"  error: {result['error']}", ""]
        return "\n".join(L)

    w = result["window"]
    ad = result["adoption"]
    dh = result["delivery_health"]
    rd = result.get("readiness")
    L.append(f"  {w['first_commit']} → {w['last_commit']}  "
             f"({w['weeks']} weeks, {ad['total_commits']} commits)")
    L.append("")

    # --- The three always-on headline numbers ---
    tool = ""
    if ad.get("per_tool"):
        tool = "  (" + ", ".join(f"{k} {v}" for k, v in ad["per_tool"].items()) + ")"
    L.append(f"  AI Adoption      {ad['level']:<11} {ad['ai_coauthor_share'] * 100:.0f}%{tool}")
    if dh["status"] == "scored":
        flags = [c["flag"] for c in dh["components"] if c.get("flag")]
        flag_s = ("   ! " + "; ".join(flags)) if flags else ""
        L.append(f"  Delivery Health  {dh['score']}/100 · {dh['grade']}{flag_s}")
    else:
        L.append(f"  Delivery Health  —  ({dh['reason']})")
    L.append(f"  Readiness        {rd['score']}/100 · {rd['grade']}" if rd
             else "  Readiness        —  (run a readiness scan to populate)")
    L.append("")

    # --- AI adoption detail ---
    L.append(f"  AI adoption ({ad['ai_commits']}/{ad['total_commits']} commits — lower bound)")
    if ad.get("adoption_date"):
        L.append(f"   adoption date {ad['adoption_date']} "
                 f"({'auto' if ad['adoption_auto_detected'] else 'override'})")
    series = ad.get("weekly_series", [])
    if series:
        spark = _sparkline([s[1] for s in series], max_val=1.0)
        tail = "  (recent 60 wks)" if len(spark) > 60 else ""
        L.append(f"   rate/week {spark[-60:]}{tail}  0–100%")
    L.append("")

    # --- Delivery Health breakdown ---
    if dh["status"] == "scored":
        L.append("  Delivery Health — general engineering norms, NOT AI-attributed:")
        for c in dh["components"]:
            if c["score_frac"] is None:
                L.append(f"   {c['id']:<24} {'·' * 12} {c['status']}")
            else:
                flag = f"  ! {c['flag']}" if c.get("flag") else ""
                L.append(f"   {c['id']:<24} {_bar(c['score_frac'], 1.0, 12)} "
                         f"{c['score_frac'] * 100:.0f}%  (w{c['weight']}){flag}")
        d = dh["descriptive"]
        L.append(f"   context (not scored): fix/revert {d['fix_revert_rate']:.0%} · "
                 f"{d['commits_per_week']:g} commits/wk · {d['contributors']} contributors")
        L.append("")

    # --- Before/after AI Enablement delta (the conditional bonus) ---
    if result.get("score_status") == "scored":
        L.append(f"  Before/after AI Enablement: {result['score']}/100")
        for p in result.get("pillars", []):
            if p.get("pts") is None:
                L.append(f"   {p['id']:<20} {'·' * 12} {p.get('status', 'n/a')}  ({p['basis']})")
            else:
                L.append(f"   {p['id']:<20} {_bar(p['pts'], p['max'], 12)} "
                         f"{p['pts']:g}/{p['max']:g}  ({p['basis']})")
    else:
        reason = result.get("score_withheld_reason") or "see confidence"
        L.append(f"  Before/after AI Enablement: n/a — {reason}")
        L.append("   (a before/after needs a clean pre-AI baseline; the three numbers above "
                 "stand on their own)")
    L.append("")

    L.append(f"  Note: {result['attribution_caveat']}")
    L.append("")
    return "\n".join(L)


def render_impact_markdown(result: dict) -> str:
    if result.get("error"):
        return f"# Bellwether impact — {result['repo']}\n\n**Error:** {result['error']}\n"
    w = result["window"]
    ad = result["adoption"]
    dh = result["delivery_health"]
    rd = result.get("readiness")
    m = result["metrics"]
    f, cs, q, p = m["flow"], m["change_shape"], m["quality"], m["people"]

    health_cell = (f"{dh['score']}/100 · {dh['grade']}" if dh["status"] == "scored"
                   else f"— ({dh['reason']})")
    ready_cell = f"{rd['score']}/100 · {rd['grade']}" if rd else "—"
    tools = (", ".join(f"{k} {v}" for k, v in ad["per_tool"].items())) if ad.get("per_tool") else "—"

    L = [f"# Bellwether — AI impact: {result['repo']}", "",
         f"**{w['first_commit']} → {w['last_commit']} · {w['weeks']} weeks · "
         f"{ad['total_commits']} commits**", "",
         "| | Result | |", "|---|---|---|",
         f"| **AI Adoption** | {ad['level']} · {ad['ai_coauthor_share'] * 100:.0f}% | {tools} |",
         f"| **Delivery Health** | {health_cell} | general eng norms, not AI-attributed |",
         f"| **Readiness** | {ready_cell} | static repo state |", ""]

    L += ["## AI adoption (direct, in-repo signal)", "",
          f"- **{ad['level']} — {ad['ai_coauthor_share'] * 100:.1f}%** "
          f"({ad['ai_commits']}/{ad['total_commits']} commits), a **lower bound** "
          "(squash-merges drop trailers)."]
    if ad.get("adoption_date"):
        L.append(f"- Adoption date: `{ad['adoption_date']}` "
                 f"({'auto-detected' if ad['adoption_auto_detected'] else 'override'})")
    if ad.get("per_tool"):
        L.append("- Per tool: " + ", ".join(f"`{k}` ({v})" for k, v in ad["per_tool"].items()))
    L.append("")

    if dh["status"] == "scored":
        L += ["## Delivery Health (general engineering norms — NOT AI-attributed)", "",
              f"**{dh['score']}/100 · grade {dh['grade']}**", "",
              "| Component | Score | Weight | Flag |", "|---|---|---|---|"]
        for c in dh["components"]:
            val = f"{c['score_frac'] * 100:.0f}%" if c["score_frac"] is not None else c["status"]
            L.append(f"| {c['id']} | {val} | {c['weight']} | {c.get('flag') or ''} |")
        d = dh["descriptive"]
        L += ["", f"*Context (not scored — too noisy to rank health by): fix/revert "
              f"{d['fix_revert_rate']:.0%}, {d['commits_per_week']:g} commits/wk, "
              f"{d['contributors']} contributors.*", ""]
    else:
        L += ["## Delivery Health", "",
              f"*Insufficient data — {dh['reason']}.*", ""]

    # Before/after delta — the conditional bonus.
    L += ["## Before/after AI Enablement (bonus — needs a clean pre-AI baseline)", ""]
    if result.get("score_status") == "scored":
        L += [f"**{result['score']}/100**", "", "| Pillar | Score | Basis |", "|---|---|---|"]
        for pl in result.get("pillars", []):
            val = (f"{pl['pts']:g}/{pl['max']:g}" if pl.get("pts") is not None
                   else pl.get("status", "n/a"))
            L.append(f"| {pl['id']} | {val} | {pl['basis']} |")
    else:
        L.append(f"*n/a — {result.get('score_withheld_reason', 'see confidence')}. "
                 "The three numbers above stand on their own.*")
    L.append("")

    L += ["## Attribution caveat", "", f"> {result['attribution_caveat']}", "",
          f"<sub>bellwether v{__version__} · {result['scanned_at']}</sub>", ""]
    return "\n".join(L)


def _stat_card(label: str, value: str, grade: str | None, sub: str) -> str:
    color = GRADE_COLOR.get(grade, "#4477dd") if grade else "#4477dd"
    grade_chip = (f"<span class='gchip' style='background:{color}'>{_esc(grade)}</span>"
                  if grade else "")
    return (f"<div class='card' style='border-top:3px solid {color}'>"
            f"<div class='clabel'>{_esc(label)}</div>"
            f"<div class='cval'>{_esc(value)}{grade_chip}</div>"
            f"<div class='csub'>{_esc(sub)}</div></div>")


def render_impact_html(result: dict) -> str:
    if result.get("error"):
        return (f"<!doctype html><meta charset='utf-8'><title>impact error</title>"
                f"<h1>Bellwether impact — {_esc(result['repo'])}</h1>"
                f"<p><b>Error:</b> {_esc(result['error'])}</p>")
    w = result["window"]
    ad = result["adoption"]
    dh = result["delivery_health"]
    rd = result.get("readiness")
    pct = ad["ai_coauthor_share"] * 100
    series_rates = [s[1] for s in ad.get("weekly_series", [])]
    spark = _esc(_sparkline(series_rates, max_val=1.0)) if series_rates else ""

    # --- three headline cards ---
    tools = (", ".join(f"{k} {v}" for k, v in ad["per_tool"].items())
             if ad.get("per_tool") else "no AI trailers")
    cards = (f"<div class='card' style='border-top:3px solid #4477dd'>"
             f"<div class='clabel'>AI Adoption</div>"
             f"<div class='cval'>{ad['level']}<span class='pct'>{pct:.0f}%</span></div>"
             f"<div class='csub'>{_esc(tools)} · lower bound</div></div>")
    if dh["status"] == "scored":
        cards += _stat_card("Delivery Health", f"{dh['score']}/100 ", dh["grade"],
                            "general eng norms")
    else:
        cards += _stat_card("Delivery Health", "—", None, dh["reason"])
    if rd:
        cards += _stat_card("Readiness", f"{rd['score']}/100 ", rd["grade"], "static repo state")
    else:
        cards += _stat_card("Readiness", "—", None, "not run")

    # --- delivery-health breakdown ---
    if dh["status"] == "scored":
        rows = ""
        for c in dh["components"]:
            flag = (f"<span class='flag'>{_esc(c['flag'])}</span>" if c.get("flag") else "")
            if c["score_frac"] is None:
                rows += (f"<div class='row'><div class='cat'>{_esc(c['id'])}</div>"
                         f"<div class='bar na'></div>"
                         f"<div class='num'>{_esc(c['status'])}</div></div>")
            else:
                rows += (f"<div class='row'><div class='cat'>{_esc(c['id'])}</div>"
                         f"<div class='bar'><span style='width:{c['score_frac'] * 100:.0f}%'></span></div>"
                         f"<div class='num'>{c['score_frac'] * 100:.0f}% {flag}</div></div>")
        d = dh["descriptive"]
        ctx = (f"<p class='hint'>Context (not scored): fix/revert {d['fix_revert_rate']:.0%} · "
               f"{d['commits_per_week']:g} commits/wk · {d['contributors']} contributors.</p>")
        health_block = (f"<h2>Delivery Health <span class='hint'>(general norms, "
                        f"NOT AI-attributed)</span></h2>{rows}{ctx}")
    else:
        health_block = (f"<h2>Delivery Health</h2><div class='withheld'>Insufficient data — "
                        f"{_esc(dh['reason'])}.</div>")

    # --- before/after bonus ---
    if result.get("score_status") == "scored":
        prows = "".join(
            f"<div class='row'><div class='cat'>{_esc(pl['id'])}</div>"
            f"<div class='bar'><span style='width:{100 * pl['pts'] / pl['max']:.0f}%'></span></div>"
            f"<div class='num'>{pl['pts']:g}/{pl['max']:g}</div></div>"
            if pl.get("pts") is not None else
            f"<div class='row'><div class='cat'>{_esc(pl['id'])}</div>"
            f"<div class='bar na'></div><div class='num'>{_esc(pl.get('status', 'n/a'))}</div></div>"
            for pl in result.get("pillars", [])
        )
        bonus_block = (f"<h2>Before/after AI Enablement</h2>"
                       f"<p><span class='score'>{result['score']}</span>"
                       f"<span class='slash'>/100</span></p>{prows}")
    else:
        bonus_block = (f"<h2>Before/after AI Enablement <span class='hint'>(bonus)</span></h2>"
                       f"<div class='withheld'>n/a — "
                       f"{_esc(result.get('score_withheld_reason', 'see confidence'))}<br>"
                       f"<span class='hint'>A before/after needs a clean pre-AI baseline; the "
                       f"three numbers above stand on their own.</span></div>")

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>AI impact — {_esc(result['repo'])}</title><style>
body{{font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;max-width:780px;margin:40px auto;padding:0 20px;color:#1a1a1a}}
h1{{font-size:18px;margin-bottom:2px}}.sub{{color:#888;margin-bottom:18px}}
.cards{{display:flex;gap:12px;margin:16px 0 24px}}
.card{{flex:1;background:#fafafa;border-radius:8px;padding:14px 16px}}
.clabel{{color:#888;font-size:12px;text-transform:uppercase;letter-spacing:.04em}}
.cval{{font-size:22px;font-weight:700;margin:4px 0}}
.cval .pct{{font-size:14px;color:#888;font-weight:400;margin-left:6px}}
.csub{{color:#777;font-size:12px}}
.gchip{{display:inline-block;color:#fff;border-radius:5px;padding:0 8px;font-size:14px;margin-left:6px;vertical-align:middle}}
.score{{font-size:40px;font-weight:700}}.slash{{color:#bbb;font-size:22px}}
.row{{display:flex;align-items:center;margin:6px 0}}.cat{{width:200px;color:#555}}
.bar{{flex:1;background:#eee;border-radius:4px;height:14px;overflow:hidden;margin:0 10px}}
.bar span{{display:block;height:100%;background:#4c1}}
.bar.na{{background:repeating-linear-gradient(45deg,#eee,#eee 4px,#f6f6f6 4px,#f6f6f6 8px)}}
.num{{width:120px;text-align:right;color:#333}}
.flag{{color:#b8860b;font-weight:600;font-size:12px}}
.spark{{font-family:Consolas,Menlo,monospace;color:#4477dd;letter-spacing:1px;word-break:break-all}}
.headline{{background:#f4f8ff;border-left:4px solid #4477dd;padding:12px 16px;border-radius:0 6px 6px 0;margin:14px 0}}
.withheld{{background:#fff8e1;border-left:4px solid #f0b400;padding:12px 16px;border-radius:0 6px 6px 0;margin:14px 0}}
.hint{{color:#666;font-size:13px;font-weight:400}}
.caveat{{background:#fbf4ee;border-left:4px solid #b86a2c;padding:12px 16px;border-radius:0 6px 6px 0;margin:24px 0;color:#444}}
h2{{font-size:15px;margin-top:28px}}sub{{color:#aaa}}
</style></head><body>
<h1>Bellwether — AI impact</h1>
<div class="sub">{_esc(result['repo'])} · {_esc(w['first_commit'])} → {_esc(w['last_commit'])} · {w['weeks']} weeks · {ad['total_commits']} commits</div>

<div class="cards">{cards}</div>

<div class="headline">
  <b>AI adoption {pct:.1f}%</b>
  <span class="hint">({ad['ai_commits']}/{ad['total_commits']} commits — lower bound)</span><br>
  {("Adoption date: <code>" + _esc(ad['adoption_date']) + "</code>") if ad.get('adoption_date') else "<span class='hint'>No sustained adoption window detected.</span>"}
  {("<br>Rate / week: <span class='spark'>" + spark + "</span>") if spark else ""}
</div>

{health_block}

{bonus_block}

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
