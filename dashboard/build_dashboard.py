#!/usr/bin/env python3
"""build_dashboard.py - dashboard of all pipeline runs (static build OR live server).

Usage:
    python dashboard/build_dashboard.py            # static -> dashboard/index.html
    python dashboard/build_dashboard.py --serve [port]   # live, auto-refreshing UI

Per run it shows: the source video LINK that ran, its requirement doc (SRS), how many
user stories were created, each story's traceability (FR/NFR ids it traces to), and a
REQUIREMENT -> STORIES reverse map. The live server rebuilds on every request (so it
reflects new runs without re-running anything) and serves the SRS, the stories folder,
and each story file in-browser.

No third-party deps.
"""
import html
import json
import os
import sys
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, quote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPE = os.path.join(ROOT, "pipeline")
OUT = os.path.join(ROOT, "dashboard", "index.html")


def esc(s):
    return html.escape(str(s)) if s is not None else ""


def jload(p):
    return json.load(open(p, encoding="utf-8-sig"))


def load_runs():
    runs = []
    if not os.path.isdir(PIPE):
        return runs
    for name in sorted(os.listdir(PIPE)):
        d = os.path.join(PIPE, name)
        sp = os.path.join(d, "state.json")
        if not os.path.isfile(sp):
            continue
        st = jload(sp)
        stories = []
        bj = os.path.join(d, "stories", "backlog.json")
        if os.path.isfile(bj):
            stories = jload(bj).get("stories", [])
        srs_file = next((f for f in os.listdir(d) if f.endswith("-SRS.html")), None)
        st["_stories"], st["_srs_file"], st["_name"] = stories, srs_file, name
        runs.append(st)
    return runs


def reverse_map(stories):
    rev = defaultdict(list)
    for s in stories:
        for t in s.get("traces_to", []):
            rev[t].append(s.get("id"))
    return dict(sorted(rev.items()))


def story_rows(stories, mode, name):
    out = ""
    for s in stories:
        traces = " ".join(f'<span class="pill fr">{esc(t)}</span>' for t in s.get("traces_to", [])) or "—"
        dep = " ".join(f'<span class="pill dep">{esc(t)}</span>' for t in s.get("depends_on", [])) or "—"
        pr = esc(s.get("priority", "")).lower()
        sid = s.get("id")
        title = esc(s.get("title"))
        if mode == "serve":
            title = f'<a href="/story?run={quote(name)}&id={quote(str(sid))}" target="_blank">{title}</a>'
        out += (f'<tr><td class="mono">{esc(sid)}</td><td>{title}</td>'
                f'<td><span class="pill epic">{esc(s.get("epic"))}</span></td>'
                f'<td><span class="pri {pr}">{esc(s.get("priority"))}</span></td>'
                f'<td>{traces}</td><td>{dep}</td></tr>')
    return out


def coverage_html(stories):
    rev = reverse_map(stories)
    if not rev:
        return ""
    items = "".join(
        f'<tr><td class="mono"><span class="pill fr">{esc(fr)}</span></td>'
        f'<td>{" ".join(f"<span class=\'pill dep\'>{esc(i)}</span>" for i in ids)}</td></tr>'
        for fr, ids in rev.items())
    return (f'<details class="cov"><summary>Requirement → stories ({len(rev)} requirements)</summary>'
            f'<table class="covtbl"><thead><tr><th>Requirement</th><th>Covered by</th></tr></thead>'
            f'<tbody>{items}</tbody></table></details>')


def run_card(r, mode):
    name = r["_name"]
    src = r.get("source", "")
    link = (f'<a href="{esc(src)}" target="_blank">{esc(src[:72])}{"…" if len(src) > 72 else ""}</a>'
            if src else "—")
    if r.get("_srs_file"):
        href = f'/srs?run={quote(name)}' if mode == "serve" else f'../pipeline/{name}/{r["_srs_file"]}'
        srs = f'<a class="btn" href="{esc(href)}" target="_blank">Open requirement doc (SRS)</a>'
    else:
        srs = '<span class="muted">SRS not rendered</span>'
    if mode == "serve":
        browse = f'<a class="btn ghost" href="/stories?run={quote(name)}" target="_blank">Browse stories</a>'
    else:
        browse = f'<span class="muted">stories: pipeline/{esc(name)}/stories/</span>'
    n = len(r["_stories"])
    epics = " ".join(f'<span class="pill epic">{esc(e)}</span>'
                     for e in sorted({s.get("epic", "") for s in r["_stories"]}) if e)
    return f"""
    <div class="card">
      <div class="chead">
        <div><h2>{esc(name)}</h2>
          <div class="meta"><b>Ran link:</b> {link} &nbsp;·&nbsp; <b>Duration:</b> {esc(r.get("duration","—"))}
            &nbsp;·&nbsp; <b>Stage:</b> <span class="stage">{esc(r.get("stage","—"))}</span></div>
        </div>
        <div class="counts"><div class="big">{n}</div><div class="lbl">user stories</div></div>
      </div>
      <div class="row2">{srs} {browse} <span class="epics">{epics}</span></div>
      <table><thead><tr><th>Story</th><th>Title</th><th>Epic</th><th>Priority</th>
        <th>Traces to (requirements)</th><th>Depends on</th></tr></thead>
        <tbody>{story_rows(r["_stories"], mode, name)}</tbody></table>
      {coverage_html(r["_stories"])}
    </div>"""


CSS = """
 :root{--acc:#2563eb;--bg:#f6f7f9;--card:#fff;--bd:#e3e6ea;--ink:#1f2430;--mut:#6b7280}
 *{box-sizing:border-box}body{font-family:system-ui,Segoe UI,Roboto,sans-serif;margin:0;background:var(--bg);color:var(--ink)}
 .wrap{max-width:1100px;margin:0 auto;padding:26px 20px 70px}
 h1{font-size:24px;margin:0 0 2px} .sub{color:var(--mut);margin:0 0 18px;font-size:14px}
 .summary{display:flex;gap:14px;margin-bottom:22px;flex-wrap:wrap}
 .stat{background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:14px 20px;min-width:140px}
 .stat .n{font-size:26px;font-weight:800} .stat .l{color:var(--mut);font-size:12px}
 .card{background:var(--card);border:1px solid var(--bd);border-radius:14px;padding:18px 20px;margin-bottom:20px}
 .chead{display:flex;justify-content:space-between;align-items:flex-start;gap:16px}
 h2{margin:0;font-size:19px} .meta{color:var(--mut);font-size:13px;margin-top:6px}
 .meta a{color:var(--acc);text-decoration:none} .meta a:hover{text-decoration:underline}
 .counts{text-align:center} .big{font-size:34px;font-weight:800;color:var(--acc);line-height:1}
 .lbl{font-size:11px;color:var(--mut);text-transform:uppercase;letter-spacing:.04em}
 .row2{margin:12px 0 8px;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
 .btn{background:var(--acc);color:#fff;text-decoration:none;font-size:13px;font-weight:600;padding:8px 14px;border-radius:8px}
 .btn.ghost{background:#fff;color:var(--acc);border:1px solid var(--acc)}
 table{width:100%;border-collapse:collapse;margin-top:8px;font-size:13px}
 th{background:#0f172a;color:#fff;text-align:left;padding:7px 9px;font-weight:600;font-size:12px}
 td{border:1px solid var(--bd);padding:6px 9px;vertical-align:top}
 tr:nth-child(even) td{background:#f8fafc} .mono{font-family:ui-monospace,Consolas,monospace;font-weight:700}
 .pill{display:inline-block;font-size:11px;font-weight:700;padding:2px 7px;border-radius:10px;margin:1px}
 .pill.fr{background:#eef2ff;color:#3730a3} .pill.dep{background:#f1f5f9;color:#475569} .pill.epic{background:#ecfeff;color:#0e7490}
 .pri{font-size:11px;font-weight:800;padding:2px 7px;border-radius:10px}
 .high{background:#fee2e2;color:#991b1b} .medium{background:#fef3c7;color:#92400e} .low{background:#f1f5f9;color:#475569}
 .stage{font-weight:700;color:#b45309} .muted{color:var(--mut);font-size:13px}
 .note{background:#eef4ff;border:1px solid #c7dbff;border-radius:10px;padding:10px 14px;font-size:13px;margin-bottom:18px}
 details.cov{margin-top:10px} details.cov summary{cursor:pointer;font-size:13px;font-weight:600;color:var(--acc)}
 .covtbl{max-width:520px} pre{background:#0d1117;color:#d1d5db;padding:16px;border-radius:10px;overflow:auto;white-space:pre-wrap;font:12.5px/1.5 ui-monospace,Consolas,monospace}
"""


def render(mode):
    runs = load_runs()
    total_stories = sum(len(r["_stories"]) for r in runs)
    total_reqs = len({t for r in runs for s in r["_stories"] for t in s.get("traces_to", [])})
    refresh = '<span class="muted">· live (rebuilds on refresh)</span>' if mode == "serve" else ""
    summary = (f'<div class="stat"><div class="n">{len(runs)}</div><div class="l">videos run</div></div>'
               f'<div class="stat"><div class="n">{total_stories}</div><div class="l">user stories</div></div>'
               f'<div class="stat"><div class="n">{total_reqs}</div><div class="l">requirements traced</div></div>')
    cards = "\n".join(run_card(r, mode) for r in runs) or '<div class="card"><p class="muted">No runs yet.</p></div>'
    return f"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>rahulagents — Pipeline Dashboard</title>
<style>{CSS}</style></head><body><div class="wrap">
 <h1>rahulagents — Pipeline Dashboard {refresh}</h1>
 <p class="sub">Every video link that ran → its requirement doc → the user stories created → what each story traces to.</p>
 <div class="note">Self-contained &amp; separate: all runs live under <code>rahulagents/pipeline/</code>. Nothing is written into py2026.</div>
 <div class="summary">{summary}</div>
 {cards}
</div></body></html>"""


def md_to_page(name, sid, md):
    return (f"<!doctype html><meta charset=utf-8><title>{esc(sid)} — {esc(name)}</title>"
            f"<style>{CSS}</style><div class='wrap'><a href='/stories?run={quote(name)}'>← stories</a>"
            f"<h1>{esc(sid)}</h1><pre>{esc(md)}</pre></div>")


# ---- static build ----
def build_static():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w", encoding="utf-8").write(render("static"))
    runs = load_runs()
    print(f"Wrote {OUT} ({len(runs)} runs, {sum(len(r['_stories']) for r in runs)} stories)")


# ---- live server ----
class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        b = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def log_message(self, *a):
        pass

    def do_GET(self):
        u = urlparse(self.path); q = parse_qs(u.query)
        run = q.get("run", [""])[0]
        rundir = os.path.join(PIPE, os.path.basename(run)) if run else None
        if u.path == "/":
            return self._send(200, render("serve"))
        if u.path == "/srs" and rundir and os.path.isdir(rundir):
            f = next((x for x in os.listdir(rundir) if x.endswith("-SRS.html")), None)
            if f:
                return self._send(200, open(os.path.join(rundir, f), encoding="utf-8").read())
        if u.path == "/stories" and rundir and os.path.isdir(os.path.join(rundir, "stories")):
            sd = os.path.join(rundir, "stories")
            files = sorted(x for x in os.listdir(sd) if x.endswith(".md") and x != "backlog.md")
            links = "".join(
                f'<li><a href="/story?run={quote(run)}&id={quote(x[:-3])}">{esc(x)}</a></li>' for x in files)
            return self._send(200, f"<!doctype html><meta charset=utf-8><style>{CSS}</style>"
                              f"<div class='wrap'><a href='/'>← dashboard</a><h1>{esc(run)} — stories</h1>"
                              f"<ul>{links}</ul></div>")
        if u.path == "/story" and rundir:
            p = os.path.join(rundir, "stories", os.path.basename(q.get("id", [""])[0]) + ".md")
            if os.path.isfile(p):
                return self._send(200, md_to_page(run, q.get("id", [""])[0], open(p, encoding="utf-8").read()))
        return self._send(404, "<p>not found — <a href='/'>dashboard</a></p>")


def serve(port):
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Dashboard live -> http://localhost:{port}  (Ctrl+C to stop; rebuilds each load)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


def main():
    if "--serve" in sys.argv:
        i = sys.argv.index("--serve")
        port = int(sys.argv[i + 1]) if len(sys.argv) > i + 1 and sys.argv[i + 1].isdigit() else 8770
        serve(port)
    else:
        build_static()


if __name__ == "__main__":
    main()
