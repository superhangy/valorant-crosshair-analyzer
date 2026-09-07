"""
Render the crosshair-coaching result as a single self-contained HTML page
(no external files -- the worst-reveal screenshots are embedded as base64),
so the portable AimCoach build can just open it in the user's browser.

Consumes the same values coach_clip.py already computes for the markdown
report: me / base distributions, vertical offset, filter counts, tip list.
"""

import base64
import html
import re
from pathlib import Path

PREAIMED_THRESHOLD_PCT = 5.0


def _md_inline(text: str) -> str:
    """**bold** -> <strong>, escape the rest."""
    parts = re.split(r"(\*\*[^*]+\*\*)", text)
    out = []
    for p in parts:
        if p.startswith("**") and p.endswith("**"):
            out.append(f"<strong>{html.escape(p[2:-2])}</strong>")
        else:
            out.append(html.escape(p))
    return "".join(out)


def _img_data_uri(path: Path, max_bytes: int = 1_200_000) -> "str | None":
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if len(raw) > max_bytes:
        # Still embed it -- a coaching report with 5 big screenshots is well
        # under any sane page-size limit; the cap is just a sanity guard.
        pass
    return "data:image/jpeg;base64," + base64.b64encode(raw).decode("ascii")


def _verdict(me: dict, base: dict) -> tuple:
    """(headline, css_class) summarising how the learner compares."""
    if not me.get("n"):
        return ("No reveals to analyse", "neutral")
    ratio = me["median"] / base["median"] if base.get("median") else None
    if ratio is None:
        return ("Analysis complete", "neutral")
    if ratio <= 1.3:
        return ("Near pro-level pre-aim", "good")
    if ratio <= 2.0:
        return ("Solid, but not pre-placed", "ok")
    if ratio <= 3.5:
        return ("Reacting, not pre-aiming", "warn")
    return ("Crosshair discipline needs work", "bad")


_CSS = """
:root { color-scheme: dark; }
* { box-sizing: border-box; }
body { margin: 0; padding: 2rem 1rem 4rem; background: #0f1117; color: #e6e6e6;
  font: 15px/1.6 system-ui, "Segoe UI", Roboto, sans-serif; }
.wrap { max-width: 860px; margin: 0 auto; }
h1 { font-size: 1.5rem; margin: 0 0 .2rem; }
h2 { font-size: 1.05rem; margin: 2.2rem 0 .8rem; color: #9fb2c9;
  text-transform: uppercase; letter-spacing: .06em; }
.sub { color: #7c8798; font-size: .85rem; margin-bottom: 1.6rem; }
.verdict { display: inline-block; padding: .5rem 1rem; border-radius: .5rem;
  font-weight: 600; font-size: 1.1rem; margin: .4rem 0 1rem; }
.verdict.good { background: #14532d; color: #bbf7d0; }
.verdict.ok   { background: #1e3a5f; color: #bfdbfe; }
.verdict.warn { background: #713f12; color: #fde68a; }
.verdict.bad  { background: #7f1d1d; color: #fecaca; }
.verdict.neutral { background: #27272a; color: #d4d4d8; }
table { border-collapse: collapse; width: 100%; margin: .5rem 0; }
th, td { text-align: left; padding: .55rem .7rem; border-bottom: 1px solid #232838; }
th { color: #9fb2c9; font-weight: 600; }
td.you { font-weight: 700; color: #fff; }
td.num { font-variant-numeric: tabular-nums; }
.tips li { margin: .5rem 0; }
.filter { color: #b9c2d0; font-size: .92rem; }
.filter b { color: #fff; }
.shots { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: .8rem; margin-top: .6rem; }
.shot { background: #171a24; border: 1px solid #232838; border-radius: .5rem;
  overflow: hidden; }
.shot img { display: block; width: 100%; }
.shot .cap { padding: .4rem .6rem; font-size: .82rem; color: #9fb2c9; }
.disclaimer { margin-top: 3rem; padding-top: 1rem; border-top: 1px solid #232838;
  color: #6b7280; font-size: .8rem; }
"""


def write_html_report(outdir: Path, clip: Path, me: dict, base: dict, voff,
                      counts: dict, tips: list, kept_rows: list) -> Path:
    v_head, v_cls = _verdict(me, base)

    rows_html = ""
    if me.get("n"):
        def r(label, you, pro, bold=False):
            you_cls = "you num" if bold else "num"
            return (f"<tr><td>{html.escape(label)}</td>"
                    f"<td class='{you_cls}'>{you}</td>"
                    f"<td class='num'>{pro}</td></tr>")
        rows_html += r("reveals analysed", me["n"], base.get("n", "-"))
        rows_html += r("median pre-aim (% screen width)",
                       f"{me['median']:.2f}", f"{base['median']:.2f}", bold=True)
        rows_html += r("mean", f"{me['mean']:.2f}",
                       f"{base.get('mean', float('nan')):.2f}")
        rows_html += r("p90 (worst 10%)", f"{me['p90']:.2f}",
                       f"{base.get('p90', float('nan')):.2f}")
        rows_html += r(f"pre-aimed rate (&le; {PREAIMED_THRESHOLD_PCT:.0f}%)",
                       f"{me['preaimed_pct']:.0f}%", f"{base['preaimed_pct']:.0f}%",
                       bold=True)
        rows_html += r("best / worst single reveal",
                       f"{me['best']:.1f}% / {me['worst']:.1f}%", "-")

    tips_html = "\n".join(f"<li>{_md_inline(t)}</li>" for t in tips)

    shots_html = ""
    worst = sorted(kept_rows, key=lambda x: -float(x["distance_pct_width"]))[:5]
    for x in worst:
        ts = float(x["timestamp_s"])
        uri = _img_data_uri(outdir / f"t{ts:07.2f}s.jpg")
        if not uri:
            continue
        pct = float(x["distance_pct_width"])
        shots_html += (f"<figure class='shot'><img src='{uri}' alt='reveal at {ts:.1f}s'>"
                       f"<figcaption class='cap'>t={ts:.1f}s &nbsp; crosshair {pct:.0f}% "
                       f"of screen width from the head</figcaption></figure>")

    c = counts
    filt = (f"<p class='filter'>The tool detected <b>{c['total']}</b> possible enemy "
            f"reveals, then filtered out false positives (teammates, UI, your own "
            f"gun): auto-kept <b>{c['auto_keep']}</b>, auto-dropped "
            f"<b>{c['auto_drop']}</b>, you spot-checked <b>{c['uncertain']}</b> "
            f"(kept {c['spot_keep']}, dropped {c['spot_drop']}). "
            f"<b>{c['kept']}</b> real reveals were scored.</p>")

    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Crosshair coaching -- {html.escape(clip.name)}</title>
<style>{_CSS}</style></head>
<body><div class="wrap">
<h1>Crosshair coaching</h1>
<div class="sub">{html.escape(clip.name)}<br>Pro baseline: {html.escape(str(base.get('source', '')))}</div>

<div class="verdict {v_cls}">{html.escape(v_head)}</div>

<h2>Your numbers vs pro</h2>
<table><tr><th>metric</th><th>you</th><th>pro baseline</th></tr>
{rows_html}</table>

<h2>Coaching</h2>
<ul class="tips">
{tips_html}
</ul>

<h2>Your 5 worst reveals</h2>
<p class="filter">Blue box = detected enemy head, yellow cross = your crosshair. For
each: was the crosshair just badly placed, or were you caught mid-rotate / reload?</p>
<div class="shots">{shots_html or "<p class='filter'>No annotated frames available.</p>"}</div>

<h2>How the reveals were filtered</h2>
{filt}

<p class="disclaimer">Auto-filtered with the ally / gunmodel / enemy classifiers
(~95% accurate). Good for tracking your own trend over time; the numbers move a
little run to run. Not a substitute for a coach watching the VOD.</p>
</div></body></html>
"""
    out = outdir / "coaching_report.html"
    out.write_text(page, encoding="utf-8")
    return out
