"""Rendering: CLI text, Markdown/HTML reports, and a badge SVG."""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from html import escape as _esc

from . import __version__, ansi, glossary, prdata
from .detectors import AREA_ORDER

GRADE_COLOR = {"A": "#4c1", "B": "#97ca00", "C": "#dfb317", "D": "#fe7d37", "F": "#e05d44"}

_SPARK = "▁▂▃▄▅▆▇█"


def _human_date(iso: str, *, with_year: bool = True) -> str:
    """'2026-02-05' -> '5 Feb 2026' (or '5 Feb' when with_year=False). Falls
    back to the raw string when it doesn't parse — never raises on bad input."""
    try:
        d = datetime.strptime(iso, "%Y-%m-%d")
    except (ValueError, TypeError):
        return iso
    return f"{d.day} {d:%b %Y}" if with_year else f"{d.day} {d:%b}"


def _human_range(a: str, b: str) -> str:
    """A commit window as '5 Feb – 17 Jun 2026', dropping the repeated year on
    the start when both ends share it. Falls back to 'a → b' on parse trouble."""
    try:
        da = datetime.strptime(a, "%Y-%m-%d")
        db = datetime.strptime(b, "%Y-%m-%d")
    except (ValueError, TypeError):
        return f"{a} → {b}"
    return f"{_human_date(a, with_year=da.year != db.year)} – {_human_date(b)}"


def _human_ts(iso: str) -> str:
    """'2026-06-20T22:19:22Z' -> '20 Jun 2026, 22:19 UTC'. Falls back to raw."""
    try:
        d = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, TypeError):
        return iso
    return f"{d.day} {d:%b %Y}, {d:%H:%M} UTC"


def _tip(label: str, key: str) -> str:
    """An HTML term carrying a hover tooltip (native title=, zero-dependency).
    A dotted underline (.tip) cues that an explanation is available."""
    t = glossary.tip(key)
    return f"<span class='tip' title='{_esc(t)}'>{_esc(label)}</span>" if t else _esc(label)


def _how_to_read_html() -> str:
    """A collapsible glossary so the report is self-teaching without hovering."""
    items = "".join(
        f"<dt>{_esc(name)}</dt><dd>{_esc(glossary.short(key))}</dd>"
        for name, key in glossary.HOWTO_ORDER
    )
    return ("<details class='howto'><summary>How to read this report</summary>"
            f"<dl>{items}</dl></details>")


def _bar(points, maximum, width: int = 16) -> str:
    filled = int(round(width * (points / maximum))) if maximum else 0
    filled = max(0, min(width, filled))
    return "█" * filled + "░" * (width - filled)


def _terminal_width(default: int = 80) -> int:
    try:
        return shutil.get_terminal_size((default, 24)).columns
    except OSError:
        return default


def _downsample(values: list, target: int) -> list:
    """Bucket-average ``values`` down to length ``target`` cells. If the input
    is already short enough, it's returned unchanged. ``None`` entries are
    skipped within a bucket, but a bucket that is *entirely* ``None`` stays
    ``None`` so gap-aware sparklines preserve real gaps honestly."""
    if target <= 0 or len(values) <= target:
        return list(values)
    n = len(values)
    out: list = []
    for i in range(target):
        lo, hi = int(i * n / target), int((i + 1) * n / target)
        bucket = [v for v in values[lo:hi] if v is not None]
        out.append(sum(bucket) / len(bucket) if bucket else None)
    return out


def _fit_spark_width(chrome: int, *, hi: int = 60, lo: int = 20) -> int:
    """Number of sparkline cells that fit on the current terminal once you
    subtract ``chrome`` (label + caption + padding). Clamped to ``[lo, hi]``
    so very narrow terminals still get something useful and very wide ones
    don't sprawl past the natural data window."""
    return max(lo, min(hi, _terminal_width() - chrome))


def _adaptive_spark(values: list, chrome: int, max_val: float) -> str:
    """Width-fitting + gap-aware sparkline used by every CLI sparkline row."""
    return _spark_series(_downsample(values, _fit_spark_width(chrome)), max_val)


def _fix_path(f: dict) -> str:
    """Path with an optional ``:line`` suffix (#5)."""
    p = f.get("path", "")
    return f"{p}:{f['line']}" if f.get("line") else p


def _fix_meta(f: dict) -> str:
    """Compact ' · ≈+3 pts · moderate' suffix (#1). Informational findings say
    so instead of a points number, so a 0 doesn't read as 'worthless'."""
    bits = []
    if f.get("informational"):
        bits.append("informational")
    else:
        pts = f.get("points_at_stake", 0.0)
        if pts:
            bits.append(f"≈+{pts:g} pts")
    if f.get("effort"):
        bits.append(f["effort"])
    return ("  · " + " · ".join(bits)) if bits else ""


# --- #4 grouped + collapsed rendering helpers --------------------------------
_COLLAPSE_THRESHOLD = 3  # collapse setup info findings when 3+ accumulate


def _collapse_broken_links(bucket: list[dict]) -> list[dict]:
    """Within an Integrity bucket, collapse broken_link findings that share
    the same target into one bundle when ≥ _COLLAPSE_THRESHOLD files are
    affected. Individual findings (or targets with fewer hits) stay as-is.
    The bundle carries a ``files`` list so the HTML renderer can expand it."""
    from collections import defaultdict
    by_target: dict[str, list[dict]] = defaultdict(list)
    non_link: list[dict] = []
    for f in bucket:
        if f.get("detector") == "broken_link" and f.get("link_target"):
            by_target[f["link_target"]].append(f)
        else:
            non_link.append(f)

    result: list[dict] = list(non_link)
    for tgt, group in by_target.items():
        if len(group) < _COLLAPSE_THRESHOLD:
            result.extend(group)
        else:
            file_labels = [
                f"{f['path']}:{f['line']}" if f.get("line") else f["path"]
                for f in group
            ]
            first_two = ", ".join(file_labels[:2])
            overflow = len(file_labels) - 2
            fix_loc = f"{first_two}{f', +{overflow} more' if overflow > 0 else ''}"
            bundled = {
                "_collapsed": True,
                "count": len(group),
                "evidence": f"Link to '{tgt}' is broken in {len(group)} files",
                "fix": f"Fix or remove '{tgt}' — {fix_loc}",
                "effort": "quick",
                "files": file_labels,
            }
            result.append(bundled)
    return result


def _group_fixes(findings: list[dict], *, collapse_setup: bool = True,
                 collapse_links: bool = True) -> list[dict]:
    """Group findings into ``[{area, items}]`` in the fixed AREA_ORDER. Each
    ``items`` is a list of either real finding dicts or one collapsed bundle
    of low-value setup info findings (so the list doesn't drown in 5 tiny
    convention-file misses). Broken-link findings that share a target are
    similarly collapsed when ≥ _COLLAPSE_THRESHOLD files are affected."""
    by_area: dict[str, list[dict]] = {a: [] for a in AREA_ORDER}
    other: list[dict] = []
    for f in findings:
        area = f.get("area") or "Other"
        (by_area.get(area, other)).append(f)

    blocks: list[dict] = []
    for area in AREA_ORDER:
        bucket = by_area.get(area) or []
        if not bucket:
            continue
        items: list = list(bucket)  # mix of finding-dicts + a collapsed bundle
        if collapse_setup and area == "Setup":
            info_items = [f for f in bucket if f.get("severity") == "info"]
            if len(info_items) >= _COLLAPSE_THRESHOLD:
                # Build the collapsed line: total points + a comma list of "label (+N)"
                labels = []
                for f in info_items:
                    # Evidence is "Missing <label>"; trim the prefix to label.
                    ev = f.get("evidence") or ""
                    label = ev.split("Missing ", 1)[1] if ev.startswith("Missing ") else ev
                    pts = f.get("points_at_stake", 0.0)
                    suffix = f" (+{pts:g})" if pts else ""
                    labels.append(label + suffix)
                bundled = {
                    "_collapsed": True,
                    "count": len(info_items),
                    "evidence": f"Missing {len(info_items)} convention items: "
                                + ", ".join(labels),
                    "fix": "Drop these in — each is small but they add up to "
                           f"≈+{sum(f.get('points_at_stake', 0) for f in info_items):g} pts",
                    "effort": "quick",
                }
                # Keep warn-level setup items separate (they're load-bearing).
                items = [f for f in bucket if f.get("severity") != "info"] + [bundled]
        if collapse_links and area == "Integrity":
            items = _collapse_broken_links(items)
        blocks.append({"area": area, "items": items})
    if other:
        blocks.append({"area": "Other", "items": other})
    return blocks


def _top_n_payoff_ids(findings: list[dict], n: int = 3) -> set[int]:
    """Return ``id(f)`` for the top-N findings by points (warn-class, not
    informational). Used to gate snippet display in the CLI."""
    eligible = [f for f in findings if not f.get("informational")
                and f.get("severity") == "warn"]
    eligible.sort(key=lambda f: -f.get("points_at_stake", 0.0))
    return {id(f) for f in eligible[:n]}


def _indent(text: str, prefix: str) -> str:
    return "\n".join(prefix + ln if ln else ln for ln in text.splitlines())


def _renorm_caveat() -> str:
    return ("≈ marks each fix's marginal payoff (resolving it alone). Renormalization "
            "means totals aren't additive — fixing several won't equal the sum.")


def _render_grouped_fixes_html(findings: list[dict]) -> str:
    """The grouped+collapsed fixes block — used by both the readiness-only
    and unified HTML renderers (so they don't drift). Snippets always shown
    here, in a collapsible <details>, per the spec."""
    blocks_html: list[str] = []
    for block in _group_fixes(findings):
        shown = [it for it in block["items"]
                 if it.get("_collapsed") or it.get("severity") == "warn"]
        if not shown:
            continue
        items_html: list[str] = []
        for it in shown:
            if it.get("_collapsed"):
                body = (f"<li>{_esc(it['evidence'])} — <i>quick</i><br>"
                        f"<span class='fix'>→ {_esc(it['fix'])}</span>")
                if it.get("files"):
                    file_lines = "\n".join(_esc(fl) for fl in it["files"])
                    body += (
                        "<details class='snippet'><summary>All affected files</summary>"
                        f"<pre>{file_lines}</pre></details>"
                    )
                items_html.append(body + "</li>")
                continue
            base = (f"<li><b>{_esc(_fix_path(it))}</b> — {_esc(it['evidence'])}"
                    f"{_esc(_fix_meta(it))}<br>"
                    f"<span class='fix'>→ {_esc(it['fix'])}</span>")
            if it.get("snippet"):
                base += (
                    "<details class='snippet'><summary>Starter — copy + fill in "
                    "placeholders</summary>"
                    f"<pre>{_esc(it['snippet'])}</pre></details>"
                )
            items_html.append(base + "</li>")
        blocks_html.append(
            f"<h3 class='area'>{_esc(block['area'])}</h3>"
            f"<ul>{''.join(items_html)}</ul>"
        )
    return "\n".join(blocks_html) or "<p>None — nicely set up. ✓</p>"


def render(result: dict, *, color: bool = False) -> str:
    out = []
    out.append("")
    out.append(f"  ShipSignal readiness — {result['repo']}")
    score_line = ansi.bold(f"Score: {result['score']}/100", color)
    grade_line = ansi.grade(f"(grade {result['grade']})", result["grade"], color)
    out.append(f"  {score_line}   {grade_line}")
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
    if warns or any(f.get("severity") == "info" and f.get("detector") == "setup"
                    for f in findings):
        out.append("")
        out.append(f"  Top fixes ({len(warns)} issues, grouped by area, "
                   "highest payoff first):")
        snippet_ids = _top_n_payoff_ids(findings, n=3)
        blocks = _group_fixes(findings)
        for block in blocks:
            shown = [it for it in block["items"]
                     if it.get("_collapsed") or it.get("severity") == "warn"]
            if not shown:
                continue
            out.append("")
            out.append(f"  {block['area']}")
            for it in shown:
                if it.get("_collapsed"):
                    out.append(f"   • {it['evidence']}  · quick")
                    out.append(f"       → {it['fix']}")
                    continue
                out.append(f"   • {_fix_path(it)}: {it['evidence']}{_fix_meta(it)}")
                out.append(f"       → {it['fix']}")
                if id(it) in snippet_ids and it.get("snippet"):
                    out.append("       starter (copy + fill in the placeholders):")
                    out.append(_indent(it["snippet"], "         "))
        out.append("")
        out.append(f"  {_renorm_caveat()}")
    out.append("")
    return "\n".join(out)


def _cat_rows(result):
    for c in result["categories"]:
        if c["status"] == "scored":
            pct = 100 * c["points"] / c["max"] if c["max"] else 0
            yield c["id"], f"{c['points']:g}/{c['max']:g}", pct
        else:
            yield c["id"], c["status"], None


def render_markdown(result: dict) -> str:
    L = [f"# ShipSignal — AI readiness: {result['repo']}", "",
         f"**Score: {result['score']}/100 — grade {result['grade']}**", "",
         "| Category | Score |", "|---|---|"]
    for cid, val, _pct in _cat_rows(result):
        L.append(f"| {cid} | {val} |")
    findings = result["findings"]
    warns = [f for f in findings if f["severity"] != "info"]
    if warns or findings:
        L += ["", "## Fixes _(grouped by area, highest payoff first)_", ""]
        for block in _group_fixes(findings):
            shown = [it for it in block["items"]
                     if it.get("_collapsed") or it.get("severity") == "warn"]
            if not shown:
                continue
            L += [f"### {block['area']}", ""]
            for it in shown:
                if it.get("_collapsed"):
                    L.append(f"- {it['evidence']} — _quick_  \n  → {it['fix']}")
                    continue
                L.append(f"- **{_fix_path(it)}** — {it['evidence']}{_fix_meta(it)}  \n"
                         f"  → {it['fix']}")
                if it.get("snippet"):
                    L += ["",
                          ("  <details><summary>Starter (copy + fill in the placeholders)"
                           "</summary>"),
                          "", "  ```markdown", _indent(it["snippet"], "  "),
                          "  ```", "  </details>", ""]
            L.append("")
        L += [f"_<sub>{_renorm_caveat()}</sub>_", ""]
    L += [f"<sub>shipsignal v{__version__} · {result['scanned_at']}</sub>", ""]
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
    findings = result["findings"]
    warns = [f for f in findings if f["severity"] != "info"]
    fixes_html = _render_grouped_fixes_html(findings) if (warns or findings) else \
                 "<p>None — nicely set up. ✓</p>"
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>AI readiness — {_esc(result['repo'])}</title><style>
body{{font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;max-width:760px;
margin:40px auto;padding:0 20px;color:#1a1a1a}}
h1{{font-size:18px;margin-bottom:2px}}.sub{{color:#888;margin-bottom:18px}}
.score{{font-size:48px;font-weight:700}}.slash{{color:#bbb;font-size:24px}}
.grade{{display:inline-block;color:#fff;background:{color};border-radius:6px;
padding:2px 12px;font-size:20px;vertical-align:middle;margin-left:10px}}
.row{{display:flex;align-items:center;margin:6px 0}}.cat{{width:170px;color:#555}}
.bar{{flex:1;background:#eee;border-radius:4px;height:14px;overflow:hidden;margin:0 10px}}
.bar span{{display:block;height:100%;background:{color}}}
.bar.na{{background:repeating-linear-gradient(45deg,#eee,#eee 4px,#f6f6f6 4px,#f6f6f6 8px)}}
.num{{width:74px;text-align:right;color:#333}}h2{{font-size:15px;margin-top:28px}}
h3.area{{font-size:13px;margin:16px 0 4px;color:#4477dd;
text-transform:uppercase;letter-spacing:.05em}}
ul{{padding-left:18px}}li{{margin:8px 0}}.fix{{color:#666}}
details.snippet{{margin-top:6px;font-size:12px}}
details.snippet summary{{cursor:pointer;color:#4477dd}}
details.snippet pre{{background:#fafafa;border:1px solid #eee;padding:10px;
border-radius:4px;overflow-x:auto;white-space:pre-wrap}}
.hint{{color:#666;font-size:12px}}
sub{{color:#aaa}}
</style></head><body>
<h1>ShipSignal — AI readiness</h1><div class="sub">{_esc(result['repo'])}</div>
<p><span class="score">{result['score']}</span><span class="slash">/100</span>
<span class="grade">{_esc(result['grade'])}</span></p>
{rows}
<h2>Top fixes ({len(warns)}, grouped by area, highest payoff first)</h2>
{fixes_html}
<p class="hint" style="margin-top:18px">{_esc(_renorm_caveat())}</p>
<p><sub>shipsignal v{__version__} · {_esc(result['scanned_at'])}</sub></p>
</body></html>"""


# ---------------------------------------------------------------------------
# Impact lens renderers
# ---------------------------------------------------------------------------
def _adoption_headline(adoption: dict) -> str:
    pct = adoption["ai_coauthor_share"] * 100
    return (f"AI co-author share: {pct:.1f}% "
            f"({adoption['ai_commits']}/{adoption['total_commits']} commits, lower bound)")


# Honest framing for the delivery-health focus list: it mirrors the Readiness
# fix backlog in shape, but the voice is deliberately softer — these are general
# engineering-norm observations, never AI-attributed and never one-file "fixes".
_DELIVERY_FOCUS_NOTE = ("General engineering norms — not AI-attributed; where "
                        "delivery health has the most headroom, not a defect list.")


def _delivery_focus(dh: dict, metrics: dict) -> list[dict]:
    """Flagged Delivery-Health components → a short 'where to focus' list, the
    delivery-side parallel to the Readiness fixes. Each item pulls the concrete
    number behind the flag from ``metrics`` so the advice is specific, not
    generic. Empty when nothing is flagged (or health wasn't scored)."""
    if dh.get("status") != "scored":
        return []
    cs = metrics.get("change_shape", {})
    q = metrics.get("quality", {})
    p = metrics.get("people", {})
    out: list[dict] = []
    for c in dh["components"]:
        if not c.get("flag"):
            continue
        cid = c["id"]
        if cid == "change_size_discipline":
            median = cs.get("median_lines")
            large = cs.get("large_change_rate")
            detail = (f"Median commit is {median:g} lines" if median is not None
                      else "Commits run large")
            if large:
                detail += f"; {large:.0%} are large (400+ lines)"
            out.append({"label": "Change size", "detail": f"{detail}. Smaller, more "
                        "frequent commits are safer to review, test, and revert."})
        elif cid == "test_discipline":
            ratio = q.get("test_to_code_ratio")
            frac = f"{ratio:.0%}" if ratio is not None else "few"
            out.append({"label": "Test discipline", "detail": f"Only {frac} of "
                        "code-touching commits also touch tests. Pairing changes "
                        "with tests keeps coverage moving with the code."})
        elif cid == "knowledge_distribution":
            share = p.get("top_author_share")
            bus = p.get("bus_factor")
            who = (f"One author owns {share:.0%} of commits" if share is not None
                   else "Authorship is concentrated")
            if bus:
                who += f" (bus factor {bus})"
            out.append({"label": "Knowledge distribution", "detail": f"{who}. "
                        "Spreading review and authorship reduces key-person risk."})
    return out


def _squash_caveat(ad: dict) -> str | None:
    """One-line caveat when a squash workflow *might* undercount adoption, else None.

    Calibrated wording (Package D): GitHub-native squash PRESERVES co-authors, so
    a squash workflow is not automatically a floor — only pipelines that strip
    trailers (internal-sync bots, some merge queues) undercount. Suppressed once
    --pr-data has actually resolved the question (the recovery line speaks then).
    """
    if ad.get("recovery") is not None:
        return None
    if not ad.get("squash_suspected"):
        return None
    how = "declared" if ad.get("squash_source") == "declared" else "detected"
    return (f"squash-merge workflow {how} — GitHub-native squash keeps co-authors, but if "
            f"your pipeline strips them (internal-sync bots, some merge queues) adoption is "
            f"undercounted")


def _pct(share: float) -> str:
    """Adoption percentage for display. `.0f` normally, but keep significant
    digits below 1% so a real recovered figure (e.g. jest's 0.2%) never rounds
    to a contradictory '0%' next to an above-None band."""
    v = share * 100
    if 0 < v < 1:
        return f"{v:.2g}%"
    return f"{v:.0f}%"


def _recovery_facts(ad: dict) -> dict | None:
    """Preformatted display values for the squash-recovery figure (Package D),
    or None when --pr-data wasn't supplied. One place computes the numbers so the
    three renderers can't drift."""
    rec = ad.get("recovery")
    if not rec:
        return None
    cov = rec["coverage"]
    return {
        "recovered": rec["newly_attributed"] > 0,
        "m_pct": _pct(rec["measured_share"]),
        "r_pct": _pct(rec["recovered_share"]),
        "r_level": rec["recovered_level"],
        "newly": rec["newly_attributed"],
        "matched": rec["squash_matched"],
        "squash": rec["squash_commits"],
        "cov": f"{cov * 100:.0f}%" if cov is not None else "n/a",
        "partial": cov is not None and cov < 0.9 and rec["squash_commits"] > 0,
        "tools": ", ".join(rec["recovered_tools"]),
    }


def _recovery_text(ad: dict) -> str | None:
    """Plain-text dual figure — recovered attribution, or an explicit
    'nothing to recover' (never implying the measured number was soft)."""
    f = _recovery_facts(ad)
    if not f:
        return None
    if f["recovered"]:
        tools = f" ({f['tools']})" if f["tools"] else ""
        s = (f"recovered {f['r_level']} {f['r_pct']} from PR data — "
             f"+{f['newly']} squash commit(s) re-attributed{tools}; "
             f"measured {f['m_pct']} · {f['matched']}/{f['squash']} matched · coverage {f['cov']}")
    else:
        s = (f"PR data checked — no dropped AI attribution; measured {f['m_pct']} holds "
             f"({f['matched']}/{f['squash']} squash commits matched)")
    if f["partial"]:
        s += " — partial export, so the recovered figure is itself a lower bound"
    return s


def _recovery_recipe(ad: dict) -> list[str] | None:
    """The 2-step self-advertising recipe, shown only when a squash workflow is
    suspected AND no --pr-data was given — the discovery mechanism that teaches
    the feature exactly when it's relevant. Returns (export, rerun) lines."""
    if ad.get("recovery") is not None or not ad.get("squash_suspected"):
        return None
    return [f"{prdata.EXPORT_COMMAND} > pr.json", "then re-run with --pr-data pr.json"]


# AI Adoption has no letter grade, but the same green/yellow/red intent
# applies: None is a gap, Emerging/Established are progress, Pervasive is
# the strongest signal.
_ADOPTION_BAND = {"None": "red", "Emerging": "yellow", "Established": "green",
                  "Pervasive": "green"}


def _adoption_color(text: str, level: str, enabled: bool) -> str:
    return ansi.paint(text, _ADOPTION_BAND.get(level, ""), enabled)


def render_impact(result: dict, *, color: bool = False) -> str:
    L: list[str] = ["", f"  ShipSignal impact — {result['repo']}"]
    if result.get("error"):
        L += [f"  AI Adoption / Delivery Health: {result['error']}", ""]
        return "\n".join(L)

    w = result["window"]
    ad = result["adoption"]
    dh = result["delivery_health"]
    rd = result.get("readiness")
    sq = _squash_caveat(ad)
    L.append(f"  {w['first_commit']} → {w['last_commit']}  "
             f"({w['weeks']} weeks, {ad['total_commits']} dev commits)")
    an = result.get("analysis") or {}
    if an.get("merges_excluded") or an.get("maintenance_bots_excluded"):
        L.append(f"  excluded {an['merges_excluded']} merges + "
                 f"{an['maintenance_bots_excluded']} maintenance-bot commits")
    if an.get("ai_agent_commits"):
        L.append(f"  {an['ai_agent_commits']} AI-agent commits counted as AI (not excluded)")
    L.append("")

    # --- The three always-on headline numbers ---
    tool = ""
    if ad.get("per_tool"):
        tool = "  (" + ", ".join(f"{k} {v}" for k, v in ad["per_tool"].items()) + ")"
    # Labels are padded to a fixed column (17) before bolding so plain output
    # (color disabled) stays byte-identical to the pre-color layout.
    _LW = 17
    adoption_label = ansi.bold(f"{'AI Adoption':<{_LW}}", color)
    adoption_val = _adoption_color(
        f"{ad['level']:<11} {ad['ai_coauthor_share'] * 100:.0f}%", ad["level"], color)
    rf = _recovery_facts(ad)
    if rf and rf["recovered"]:
        head_suffix = "  " + _adoption_color(
            f"→ {rf['r_level']} {rf['r_pct']} recovered", rf["r_level"], color)
    elif sq:
        head_suffix = ansi.warn("  ? squash — may undercount", color)
    else:
        head_suffix = ""
    L.append(f"  {adoption_label}{adoption_val}{tool}{head_suffix}")

    dh_label = ansi.bold(f"{'Delivery Health':<{_LW}}", color)
    if dh["status"] == "scored":
        flags = [c["flag"] for c in dh["components"] if c.get("flag")]
        flag_s = ansi.warn("   ! " + "; ".join(flags), color) if flags else ""
        dh_val = ansi.grade(f"{dh['score']}/100 · {dh['grade']}", dh["grade"], color)
        L.append(f"  {dh_label}{dh_val}{flag_s}")
    else:
        L.append(f"  {dh_label}—  ({dh['reason']})")

    rd_label = ansi.bold(f"{'Readiness':<{_LW}}", color)
    if rd:
        rd_val = ansi.grade(f"{rd['score']}/100 · {rd['grade']}", rd["grade"], color)
        L.append(f"  {rd_label}{rd_val}")
    else:
        L.append(f"  {rd_label}—  (run a readiness scan to populate)")
    L.append("")

    # --- AI adoption detail ---
    L.append(f"  AI adoption ({ad['ai_commits']}/{ad['total_commits']} commits — lower bound)")
    L.append(f"   {glossary.short('ai_adoption')}")
    if ad.get("adoption_date"):
        L.append(f"   adoption date {ad['adoption_date']} "
                 f"({'auto' if ad['adoption_auto_detected'] else 'override'})")
    if sq:
        L.append(f"   ! {sq}")
    rtext = _recovery_text(ad)
    if rtext:
        L.append(f"   ↑ {rtext}")
    recipe = _recovery_recipe(ad)
    if recipe:
        L.append("   recover squash-dropped attribution (zero network — you run the export):")
        L.append(f"     {recipe[0]}")
        L.append(f"     {recipe[1]}")
    # Feature C: team-level breadth — aggregate only, with the non-goal line.
    br = ad.get("breadth") or {}
    if br.get("status") == "scored":
        trend_label = {"growing": " · growing", "shrinking": " · shrinking",
                       "flat": " · flat", "unknown": ""}.get(br.get("trend", ""), "")
        L.append(f"   breadth {br['breadth_pct']:.0f}% — "
                 f"{br['ai_contributors']} of {br['active_contributors']} active "
                 f"contributors{trend_label}")
        L.append("   (team-level only — ShipSignal does not score individuals)")
    elif br.get("status") == "n/a":
        L.append(f"   breadth: n/a — {br.get('reason', 'too few contributors')}")
    series = ad.get("weekly_series", [])
    if series:
        # Cap the data window at 60w (the recent slice), then size the bar
        # count to the terminal so the line never overflows on 80 cols.
        # Chrome = "   rate/week " (13) + "  {Nw} · 0–100%" (≈14) ≈ 28.
        values = [s[1] for s in series]
        window = values[-60:]
        spark = _adaptive_spark(window, chrome=28, max_val=1.0)
        L.append(f"   rate/week {spark}  {len(window)}w · 0–100%")
    L.append("")

    # --- Delivery Health breakdown ---
    if dh["status"] == "scored":
        L.append("  Delivery Health — general engineering norms, NOT AI-attributed:")
        L.append(f"   {glossary.short('delivery_health')}")
        for c in dh["components"]:
            if c["score_frac"] is None:
                L.append(f"   {c['id']:<24} {'·' * 12} {c['status']}")
            else:
                flag = f"  ! {c['flag']}" if c.get("flag") else ""
                L.append(f"   {c['id']:<24} {_bar(c['score_frac'], 1.0, 12)} "
                         f"{c['score_frac'] * 100:.0f}%  (w{c['weight']}){flag}")
        d = dh["descriptive"]
        L.append(f"   context (not scored): {d['commits_per_week']:g} commits/wk · "
                 f"{d['contributors']} contributors")
        focus = _delivery_focus(dh, result["metrics"])
        if focus:
            L.append("")
            L.append("   Where to focus (general eng norms, not AI-attributed):")
            for it in focus:
                L.append(f"    • {it['label']} — {it['detail']}")
        L.append("")

    # --- Outcomes (Package J): revert pairs / time-to-correction + the
    # relabeled change-failure proxy — context, never scored. ---
    oc = result.get("outcomes")
    if oc:
        rp = oc["revert_pairs"]
        L.append("  Outcomes — context, not scored:")
        L.append(f"   {glossary.short('outcomes')}")
        if rp["status"] == "scored":
            unmatched_s = f"  ({rp['unmatched']} unmatched)" if rp["unmatched"] else ""
            L.append(f"   revert pairs {rp['matched']}  ·  median time-to-correction "
                     f"{rp['median_days']:g}d{unmatched_s}")
        else:
            L.append(f"   revert pairs: n/a — {rp['reason']}")
        L.append(f"   change-failure proxy {oc['change_failure_rate']:.0%} "
                 f"({oc['change_failure_commits']} commits)")
        L.append("")

    # --- Release cadence & lead time (Package K): tag-based proxies —
    # context, never scored. Tags aren't deploys; an untagged repo shows n/a,
    # never a penalty. ---
    rc = result.get("release_cadence")
    if rc:
        L.append("  Release cadence & lead time — context, not scored:")
        L.append(f"   {glossary.short('release_cadence')}")
        if rc["status"] == "scored":
            cad = rc["cadence"]
            L.append(f"   {cad['tags_per_month']:g} tags/mo  ·  median gap "
                     f"{cad['median_gap_days']:g}d  ({rc['window']}, "
                     f"{rc['tags_matched']} tags)")
            lt = rc["lead_time"]
            if lt["status"] == "scored":
                L.append(f"   lead time: median {lt['median_days']:g}d "
                         f"({lt['commits']} commits)")
            else:
                L.append(f"   lead time: n/a — {lt['reason']}")
        else:
            L.append(f"   n/a — {rc['reason']}")
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


def _spark_series(values, max_val: float) -> str:
    """Sparkline that renders None as a blank (a genuine gap, never zero)."""
    out = ""
    for v in values:
        if v is None:
            out += " "
        else:
            out += _SPARK[min(7, int(v / max_val * 7))] if max_val > 0 else _SPARK[0]
    return out


def render_trajectory_cli(result: dict) -> str:
    """The over-time section (shown on `--timeline`). Two gap-aware sparkline rows
    + a period table. The two lines are parallel timelines, NOT a causal claim."""
    t = result.get("trajectory") or {}
    if t.get("status") != "ok":
        return f"\n  Trajectory: n/a — {t.get('reason', 'not enough history')}\n"
    periods = t["periods"]
    adoption = [p["adoption_pct"] for p in periods]
    health = [float(p["health_score"]) if p["health_score"] is not None else None
              for p in periods]
    # Feature C: per-period breadth sparkline + column (n/a when below the
    # contributor floor — team-level only, no per-person data).
    breadth = [p.get("breadth_pct") for p in periods]
    any_breadth = any(b is not None for b in breadth)
    # Chrome accounting (3 indent + label + 2-space gap + spark + 3-space gap +
    # caption). adoption/health captions are short ("0–100%" / "0–100"); the
    # breadth caption is longer due to "(team-level)" so it reserves more.
    L = ["", "  Trajectory — adoption & delivery health over time",
         f"  {len(periods)} periods · ~{t['period_days']}d each · "
         "parallel timelines, NOT a causal link (blank = quiet/thin period)", "",
         f"   adoption  {_adaptive_spark(adoption, chrome=22, max_val=100)}"
         "   0–100%",
         f"   health    {_adaptive_spark(health, chrome=22, max_val=100)}"
         "   0–100"]
    if any_breadth:
        L.append(
            f"   breadth   {_adaptive_spark(breadth, chrome=35, max_val=100)}"
            "   0–100% (team-level)"
        )
    L += [f"   {periods[0]['start']} → {periods[-1]['start']}", ""]
    if any_breadth:
        L.append("   period       commits  adoption  health  breadth")
    else:
        L.append("   period       commits  adoption  health")
    for p in periods:
        ad = f"{p['adoption_pct']:.0f}%" if p["adoption_pct"] is not None else "—"
        h = str(p["health_score"]) if p["health_score"] is not None else "—"
        if any_breadth:
            b_pct = p.get("breadth_pct")
            br = f"{b_pct:.0f}%" if b_pct is not None else "—"
            L.append(f"   {p['start']}  {p['commits']:<7}  {ad:<8}  {h:<6}  {br}")
        else:
            L.append(f"   {p['start']}  {p['commits']:<7}  {ad:<8}  {h}")
    L.append("")
    return "\n".join(L)


def render_impact_markdown(result: dict) -> str:
    if result.get("error"):
        return f"# ShipSignal impact — {result['repo']}\n\n**Error:** {result['error']}\n"
    w = result["window"]
    ad = result["adoption"]
    dh = result["delivery_health"]
    rd = result.get("readiness")
    m = result["metrics"]
    p = m["people"]

    health_cell = (f"{dh['score']}/100 · {dh['grade']}" if dh["status"] == "scored"
                   else f"— ({dh['reason']})")
    ready_cell = f"{rd['score']}/100 · {rd['grade']}" if rd else "—"
    tools = (", ".join(f"{k} {v}" for k, v in ad["per_tool"].items())
             if ad.get("per_tool") else "—")

    an = result.get("analysis") or {}
    _parts = []
    if an.get("merges_excluded") or an.get("maintenance_bots_excluded"):
        _parts.append(f"excluded {an['merges_excluded']} merges + "
                      f"{an['maintenance_bots_excluded']} maintenance-bot commits")
    if an.get("ai_agent_commits"):
        _parts.append(f"{an['ai_agent_commits']} AI-agent commits counted as AI")
    excl = f" *({'; '.join(_parts)})*" if _parts else ""
    _sq = _squash_caveat(ad)
    _rf = _recovery_facts(ad)
    if _rf and _rf["recovered"]:
        adopt_suffix = f" → {_rf['r_level']} {_rf['r_pct']} recovered"
    elif _sq:
        adopt_suffix = " ⚠"
    else:
        adopt_suffix = ""
    L = [f"# ShipSignal — AI impact: {result['repo']}", "",
         f"**{w['first_commit']} → {w['last_commit']} · {w['weeks']} weeks · "
         f"{ad['total_commits']} dev commits**{excl}", "",
         "| | Result | |", "|---|---|---|",
         f"| **AI Adoption** | {ad['level']} · {ad['ai_coauthor_share'] * 100:.0f}%"
         f"{adopt_suffix} | {tools} |",
         f"| **Delivery Health** | {health_cell} | general eng norms, not AI-attributed |",
         f"| **Readiness** | {ready_cell} | static repo state |", ""]

    L += ["## How to read this", ""]
    L += [f"- **{name}** — {glossary.short(key)}" for name, key in glossary.HOWTO_ORDER]
    L.append("")

    L += ["## AI adoption (direct, in-repo signal)", "",
          f"- **{ad['level']} — {ad['ai_coauthor_share'] * 100:.1f}%** "
          f"({ad['ai_commits']}/{ad['total_commits']} commits), a **lower bound** "
          "(some squash/merge pipelines strip trailers; GitHub-native squash keeps them)."]
    if _sq:
        L.append(f"- ⚠ **{_sq[:1].upper() + _sq[1:]}.**")
    _rtext = _recovery_text(ad)
    if _rtext:
        L.append(f"- **Recovery:** {_rtext}.")
    _recipe = _recovery_recipe(ad)
    if _recipe:
        L.append("- Recover squash-dropped attribution (zero network — you run the export):  \n"
                 f"  ```\n  {_recipe[0]}\n  # {_recipe[1]}\n  ```")
    if ad.get("adoption_date"):
        L.append(f"- Adoption date: `{ad['adoption_date']}` "
                 f"({'auto-detected' if ad['adoption_auto_detected'] else 'override'})")
    if ad.get("per_tool"):
        L.append("- Per tool: " + ", ".join(f"`{k}` ({v})" for k, v in ad["per_tool"].items()))
    br = ad.get("breadth") or {}
    if br.get("status") == "scored":
        trend = br.get("trend") or ""
        trend_md = f" · trend: **{trend}**" if trend and trend != "unknown" else ""
        L.append(f"- **Breadth:** {br['breadth_pct']:.0f}% — {br['ai_contributors']} "
                 f"of {br['active_contributors']} active contributors{trend_md}.  \n"
                 f"  *Team-level only — ShipSignal does not score individuals.*")
    elif br.get("status") == "n/a":
        L.append(f"- *Breadth: n/a — {br.get('reason', 'too few contributors')}.*")
    L.append("")

    if dh["status"] == "scored":
        L += ["## Delivery Health (general engineering norms — NOT AI-attributed)", "",
              f"**{dh['score']}/100 · grade {dh['grade']}**", "",
              "| Component | Score | Weight | Flag |", "|---|---|---|---|"]
        for c in dh["components"]:
            val = f"{c['score_frac'] * 100:.0f}%" if c["score_frac"] is not None else c["status"]
            L.append(f"| {c['id']} | {val} | {c['weight']} | {c.get('flag') or ''} |")
        d = dh["descriptive"]
        L += ["", f"*Context (not scored — too noisy to rank health by): "
              f"{d['commits_per_week']:g} commits/wk, "
              f"{d['contributors']} contributors.*", ""]
        focus = _delivery_focus(dh, result["metrics"])
        if focus:
            L += [f"### Where to focus ({len(focus)})", ""]
            L += [f"- **{it['label']}** — {it['detail']}" for it in focus]
            L += ["", f"_<sub>{_DELIVERY_FOCUS_NOTE}</sub>_", ""]
    else:
        L += ["## Delivery Health", "",
              f"*Insufficient data — {dh['reason']}.*", ""]

    # Outcomes (Package J): revert pairs / time-to-correction + the relabeled
    # change-failure proxy — context, never scored.
    oc = result.get("outcomes")
    if oc:
        rp = oc["revert_pairs"]
        L += ["## Outcomes (context — never scored)", ""]
        if rp["status"] == "scored":
            unmatched_md = f" ({rp['unmatched']} unmatched)" if rp["unmatched"] else ""
            L.append(f"- **Revert pairs:** {rp['matched']} · median time-to-correction "
                     f"**{rp['median_days']:g}d**{unmatched_md}")
        else:
            L.append(f"- *Revert pairs: n/a — {rp['reason']}.*")
        L.append(f"- **Change-failure proxy:** {oc['change_failure_rate']:.0%} "
                 f"({oc['change_failure_commits']} commits)")
        L += ["", f"_<sub>{glossary.short('outcomes')}</sub>_", ""]

    # Release cadence & lead time (Package K): tag-based proxies — context,
    # never scored.
    rc = result.get("release_cadence")
    if rc:
        L += ["## Release cadence & lead time (context — never scored)", ""]
        if rc["status"] == "scored":
            cad = rc["cadence"]
            L.append(f"- **Cadence:** {cad['tags_per_month']:g} tags/mo · "
                     f"median gap **{cad['median_gap_days']:g}d** "
                     f"({rc['window']}, {rc['tags_matched']} tags)")
            lt = rc["lead_time"]
            if lt["status"] == "scored":
                L.append(f"- **Lead time:** median **{lt['median_days']:g}d** "
                         f"({lt['commits']} commits)")
            else:
                L.append(f"- *Lead time: n/a — {lt['reason']}.*")
        else:
            L.append(f"- *n/a — {rc['reason']}.*")
        L += ["", f"_<sub>{glossary.short('release_cadence')}</sub>_", ""]

    # Over-time trajectory (always included when there's enough history).
    traj = result.get("trajectory") or {}
    if traj.get("status") == "ok":
        L += ["## Trajectory — over time *(parallel timelines, NOT a causal link)*", "",
              f"*{len(traj['periods'])} periods, ~{traj['period_days']}d each.*", "",
              "| Period | Commits | Adoption | Health |", "|---|---|---|---|"]
        for p in traj["periods"]:
            ad = f"{p['adoption_pct']:.0f}%" if p["adoption_pct"] is not None else "—"
            h = str(p["health_score"]) if p["health_score"] is not None else "—"
            L.append(f"| {p['start']} | {p['commits']} | {ad} | {h} |")
        L.append("")

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
          f"<sub>shipsignal v{__version__} · {result['scanned_at']}</sub>", ""]
    return "\n".join(L)


def _stat_card(label: str, value: str, grade: str | None, sub: str, key: str = "") -> str:
    color = GRADE_COLOR.get(grade, "#4477dd") if grade else "#4477dd"
    grade_chip = (f"<span class='gchip' style='background:{color}'>{_esc(grade)}</span>"
                  if grade else "")
    clabel = _tip(label, key) if key else _esc(label)
    return (f"<div class='card' style='border-top:3px solid {color}'>"
            f"<div class='clabel'>{clabel}</div>"
            f"<div class='cval'>{_esc(value)}{grade_chip}</div>"
            f"<div class='csub'>{_esc(sub)}</div></div>")


def _svg_trajectory(traj: dict, adoption_date: str | None) -> str:
    """Inline SVG line chart: adoption % and delivery health over time. Lines break
    at gaps (None) so quiet/thin periods aren't interpolated. No external deps."""
    periods = traj["periods"]
    n = len(periods)
    W, H, Lm, Rm, Tm, Bm = 680, 250, 44, 16, 24, 40
    pw, ph = W - Lm - Rm, H - Tm - Bm

    def xc(i: int) -> float:
        return Lm + (pw * i / (n - 1) if n > 1 else pw / 2)

    def yc(v: float) -> float:
        return Tm + ph * (1 - v / 100)

    grid = ""
    for gv in (0, 50, 100):
        gy = yc(gv)
        grid += (f"<line x1='{Lm}' y1='{gy:.1f}' x2='{W - Rm}' y2='{gy:.1f}' stroke='#eee'/>"
                 f"<text x='{Lm - 6}' y='{gy + 3:.1f}' text-anchor='end' font-size='10' "
                 f"fill='#aaa'>{gv}</text>")

    def series(key: str, color: str) -> str:
        pts = [None if p[key] is None else (xc(i), yc(float(p[key])))
               for i, p in enumerate(periods)]
        out = ""
        for a, b in zip(pts, pts[1:], strict=False):
            if a and b:  # only connect adjacent present points — gaps break the line
                out += (f"<line x1='{a[0]:.1f}' y1='{a[1]:.1f}' x2='{b[0]:.1f}' "
                        f"y2='{b[1]:.1f}' stroke='{color}' stroke-width='2'/>")
        out += "".join(f"<circle cx='{q[0]:.1f}' cy='{q[1]:.1f}' r='2.5' fill='{color}'/>"
                       for q in pts if q)
        return out

    marker = ""
    if adoption_date:
        for i, p in enumerate(periods):
            if p["start"] <= adoption_date <= p["end"]:
                mx = xc(i)
                marker = (f"<line x1='{mx:.1f}' y1='{Tm}' x2='{mx:.1f}' y2='{Tm + ph}' "
                          f"stroke='#b86a2c' stroke-width='1' stroke-dasharray='3 3'/>"
                          f"<text x='{mx + 3:.1f}' y='{Tm + 10}' font-size='9' "
                          f"fill='#b86a2c'>AI adoption</text>")
                break

    xlabels = (f"<text x='{xc(0):.1f}' y='{H - 14}' font-size='10' fill='#aaa'>"
               f"{_esc(periods[0]['start'])}</text>"
               f"<text x='{xc(n - 1):.1f}' y='{H - 14}' text-anchor='end' font-size='10' "
               f"fill='#aaa'>{_esc(periods[-1]['start'])}</text>")
    legend = (f"<circle cx='{Lm + 6}' cy='{H - 26}' r='3' fill='#4477dd'/>"
              f"<text x='{Lm + 14}' y='{H - 23}' font-size='10' fill='#555'>adoption %</text>"
              f"<circle cx='{Lm + 104}' cy='{H - 26}' r='3' fill='#4c1'/>"
              f"<text x='{Lm + 112}' y='{H - 23}' font-size='10' fill='#555'>"
              f"delivery health</text>")
    return (f"<svg viewBox='0 0 {W} {H}' width='100%' style='max-width:680px' "
            f"xmlns='http://www.w3.org/2000/svg' font-family='sans-serif'>{grid}{marker}"
            f"{series('adoption_pct', '#4477dd')}{series('health_score', '#4c1')}"
            f"{xlabels}{legend}</svg>")


_REPORT_CSS = (
    "body{font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;max-width:780px;"
    "margin:40px auto;padding:0 20px;color:#1a1a1a}"
    "h1{font-size:24px;margin:0 0 10px;font-weight:700}.sub{color:#888;margin-bottom:18px}"
    ".kicker{color:#999;font-size:12px;letter-spacing:.04em;margin-bottom:3px}"
    ".chips{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px}"
    ".chip{background:#f2f4f7;border-radius:6px;padding:3px 10px;font-size:13px;color:#555}"
    ".chip.muted{color:#999;background:#f7f7f8}"
    ".gen{color:#999;font-size:12px;border-top:1px solid #eee;padding-top:10px;margin-bottom:20px}"
    ".cards{display:flex;gap:12px;margin:16px 0 24px}"
    ".card{flex:1;background:#fafafa;border-radius:8px;padding:14px 16px}"
    ".clabel{color:#888;font-size:12px;text-transform:uppercase;letter-spacing:.04em}"
    ".cval{font-size:22px;font-weight:700;margin:4px 0}"
    ".cval .pct{font-size:14px;color:#888;font-weight:400;margin-left:6px}"
    ".csub{color:#777;font-size:12px}"
    ".gchip{display:inline-block;color:#fff;border-radius:5px;padding:0 8px;"
    "font-size:14px;margin-left:6px;vertical-align:middle}"
    ".score{font-size:40px;font-weight:700}.slash{color:#bbb;font-size:22px}"
    ".row{display:flex;align-items:center;margin:6px 0}.cat{width:200px;color:#555}"
    ".bar{flex:1;background:#eee;border-radius:4px;height:14px;overflow:hidden;margin:0 10px}"
    ".bar span{display:block;height:100%;background:#4c1}"
    ".bar.na{background:repeating-linear-gradient(45deg,#eee,#eee 4px,#f6f6f6 4px,#f6f6f6 8px)}"
    ".num{width:120px;text-align:right;color:#333}"
    ".flag{color:#b8860b;font-weight:600;font-size:12px}"
    ".spark{font-family:Consolas,Menlo,monospace;color:#4477dd;letter-spacing:1px;word-break:break-all}"
    ".headline{background:#f4f8ff;border-left:4px solid #4477dd;padding:12px 16px;"
    "border-radius:0 6px 6px 0;margin:14px 0}"
    ".withheld{background:#fff8e1;border-left:4px solid #f0b400;padding:12px 16px;"
    "border-radius:0 6px 6px 0;margin:14px 0}"
    ".hint{color:#666;font-size:13px;font-weight:400}"
    ".tip{border-bottom:1px dotted #bbb;cursor:help}"
    ".howto{margin:4px 0 20px;font-size:13px;background:#fafafa;border-radius:8px;padding:8px 14px}"
    ".howto summary{cursor:pointer;color:#4477dd;font-weight:600}"
    ".howto dt{font-weight:600;margin-top:8px}.howto dd{margin:2px 0 0;color:#555}"
    ".caveat{background:#fbf4ee;border-left:4px solid #b86a2c;padding:12px 16px;"
    "border-radius:0 6px 6px 0;margin:24px 0;color:#444}"
    "h2{font-size:15px;margin-top:28px}sub{color:#aaa}"
    "h3{font-size:13px;margin:18px 0 6px;color:#444}"
    ".focus{margin:6px 0;padding-left:18px}.focus li{margin:4px 0;color:#444}"
)


def render_impact_html(result: dict) -> str:
    if result.get("error"):
        return (
            f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<title>AI impact — {_esc(result["repo"])}</title>'
            f'<style>{_REPORT_CSS}</style></head><body>'
            f'<div class="kicker">ShipSignal · AI impact audit</div>'
            f'<h1>{_esc(result["repo"])}</h1>'
            f'<div class="gen">Generated {_esc(_human_ts(result["scanned_at"]))} · '
            f'shipsignal v{__version__}</div>'
            f'<div class="withheld"><b>No git history</b> — '
            f'AI Adoption and Delivery Health require commit history to compute. '
            f'Readiness scan (static analysis) is shown below.</div>'
            f'</body></html>'
        )
    w = result["window"]
    ad = result["adoption"]
    dh = result["delivery_health"]
    rd = result.get("readiness")
    sq = _squash_caveat(ad)
    pct = ad["ai_coauthor_share"] * 100
    series_rates = [s[1] for s in ad.get("weekly_series", [])]
    # Recent pulse only — mirror the CLI's last-60w window so the strip never
    # overflows on old repos; the full adoption arc lives in the Trajectory chart.
    spark_window = series_rates[-60:]
    spark = _esc(_spark_series(spark_window, max_val=1.0)) if spark_window else ""
    spark_caption = f"last {len(spark_window)}w · 0–100%" if spark_window else ""
    an = result.get("analysis") or {}
    _bits = []
    if an.get("merges_excluded") or an.get("maintenance_bots_excluded"):
        _bits.append(f"excluded {an['merges_excluded']} merges + "
                     f"{an['maintenance_bots_excluded']} maintenance-bot")
    if an.get("ai_agent_commits"):
        _bits.append(f"{an['ai_agent_commits']} AI-agent counted as AI")
    excl_chip = (f"<span class='chip muted'>{_esc(' · '.join(_bits))}</span>") if _bits else ""

    # --- three headline cards ---
    tools = (", ".join(f"{k} {v}" for k, v in ad["per_tool"].items())
             if ad.get("per_tool") else "no AI trailers")
    _rf = _recovery_facts(ad)
    recovered_chip = (f" · → {_esc(_rf['r_level'])} {_rf['r_pct']} recovered"
                      if _rf and _rf["recovered"] else "")
    cards = (f"<div class='card' style='border-top:3px solid #4477dd'>"
             f"<div class='clabel'>{_tip('AI Adoption', 'ai_adoption')}</div>"
             f"<div class='cval'>{ad['level']}<span class='pct'>{pct:.0f}%</span></div>"
             f"<div class='csub'>{_esc(tools)} · lower bound"
             f"{recovered_chip}{' · ⚠ squash' if sq else ''}</div></div>")
    if dh["status"] == "scored":
        cards += _stat_card("Delivery Health", f"{dh['score']}/100 ", dh["grade"],
                            "general eng norms", key="delivery_health")
    else:
        cards += _stat_card("Delivery Health", "—", None, dh["reason"], key="delivery_health")
    if rd:
        cards += _stat_card("Readiness", f"{rd['score']}/100 ", rd["grade"],
                            "static repo state", key="readiness")
    else:
        cards += _stat_card("Readiness", "—", None, "not run", key="readiness")

    # --- delivery-health breakdown ---
    if dh["status"] == "scored":
        rows = ""
        for c in dh["components"]:
            flag = (f"<span class='flag'>{_esc(c['flag'])}</span>" if c.get("flag") else "")
            if c["score_frac"] is None:
                rows += (f"<div class='row'><div class='cat'>{_tip(c['id'], c['id'])}</div>"
                         f"<div class='bar na'></div>"
                         f"<div class='num'>{_esc(c['status'])}</div></div>")
            else:
                rows += (f"<div class='row'><div class='cat'>{_tip(c['id'], c['id'])}</div>"
                         f"<div class='bar'><span style='width:"
                         f"{c['score_frac'] * 100:.0f}%'></span></div>"
                         f"<div class='num'>{c['score_frac'] * 100:.0f}% {flag}</div></div>")
        d = dh["descriptive"]
        ctx = (f"<p class='hint'>Context (not scored): "
               f"{d['commits_per_week']:g} commits/wk · {d['contributors']} contributors.</p>")
        focus = _delivery_focus(dh, result["metrics"])
        focus_html = ""
        if focus:
            items = "".join(f"<li><b>{_esc(it['label'])}</b> — {_esc(it['detail'])}</li>"
                            for it in focus)
            focus_html = (f"<h3>Where to focus</h3><ul class='focus'>{items}</ul>"
                          f"<p class='hint'>{_esc(_DELIVERY_FOCUS_NOTE)}</p>")
        health_block = (f"<h2>{_tip('Delivery Health', 'delivery_health')}</h2>"
                        f"<p class='hint'>{_esc(glossary.short('delivery_health'))}</p>"
                        f"{rows}{ctx}{focus_html}")
    else:
        health_block = (f"<h2>{_tip('Delivery Health', 'delivery_health')}</h2>"
                        f"<div class='withheld'>Insufficient data — {_esc(dh['reason'])}.</div>")

    # --- Outcomes (Package J): revert pairs / time-to-correction + the
    # relabeled change-failure proxy — context, never scored. ---
    oc = result.get("outcomes")
    if oc:
        rp = oc["revert_pairs"]
        if rp["status"] == "scored":
            unmatched_html = (f" <span class='hint'>({rp['unmatched']} unmatched)</span>"
                              if rp["unmatched"] else "")
            revert_line = (f"Revert pairs: <b>{rp['matched']}</b> · median "
                           f"time-to-correction <b>{rp['median_days']:g}d</b>{unmatched_html}")
        else:
            revert_line = f"<span class='hint'>Revert pairs: n/a — {_esc(rp['reason'])}.</span>"
        outcomes_block = (
            f"<h2>{_tip('Outcomes', 'outcomes')} "
            f"<span class='hint'>context, never scored</span></h2>"
            f"<p>{revert_line}</p>"
            f"<p class='hint'>Change-failure proxy: {oc['change_failure_rate']:.0%} "
            f"({oc['change_failure_commits']} commits)</p>"
        )
    else:
        outcomes_block = ""

    # --- Release cadence & lead time (Package K): tag-based proxies —
    # context, never scored. ---
    rc = result.get("release_cadence")
    if rc and rc["status"] == "scored":
        cad = rc["cadence"]
        cadence_line = (f"Cadence: <b>{cad['tags_per_month']:g}</b> tags/mo · median gap "
                        f"<b>{cad['median_gap_days']:g}d</b> "
                        f"<span class='hint'>({rc['window']}, {rc['tags_matched']} tags)</span>")
        lt = rc["lead_time"]
        if lt["status"] == "scored":
            lead_line = (f"<p>Lead time: median <b>{lt['median_days']:g}d</b> "
                        f"<span class='hint'>({lt['commits']} commits)</span></p>")
        else:
            lead_line = f"<p class='hint'>Lead time: n/a — {_esc(lt['reason'])}.</p>"
        release_cadence_block = (
            f"<h2>{_tip('Release cadence', 'release_cadence')} "
            f"<span class='hint'>context, never scored</span></h2>"
            f"<p>{cadence_line}</p>{lead_line}"
        )
    elif rc:
        release_cadence_block = (
            f"<h2>{_tip('Release cadence', 'release_cadence')} "
            f"<span class='hint'>context, never scored</span></h2>"
            f"<div class='withheld'>n/a — {_esc(rc['reason'])}.</div>"
        )
    else:
        release_cadence_block = ""

    # --- before/after bonus ---
    if result.get("score_status") == "scored":
        prows = "".join(
            f"<div class='row'><div class='cat'>{_esc(pl['id'])}</div>"
            f"<div class='bar'><span style='width:{100 * pl['pts'] / pl['max']:.0f}%'></span></div>"
            f"<div class='num'>{pl['pts']:g}/{pl['max']:g}</div></div>"
            if pl.get("pts") is not None else
            f"<div class='row'><div class='cat'>{_esc(pl['id'])}</div>"
            f"<div class='bar na'></div>"
            f"<div class='num'>{_esc(pl.get('status', 'n/a'))}</div></div>"
            for pl in result.get("pillars", [])
        )
        bonus_block = (f"<h2>{_tip('Before/after AI Enablement', 'before_after')}</h2>"
                       f"<p class='hint'>{_esc(glossary.short('before_after'))}</p>"
                       f"<p><span class='score'>{result['score']}</span>"
                       f"<span class='slash'>/100</span></p>{prows}")
    else:
        bonus_block = (f"<h2>{_tip('Before/after AI Enablement', 'before_after')} "
                       f"<span class='hint'>(bonus)</span></h2>"
                       f"<div class='withheld'>n/a — "
                       f"{_esc(result.get('score_withheld_reason', 'see confidence'))}<br>"
                       f"<span class='hint'>A before/after needs a clean pre-AI baseline; the "
                       f"three numbers above stand on their own.</span></div>")

    traj = result.get("trajectory") or {}
    if traj.get("status") == "ok":
        chart = _svg_trajectory(traj, ad.get("adoption_date"))
        traj_block = (f"<h2>{_tip('Trajectory', 'trajectory')} <span class='hint'>over time "
                      f"— parallel timelines, NOT a causal link</span></h2>{chart}")
    else:
        traj_block = ""

    # --- breadth (Feature C) — aggregate only, non-goal line shown inline ---
    br = ad.get("breadth") or {}
    if br.get("status") == "scored":
        trend = br.get("trend") or ""
        trend_html = (f" · <b>{_esc(trend)}</b>" if trend and trend != "unknown" else "")
        breadth_html = (
            f"<br>{_tip('Breadth', 'adoption_breadth')}: {br['breadth_pct']:.0f}% — "
            f"{br['ai_contributors']} of {br['active_contributors']} active "
            f"contributors{trend_html}"
            f"<br><span class='hint'>Team-level only — ShipSignal does not score "
            f"individuals.</span>"
        )
    elif br.get("status") == "n/a":
        breadth_html = (f"<br>{_tip('Breadth', 'adoption_breadth')}: n/a — "
                        f"<span class='hint'>"
                        f"{_esc(br.get('reason', 'too few contributors'))}</span>")
    else:
        breadth_html = ""

    chips_html = (
        f'<span class="chip">{_esc(_human_range(w["first_commit"], w["last_commit"]))}</span>'
        f'<span class="chip">{w["weeks"]:g} weeks</span>'
        f'<span class="chip">{ad["total_commits"]} dev commits</span>{excl_chip}'
    )
    adoption_line = (
        f"Adoption date: <code>{_esc(ad['adoption_date'])}</code>"
        if ad.get("adoption_date")
        else "<span class='hint'>No sustained adoption window detected.</span>"
    )
    rate_line = (
        f"<br>Rate / week: <span class='spark'>{spark}</span> "
        f"<span class='hint'>{spark_caption}</span>"
    ) if spark else ""
    squash_line = (
        f"<div class='hint' style='color:#b86a2c;margin-top:6px'>⚠ {_esc(sq)}</div>"
        if sq else ""
    )
    _rtext = _recovery_text(ad)
    recovery_line = (
        f"<div class='hint' style='color:#2c7a4b;margin-top:6px'>↑ {_esc(_rtext)}</div>"
        if _rtext else ""
    )
    _recipe = _recovery_recipe(ad)
    recipe_line = (
        "<div class='hint' style='margin-top:6px'>Recover squash-dropped attribution "
        f"(zero network — you run the export):<br><code>{_esc(_recipe[0])}</code><br>"
        f"<code># {_esc(_recipe[1])}</code></div>"
        if _recipe else ""
    )

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>AI impact — {_esc(result['repo'])}</title><style>{_REPORT_CSS}</style></head><body>
<div class="kicker">ShipSignal · AI impact audit</div>
<h1>{_esc(result['repo'])}</h1>
<div class="chips">{chips_html}</div>
<div class="gen">Generated {_esc(_human_ts(result['scanned_at']))} · shipsignal v{__version__}</div>

<div class="cards">{cards}</div>

{_how_to_read_html()}

<div class="headline">
  <b>AI adoption {pct:.1f}%</b>
  <span class="hint">({ad['ai_commits']}/{ad['total_commits']} commits — lower bound)</span><br>
  {adoption_line}
  {breadth_html}
  {rate_line}
  <div class="hint" style="margin-top:6px">{_esc(glossary.short('ai_adoption'))}</div>
  {squash_line}
  {recovery_line}
  {recipe_line}
</div>

{health_block}

{outcomes_block}

{release_cadence_block}

{bonus_block}

{traj_block}

<div class="caveat"><b>Attribution caveat.</b> {_esc(result['attribution_caveat'])}</div>
</body></html>"""


# ---------------------------------------------------------------------------
# Unified report — one command, both lenses, one deliverable.
# Combines Impact's three-number header + delivery breakdown with the
# Readiness fix backlog (the missing piece in `impact` alone). This is the
# format the productized audit ships in.
# ---------------------------------------------------------------------------
def _readiness_fix_lines(readiness_result: dict, limit: int = 8) -> list[dict]:
    warns = [f for f in readiness_result.get("findings", []) if f["severity"] != "info"]
    return warns[:limit], max(0, len(warns) - limit)


def render_unified(impact_result: dict, readiness_result: dict, *, color: bool = False) -> str:
    """Plain-text CLI rendering — Impact lens header + Readiness fix backlog."""
    L = [render_impact(impact_result, color=color).rstrip()]
    L.append("")
    rd_headline = ansi.grade(f"{readiness_result['score']}/100 · {readiness_result['grade']}",
                             readiness_result["grade"], color)
    L.append(f"  Readiness {rd_headline}  (full breakdown + fixes below)")
    L.append("")
    for c in readiness_result["categories"]:
        if c["status"] == "scored":
            L.append(f"   {c['id']:<20} {_bar(c['points'], c['max'])} {c['points']:g}/{c['max']:g}")
        else:
            L.append(f"   {c['id']:<20} {'·' * 16} {c['status']}")
    findings = readiness_result.get("findings", [])
    warns = [f for f in findings if f["severity"] != "info"]
    L.append("")
    if warns:
        L.append(f"  Top Readiness fixes ({len(warns)} issues, grouped by area, "
                 "highest payoff first):")
        snippet_ids = _top_n_payoff_ids(findings, n=3)
        for block in _group_fixes(findings):
            shown = [it for it in block["items"]
                     if it.get("_collapsed") or it.get("severity") == "warn"]
            if not shown:
                continue
            L.append("")
            L.append(f"  {block['area']}")
            for it in shown:
                if it.get("_collapsed"):
                    L.append(f"   • {it['evidence']}  · quick")
                    L.append(f"       → {it['fix']}")
                    continue
                L.append(f"   • {_fix_path(it)}: {it['evidence']}{_fix_meta(it)}")
                L.append(f"       → {it['fix']}")
                if id(it) in snippet_ids and it.get("snippet"):
                    L.append("       starter (copy + fill in the placeholders):")
                    L.append(_indent(it["snippet"], "         "))
        L.append("")
        L.append(f"  {_renorm_caveat()}")
    else:
        L.append("  Readiness: no warnings — well set up.")
    L.append("")
    return "\n".join(L)


def render_unified_markdown(impact_result: dict, readiness_result: dict) -> str:
    """Markdown report combining Impact + Readiness — the audit deliverable."""
    L = [render_impact_markdown(impact_result).rstrip()]
    L.append("")
    L.append(f"## Readiness — {readiness_result['score']}/100 · grade {readiness_result['grade']}")
    L.append("")
    L.append("| Category | Score |")
    L.append("|---|---|")
    for cid, val, _pct in _cat_rows(readiness_result):
        L.append(f"| {cid} | {val} |")
    L.append("")
    warns, extra = _readiness_fix_lines(readiness_result)
    if warns:
        findings = readiness_result.get("findings", [])
        L.append(f"### Top Readiness fixes ({len(warns)} total, grouped by area, "
                 "highest payoff first)")
        L.append("")
        for block in _group_fixes(findings):
            shown = [it for it in block["items"]
                     if it.get("_collapsed") or it.get("severity") == "warn"]
            if not shown:
                continue
            L += [f"**{block['area']}**", ""]
            for it in shown:
                if it.get("_collapsed"):
                    L.append(f"- {it['evidence']} — _quick_  \n  → {it['fix']}")
                    continue
                L.append(f"- **{_fix_path(it)}** — {it['evidence']}{_fix_meta(it)}  \n"
                         f"  → {it['fix']}")
                if it.get("snippet"):
                    L += ["", "  <details><summary>Starter — copy + fill in placeholders</summary>",
                          "", "  ```markdown", _indent(it["snippet"], "  "),
                          "  ```", "  </details>", ""]
            L.append("")
        L.append(f"_<sub>{_renorm_caveat()}</sub>_")
    else:
        L.append("### Readiness")
        L.append("")
        L.append("*No warnings — the repo is well set up for agents.*")
    L.append("")
    return "\n".join(L)


def render_unified_html(impact_result: dict, readiness_result: dict) -> str:
    """One-page HTML audit deliverable — Impact three-card header + Readiness fixes."""
    # We weave the readiness section in BEFORE the closing </body> of the impact HTML,
    # rather than re-implementing the whole page.
    impact_html = render_impact_html(impact_result)
    cat_rows = ""
    for cid, val, pct in _cat_rows(readiness_result):
        if pct is None:
            cat_rows += (f"<div class='row'><div class='cat'>{_tip(cid, cid)}</div>"
                         f"<div class='bar na'></div><div class='num'>{_esc(val)}</div></div>")
        else:
            cat_rows += (f"<div class='row'><div class='cat'>{_tip(cid, cid)}</div>"
                         f"<div class='bar'><span style='width:{pct:.0f}%'></span></div>"
                         f"<div class='num'>{_esc(val)}</div></div>")
    findings = readiness_result.get("findings", [])
    warns = [f for f in findings if f["severity"] != "info"]
    if warns:
        body = _render_grouped_fixes_html(findings)
        fixes_block = (f"<h2>Top Readiness fixes ({len(warns)} issues, "
                       f"grouped by area, highest payoff first)</h2>{body}"
                       f"<p class='hint' style='margin-top:14px'>"
                       f"{_esc(_renorm_caveat())}</p>")
    else:
        fixes_block = "<h2>Readiness fixes</h2><p>None — the repo is well set up for agents.</p>"

    color = GRADE_COLOR.get(readiness_result["grade"], "#9f9f9f")
    readiness_section = (
        f"<h2>Readiness — <span style='color:#fff;background:{color};border-radius:5px;"
        f"padding:0 8px;margin-left:6px'>{readiness_result['score']}/100 · "
        f"{_esc(readiness_result['grade'])}</span></h2>"
        f"{cat_rows}{fixes_block}"
    )
    # Inject before </body>; fall through to append if the marker isn't found.
    if "</body>" in impact_html:
        return impact_html.replace("</body>", readiness_section + "</body>", 1)
    return impact_html + readiness_section


def render_badge(result: dict, label: str | None = None) -> str:
    label, value = (label or "AI readiness"), f"{result['score']}/100"
    color = GRADE_COLOR.get(result["grade"], "#9f9f9f")
    lw, rw = int(len(label) * 6.5) + 12, int(len(value) * 6.5) + 12
    w = lw + rw
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="20"
role="img" aria-label="{label}: {value}">
<linearGradient id="s" x2="0" y2="100%"><stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
<stop offset="1" stop-opacity=".1"/></linearGradient>
<rect rx="3" width="{w}" height="20" fill="#555"/>
<rect rx="3" x="{lw}" width="{rw}" height="20" fill="{color}"/>
<rect rx="3" width="{w}" height="20" fill="url(#s)"/>
<g fill="#fff" text-anchor="middle" font-family="Verdana,DejaVu Sans,sans-serif" font-size="11">
<text x="{lw / 2:.0f}" y="14">{label}</text>
<text x="{lw + rw / 2:.0f}" y="14">{value}</text>
</g></svg>"""


def render_badge_json(result: dict, label: str | None = None) -> str:
    """A shields.io endpoint-badge payload (https://shields.io/badges/endpoint-badge).

    Unlike ``render_badge``'s static SVG — which has to be committed and goes
    stale the moment the score changes — this JSON is meant to be republished
    somewhere shields.io can fetch it (a gist, GitHub Pages, ...), so a badge
    pasted into a README stays live without a new commit on every scan.

    ``label`` overrides the shields.io left-hand text (Package G's
    `.shipsignal.toml` `[report].badge_label`); defaults to "readiness".
    """
    color = GRADE_COLOR.get(result["grade"], "#9f9f9f")
    payload = {
        "schemaVersion": 1,
        "label": label or "readiness",
        "message": f"{result['score']}/100",
        "color": color.lstrip("#"),
    }
    return json.dumps(payload, indent=2) + "\n"


# ---------------------------------------------------------------------------
# Trend renderers (Feature S2 — Visual Snapshot Viewer)
# ---------------------------------------------------------------------------
# Each headline has its own scale + display formatter. Keeping these in one
# place so CLI / Markdown / HTML render them identically.
_HEADLINE_LABELS = {
    "readiness": "Readiness",
    "breadth": "Breadth",
    "ai_adoption": "AI Adoption",
    "delivery_health": "Delivery Health",
}
_HEADLINE_SCALES = {
    "readiness": 100,
    "breadth": 100,
    "ai_adoption": 1,           # stored as a fraction 0–1
    "delivery_health": 100,
}


def _fmt_headline_value(name: str, v) -> str:
    """How a current/previous value is displayed (CLI + HTML use the same)."""
    if v is None:
        return "n/a"
    if name == "readiness":
        return f"{v:g}"
    if name == "delivery_health":
        return f"{v:g}/100"
    if name == "breadth":
        return f"{v:g}%"
    if name == "ai_adoption":
        return f"{v * 100:.0f}%"
    return str(v)


def _fmt_headline_delta(name: str, delta) -> str:
    """Render a delta with the right unit. ``None`` means we deliberately
    didn't compute one (one side was n/a); render as an explainer, never 0."""
    if delta is None:
        return ""
    sign = "+" if delta >= 0 else ""
    if name == "ai_adoption":
        # share is 0–1; report in percentage points so the unit matches "58%".
        return f"({sign}{delta * 100:.0f}pp)"
    if name == "breadth":
        return f"({sign}{delta:g}pp)"
    return f"({sign}{delta:g})"


def render_trend(trend: dict) -> str:
    """CLI text rendering of a trend payload — sparkline-driven, honest about
    single-point and empty cases."""
    status = trend.get("status")
    if status == "empty":
        return (f"\n  ShipSignal trend — no snapshots found\n"
                f"  {trend.get('reason', '')}\n")
    repo = trend.get("repo", "")
    if status == "single_point":
        L = ["", f"  ShipSignal trend — {repo}",
             f"  1 snapshot · {trend.get('last', '?')}",
             f"  {trend.get('reason', '')}", ""]
        for name, h in trend["headlines"].items():
            L.append(f"   {_HEADLINE_LABELS[name]:<16} "
                     f"{_fmt_headline_value(name, h['current'])}")
        still_open = (trend.get("fixes") or {}).get("still_open_count", 0)
        L += ["", f"   Open fixes at this point: {still_open}", ""]
        return "\n".join(L)

    L = ["", f"  ShipSignal trend — {repo}",
         f"  {trend['snapshot_count']} snapshots · "
         f"{trend['first']} → {trend['last']}", ""]
    for name, h in trend["headlines"].items():
        scale = _HEADLINE_SCALES[name]
        # Chrome ≈ 3 (indent) + 16 (label) + 1 + 22 (arrow) + 1 + 10 (delta) + 1
        spark = _adaptive_spark(h["series"], chrome=54, max_val=scale)
        prev = h["series"][-2] if len(h["series"]) >= 2 else None
        prev_label = _fmt_headline_value(name, prev)
        cur_label = _fmt_headline_value(name, h["current"])
        delta_label = _fmt_headline_delta(name, h["delta"])
        arrow = f"{prev_label} → {cur_label}"
        L.append(f"   {_HEADLINE_LABELS[name]:<16} "
                 f"{arrow:<22} {delta_label:<10} {spark}")
    L.append("")

    flips = trend.get("category_flips") or []
    for fl in flips:
        L.append(f"  ! {fl['id']} flipped {fl['from']} → {fl['to']} "
                 "(status change, not a score change)")
    if flips:
        L.append("")

    fixes = trend.get("fixes") or {}
    if fixes.get("comparable"):
        resolved = fixes.get("resolved", [])
        added = fixes.get("new", [])
        still = fixes.get("still_open_count", 0)
        L.append(f"  Fixes since last snapshot — "
                 f"{len(resolved)} resolved · {len(added)} new · {still} still open")
        for f in resolved[:5]:
            L.append(f"    ✓ resolved  {f['detector']} {f['path']}")
        for f in added[:5]:
            L.append(f"    + new       {f['detector']} {f['path']}")
        if len(resolved) > 5 or len(added) > 5:
            L.append(f"    … {max(0, len(resolved) - 5) + max(0, len(added) - 5)} more "
                     "(see JSON output for the full list)")
    elif fixes.get("schema_warning"):
        L.append(f"  Fixes diff: skipped — {fixes['schema_warning']}")
    L.append("")

    win = trend.get("window") or {}
    if win.get("growth_warning"):
        L.append(f"  ! {win['growth_warning']}")
        L.append("")
    return "\n".join(L)


def render_trend_markdown(trend: dict) -> str:
    """Markdown form — same content as CLI, formatted for docs/PR bodies."""
    status = trend.get("status")
    if status == "empty":
        return (f"# ShipSignal trend — no snapshots found\n\n"
                f"{trend.get('reason', '')}\n")
    repo = trend.get("repo", "")
    if status == "single_point":
        L = [f"# ShipSignal trend — {repo}", "",
             f"*1 snapshot · {trend.get('last', '?')}*", "",
             f"*{trend.get('reason', '')}*", "",
             "| Metric | Value |", "|---|---|"]
        for name, h in trend["headlines"].items():
            L.append(f"| {_HEADLINE_LABELS[name]} | "
                     f"{_fmt_headline_value(name, h['current'])} |")
        still = (trend.get("fixes") or {}).get("still_open_count", 0)
        L += ["", f"Open fixes at this point: **{still}**", ""]
        return "\n".join(L)

    L = [f"# ShipSignal trend — {repo}", "",
         f"*{trend['snapshot_count']} snapshots · "
         f"{trend['first']} → {trend['last']}*", "",
         "| Metric | Previous | Current | Δ | Trend |",
         "|---|---|---|---|---|"]
    for name, h in trend["headlines"].items():
        spark = _spark_series(h["series"], _HEADLINE_SCALES[name])
        prev = h["series"][-2] if len(h["series"]) >= 2 else None
        L.append(f"| {_HEADLINE_LABELS[name]} | "
                 f"{_fmt_headline_value(name, prev)} | "
                 f"{_fmt_headline_value(name, h['current'])} | "
                 f"{_fmt_headline_delta(name, h['delta']) or '—'} | "
                 f"`{spark}` |")
    L.append("")

    flips = trend.get("category_flips") or []
    for fl in flips:
        L.append(f"> ⚠️ `{fl['id']}` flipped **{fl['from']}** → **{fl['to']}** "
                 "(status change, not a score change).")
    if flips:
        L.append("")

    fixes = trend.get("fixes") or {}
    if fixes.get("comparable"):
        resolved = fixes.get("resolved", [])
        added = fixes.get("new", [])
        still = fixes.get("still_open_count", 0)
        L += ["## Fixes since last snapshot",
              f"- ✅ **{len(resolved)} resolved**",
              f"- ➕ **{len(added)} new**",
              f"- ⏳ {still} still open", ""]
        if resolved:
            L.append("**Resolved:**")
            for f in resolved[:10]:
                L.append(f"- `{f['detector']}` — {f['path']}")
            L.append("")
        if added:
            L.append("**New:**")
            for f in added[:10]:
                L.append(f"- `{f['detector']}` — {f['path']}")
            L.append("")
    elif fixes.get("schema_warning"):
        L += ["## Fixes", f"*Skipped — {fixes['schema_warning']}*", ""]

    win = trend.get("window") or {}
    if win.get("growth_warning"):
        L += [f"> ⚠️ {win['growth_warning']}", ""]

    L += [f"<sub>shipsignal v{__version__}</sub>", ""]
    return "\n".join(L)


def _svg_trend(headlines: dict, dates: list[str]) -> str:
    """Inline SVG: readiness + breadth + AI adoption (normalized to 0–100)
    over snapshot dates. Gap-aware (None values break the line, like the
    trajectory chart). No external deps."""
    n = len(dates)
    W, H, Lm, Rm, Tm, Bm = 680, 240, 44, 16, 24, 40
    pw, ph = W - Lm - Rm, H - Tm - Bm

    def xc(i: int) -> float:
        return Lm + (pw * i / (n - 1) if n > 1 else pw / 2)

    def yc(v: float) -> float:
        return Tm + ph * (1 - v / 100)

    grid = ""
    for gv in (0, 50, 100):
        gy = yc(gv)
        grid += (f"<line x1='{Lm}' y1='{gy:.1f}' x2='{W - Rm}' y2='{gy:.1f}' stroke='#eee'/>"
                 f"<text x='{Lm - 6}' y='{gy + 3:.1f}' text-anchor='end' font-size='10' "
                 f"fill='#aaa'>{gv}</text>")

    def series_norm(name: str, color: str) -> str:
        scale = _HEADLINE_SCALES[name]
        series = headlines[name]["series"]
        # Normalize to 0–100 so all three sit on the same y-axis honestly.
        pts = []
        for i, v in enumerate(series):
            if v is None:
                pts.append(None)
            else:
                pct = v * (100 / scale) if scale != 100 else v
                pts.append((xc(i), yc(pct)))
        out = ""
        for a, b in zip(pts, pts[1:], strict=False):
            if a and b:
                out += (f"<line x1='{a[0]:.1f}' y1='{a[1]:.1f}' "
                        f"x2='{b[0]:.1f}' y2='{b[1]:.1f}' "
                        f"stroke='{color}' stroke-width='2'/>")
        out += "".join(f"<circle cx='{q[0]:.1f}' cy='{q[1]:.1f}' r='2.5' "
                       f"fill='{color}'/>" for q in pts if q)
        return out

    readiness_line = series_norm("readiness", "#4477dd")
    breadth_line = series_norm("breadth", "#b86a2c")
    ai_line = series_norm("ai_adoption", "#4c1")

    xlabels = (f"<text x='{xc(0):.1f}' y='{H - 14}' font-size='10' fill='#aaa'>"
               f"{_esc(dates[0])}</text>"
               f"<text x='{xc(n - 1):.1f}' y='{H - 14}' text-anchor='end' "
               f"font-size='10' fill='#aaa'>{_esc(dates[-1])}</text>")
    legend = (
        f"<circle cx='{Lm + 6}' cy='{H - 26}' r='3' fill='#4477dd'/>"
        f"<text x='{Lm + 14}' y='{H - 23}' font-size='10' fill='#555'>readiness</text>"
        f"<circle cx='{Lm + 92}' cy='{H - 26}' r='3' fill='#b86a2c'/>"
        f"<text x='{Lm + 100}' y='{H - 23}' font-size='10' fill='#555'>breadth</text>"
        f"<circle cx='{Lm + 168}' cy='{H - 26}' r='3' fill='#4c1'/>"
        f"<text x='{Lm + 176}' y='{H - 23}' font-size='10' fill='#555'>ai adoption</text>"
    )
    return (f"<svg viewBox='0 0 {W} {H}' width='100%' style='max-width:680px' "
            f"xmlns='http://www.w3.org/2000/svg' font-family='sans-serif'>"
            f"{grid}{readiness_line}{breadth_line}{ai_line}{xlabels}{legend}</svg>")


def _trend_card(name: str, h: dict) -> str:
    """One stat card for the trend header — current value + delta chip + sparkline."""
    spark = _spark_series(h["series"], _HEADLINE_SCALES[name])
    cur = _fmt_headline_value(name, h["current"])
    prev = h["series"][-2] if len(h["series"]) >= 2 else None
    prev_label = _fmt_headline_value(name, prev) if prev is not None else "—"
    delta_label = _fmt_headline_delta(name, h["delta"])
    color = "#4477dd"
    if h["delta"] is not None:
        if (name == "readiness" or name == "delivery_health" or
                name == "breadth" or name == "ai_adoption"):
            color = "#4c1" if h["delta"] >= 0 else "#e05d44"
    delta_chip = (f"<span class='dchip' style='background:{color}'>"
                  f"{_esc(delta_label)}</span>") if delta_label else ""
    return (f"<div class='tcard'>"
            f"<div class='clabel'>{_esc(_HEADLINE_LABELS[name])}</div>"
            f"<div class='cval'>{_esc(cur)} {delta_chip}</div>"
            f"<div class='csub'>was {_esc(prev_label)}</div>"
            f"<div class='spark'>{_esc(spark)}</div></div>")


def render_trend_html(trend: dict) -> str:
    """HTML deliverable — three stat cards, an SVG over-time chart, fixes
    movement, and the snapshot table. Reuses the audit CSS for visual
    consistency."""
    status = trend.get("status")
    repo = trend.get("repo") or ""

    if status == "empty":
        body = (f"<h1>ShipSignal trend</h1>"
                f"<p>No snapshots found.</p>"
                f"<p class='hint'>{_esc(trend.get('reason', ''))}</p>")
        return _trend_html_wrap(repo, body)

    if status == "single_point":
        cards = "".join(_trend_card(n, h) for n, h in trend["headlines"].items())
        still = (trend.get("fixes") or {}).get("still_open_count", 0)
        body = (
            f"<h1>ShipSignal trend — {_esc(repo)}</h1>"
            f"<div class='sub'>1 snapshot · {_esc(trend.get('last', ''))}</div>"
            f"<div class='headline'>{_esc(trend.get('reason', ''))}</div>"
            f"<div class='cards'>{cards}</div>"
            f"<p>Open fixes at this point: <b>{still}</b></p>"
        )
        return _trend_html_wrap(repo, body)

    cards = "".join(_trend_card(n, h) for n, h in trend["headlines"].items())
    dates = [None] * trend["snapshot_count"]
    # Best-effort: pull dates from the series alignment of one headline; the
    # caller passes us pre-aligned series, so any one of them works.
    # We don't actually need per-snapshot dates here — the SVG uses first/last
    # for tick labels and the series indices for positioning.
    first, last = trend.get("first") or "", trend.get("last") or ""
    dates = [first] + [""] * (trend["snapshot_count"] - 2) + [last] \
        if trend["snapshot_count"] >= 2 else [first]
    chart = _svg_trend(trend["headlines"], dates)

    fixes = trend.get("fixes") or {}
    flips = trend.get("category_flips") or []
    win = trend.get("window") or {}

    notices = ""
    if win.get("growth_warning"):
        notices += f"<div class='withheld'>⚠️ {_esc(win['growth_warning'])}</div>"
    for fl in flips:
        notices += (f"<div class='withheld'>⚠️ <code>{_esc(fl['id'])}</code> "
                    f"flipped <b>{_esc(str(fl['from']))}</b> → "
                    f"<b>{_esc(str(fl['to']))}</b> — status change, not a score change."
                    f"</div>")

    if fixes.get("comparable"):
        resolved = fixes.get("resolved", [])
        added = fixes.get("new", [])
        still = fixes.get("still_open_count", 0)
        resolved_html = "".join(
            f"<li>✅ <code>{_esc(f['detector'])}</code> — {_esc(f['path'])}</li>"
            for f in resolved[:10]
        ) or "<li class='hint'>none</li>"
        new_html = "".join(
            f"<li>➕ <code>{_esc(f['detector'])}</code> — {_esc(f['path'])}</li>"
            for f in added[:10]
        ) or "<li class='hint'>none</li>"
        fixes_block = (
            f"<h2>Fixes since last snapshot</h2>"
            f"<div class='fixrow'>"
            f"<div><b>{len(resolved)} resolved</b><ul>{resolved_html}</ul></div>"
            f"<div><b>{len(added)} new</b><ul>{new_html}</ul></div>"
            f"<div><b>{still} still open</b></div>"
            f"</div>"
        )
    elif fixes.get("schema_warning"):
        fixes_block = (f"<h2>Fixes</h2><div class='withheld'>"
                       f"Skipped — {_esc(fixes['schema_warning'])}</div>")
    else:
        fixes_block = ""

    body = (
        f"<h1>ShipSignal trend — {_esc(repo)}</h1>"
        f"<div class='sub'>{trend['snapshot_count']} snapshots · "
        f"{_esc(first)} → {_esc(last)}</div>"
        f"{notices}"
        f"<div class='cards'>{cards}</div>"
        f"<h2>Over time</h2>"
        f"<p class='hint'>All three series normalized to 0–100 for one axis. "
        f"Gap = a snapshot where the metric was n/a (e.g. solo repo, breadth not "
        f"meaningful). Never zero-filled.</p>"
        f"{chart}"
        f"{fixes_block}"
    )
    return _trend_html_wrap(repo, body)


def _trend_html_wrap(repo: str, body: str) -> str:
    """Shared HTML chrome for trend views — same CSS family as the audit pages
    so a `trend.html` next to a `report.html` looks at home."""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>ShipSignal trend — {_esc(repo)}</title><style>
body{{font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;max-width:780px;
margin:40px auto;padding:0 20px;color:#1a1a1a}}
h1{{font-size:18px;margin-bottom:2px}}h2{{font-size:15px;margin-top:28px}}
.sub{{color:#888;margin-bottom:18px}}
.cards{{display:flex;gap:12px;margin:16px 0 24px;flex-wrap:wrap}}
.tcard{{flex:1;min-width:160px;background:#fafafa;border-radius:8px;padding:14px 16px;
border-top:3px solid #4477dd}}
.clabel{{color:#888;font-size:12px;text-transform:uppercase;letter-spacing:.04em}}
.cval{{font-size:22px;font-weight:700;margin:4px 0}}
.csub{{color:#777;font-size:12px}}
.dchip{{display:inline-block;color:#fff;border-radius:5px;padding:1px 8px;
font-size:12px;margin-left:6px;vertical-align:middle}}
.spark{{font-family:Consolas,Menlo,monospace;color:#4477dd;letter-spacing:2px;margin-top:6px}}
.headline{{background:#f4f8ff;border-left:4px solid #4477dd;padding:12px 16px;
border-radius:0 6px 6px 0;margin:14px 0}}
.withheld{{background:#fff8e1;border-left:4px solid #f0b400;padding:10px 14px;
border-radius:0 6px 6px 0;margin:10px 0;color:#444}}
.hint{{color:#666;font-size:13px;font-weight:400}}
.fixrow{{display:flex;gap:18px;flex-wrap:wrap}}
.fixrow > div{{flex:1;min-width:200px}}
ul{{padding-left:18px}}li{{margin:6px 0}}
code{{background:#f0f0f0;padding:1px 5px;border-radius:3px;font-size:12px}}
sub{{color:#aaa}}
</style></head><body>
{body}
<p><sub>shipsignal v{__version__}</sub></p>
</body></html>"""
