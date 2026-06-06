#!/usr/bin/env python3
"""build_dashboard.py - render a self-contained dashboard of all pipeline runs.

Usage:
    python dashboard/build_dashboard.py

Scans pipeline/<name>/ for each run and writes dashboard/index.html showing, per run:
  * the source video LINK that ran
  * the requirement doc (SRS) it produced (clickable)
  * how many user stories were created
  * each story and WHAT IT TRACES TO (requirement FR/NFR ids) + epic + priority + status

No third-party deps. Open dashboard/index.html in a browser; re-run to refresh.
"""
import html
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPE = os.path.join(ROOT, "pipeline")
OUT = os.path.join(ROOT, "dashboard", "index.html")


def esc(s):
    return html.escape(str(s)) if s is not None else ""


def load_runs():
    runs = []
    if not os.path.isdir(PIPE):
        return runs
    for name in sorted(os.listdir(PIPE)):
        d = os.path.join(PIPE, name)
        sp = os.path.join(d, "state.json")
        if not os.path.isfile(sp):
            continue
        st = json.load(open(sp, encoding="utf-8-sig"))
        stories = []
        bj = os.path.join(d, "stories", "backlog.json")
        if os.path.isfile(bj):
            stories = json.load(open(bj, encoding="utf-8-sig")).get("stories", [])
        srs = None
        for f in os.listdir(d):
            if f.endswith("-SRS.html"):
                srs = f"../pipeline/{name}/{f}"
                break
        st["_stories"], st["_srs"], st["_name"] = stories, srs, name
        runs.append(st)
    return runs


def story_rows(stories):
    out = ""
    for s in stories:
        traces = " ".join(f'<span class="pill fr">{esc(t)}</span>' for t in s.get("traces_to", []))
        dep = " ".join(f'<span class="pill dep">{esc(t)}</span>' for t in s.get("depends_on", [])) or "—"
        pr = esc(s.get("priority", ""))
        out += (f'<tr><td class="mono">{esc(s.get("id"))}</td>'
                f'<td>{esc(s.get("title"))}</td>'
                f'<td><span class="pill epic">{esc(s.get("epic"))}</span></td>'
                f'<td><span class="pri {pr}">{pr}</span></td>'
                f'<td>{traces or "—"}</td><td>{dep}</td></tr>')
    return out


def run_card(r):
    src = r.get("source", "")
    link = f'<a href="{esc(src)}" target="_blank">{esc(src[:70])}{"…" if len(src) > 70 else ""}</a>' if src else "—"
    srs = (f'<a class="btn" href="{esc(r["_srs"])}" target="_blank">Open requirement doc (SRS)</a>'
           if r.get("_srs") else '<span class="muted">SRS not rendered</span>')
    n = len(r["_stories"])
    epics = sorted({s.get("epic", "") for s in r["_stories"]})
    epics_html = " ".join(f'<span class="pill epic">{esc(e)}</span>' for e in epics if e)
    return f"""
    <div class="card">
      <div class="chead">
        <div><h2>{esc(r["_name"])}</h2>
          <div class="meta"><b>Ran link:</b> {link} &nbsp;·&nbsp; <b>Duration:</b> {esc(r.get("duration","—"))}
            &nbsp;·&nbsp; <b>Stage:</b> <span class="stage">{esc(r.get("stage","—"))}</span></div>
        </div>
        <div class="counts"><div class="big">{n}</div><div class="lbl">user stories</div></div>
      </div>
      <div class="row2">{srs} <span class="epics">{epics_html}</span></div>
      <table>
        <thead><tr><th>Story</th><th>Title</th><th>Epic</th><th>Priority</th>
          <th>Traces to (requirements)</th><th>Depends on</th></tr></thead>
        <tbody>{story_rows(r["_stories"])}</tbody>
      </table>
    </div>"""


PAGE = """<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>rahulagents — Pipeline Dashboard</title>
<style>
 :root{{--acc:#2563eb;--bg:#f6f7f9;--card:#fff;--bd:#e3e6ea;--ink:#1f2430;--mut:#6b7280}}
 *{{box-sizing:border-box}}body{{font-family:system-ui,Segoe UI,Roboto,sans-serif;margin:0;background:var(--bg);color:var(--ink)}}
 .wrap{{max-width:1100px;margin:0 auto;padding:26px 20px 70px}}
 h1{{font-size:24px;margin:0 0 2px}} .sub{{color:var(--mut);margin:0 0 18px;font-size:14px}}
 .summary{{display:flex;gap:14px;margin-bottom:22px;flex-wrap:wrap}}
 .stat{{background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:14px 20px;min-width:140px}}
 .stat .n{{font-size:26px;font-weight:800}} .stat .l{{color:var(--mut);font-size:12px}}
 .card{{background:var(--card);border:1px solid var(--bd);border-radius:14px;padding:18px 20px;margin-bottom:20px}}
 .chead{{display:flex;justify-content:space-between;align-items:flex-start;gap:16px}}
 h2{{margin:0;font-size:19px}} .meta{{color:var(--mut);font-size:13px;margin-top:6px}}
 .meta a{{color:var(--acc);text-decoration:none}} .meta a:hover{{text-decoration:underline}}
 .counts{{text-align:center}} .big{{font-size:34px;font-weight:800;color:var(--acc);line-height:1}}
 .lbl{{font-size:11px;color:var(--mut);text-transform:uppercase;letter-spacing:.04em}}
 .row2{{margin:12px 0 8px;display:flex;align-items:center;gap:12px;flex-wrap:wrap}}
 .btn{{background:var(--acc);color:#fff;text-decoration:none;font-size:13px;font-weight:600;padding:8px 14px;border-radius:8px}}
 .epics{{display:flex;gap:5px;flex-wrap:wrap}}
 table{{width:100%;border-collapse:collapse;margin-top:8px;font-size:13px}}
 th{{background:#0f172a;color:#fff;text-align:left;padding:7px 9px;font-weight:600;font-size:12px}}
 td{{border:1px solid var(--bd);padding:6px 9px;vertical-align:top}}
 tr:nth-child(even) td{{background:#f8fafc}} .mono{{font-family:ui-monospace,Consolas,monospace;font-weight:700}}
 .pill{{display:inline-block;font-size:11px;font-weight:700;padding:2px 7px;border-radius:10px;margin:1px}}
 .pill.fr{{background:#eef2ff;color:#3730a3}} .pill.dep{{background:#f1f5f9;color:#475569}} .pill.epic{{background:#ecfeff;color:#0e7490}}
 .pri{{font-size:11px;font-weight:800;padding:2px 7px;border-radius:10px}}
 .high{{background:#fee2e2;color:#991b1b}} .medium{{background:#fef3c7;color:#92400e}} .low{{background:#f1f5f9;color:#475569}}
 .stage{{font-weight:700;color:#b45309}} .muted{{color:var(--mut);font-size:13px}}
 .note{{background:#eef4ff;border:1px solid #c7dbff;border-radius:10px;padding:10px 14px;font-size:13px;margin-bottom:18px}}
</style></head><body><div class="wrap">
 <h1>rahulagents — Pipeline Dashboard</h1>
 <p class="sub">Every video link that ran → its requirement doc → the user stories created → what each story traces to.</p>
 <div class="note">Self-contained &amp; separate: all runs live under <code>rahulagents/pipeline/</code>. Nothing is written into py2026.</div>
 <div class="summary">{summary}</div>
 {cards}
</div></body></html>"""


def main():
    runs = load_runs()
    total_stories = sum(len(r["_stories"]) for r in runs)
    total_reqs = len({t for r in runs for s in r["_stories"] for t in s.get("traces_to", [])})
    summary = (f'<div class="stat"><div class="n">{len(runs)}</div><div class="l">videos run</div></div>'
               f'<div class="stat"><div class="n">{total_stories}</div><div class="l">user stories</div></div>'
               f'<div class="stat"><div class="n">{total_reqs}</div><div class="l">requirements traced</div></div>')
    cards = "\n".join(run_card(r) for r in runs) or '<div class="card"><p class="muted">No runs yet.</p></div>'
    html_out = PAGE.format(summary=summary, cards=cards)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html_out)
    print(f"Wrote {OUT} ({len(runs)} runs, {total_stories} stories)")


if __name__ == "__main__":
    main()
