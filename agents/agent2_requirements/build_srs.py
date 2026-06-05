#!/usr/bin/env python3
"""build_srs.py — render a self-contained HTML Software Requirements Specification.

Usage:
    build_srs.py <spec.json> <output.html>

The spec JSON drives everything. Screenshots referenced by `figure.image` are
read from disk and embedded as base64 so the HTML is fully portable (works
offline / over email with no external assets).

See prompts/srs-authoring.md and examples/example_spec.json for the schema.
The agent's job in Stage 6 is to assemble this JSON from what it read on screen;
this script just renders it in the house style.
"""
import base64
import json
import os
import sys

ACCENTS = {
    "blue": "#1d4ed8", "green": "#047857", "purple": "#7c3aed",
    "red": "#b91c1c", "teal": "#0891b2", "slate": "#0f172a",
}


def b64img(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def render_figure(fig, base_dir):
    path = fig["image"]
    if not os.path.isabs(path):
        path = os.path.join(base_dir, path)
    data = b64img(path)
    cap = esc(fig.get("caption", ""))
    return (f'<figure><img src="data:image/jpeg;base64,{data}" alt="{cap}"/>'
            f'<figcaption>{cap}</figcaption></figure>')


def render_table(tbl):
    head = "".join(f"<th>{esc(h)}</th>" for h in tbl["headers"])
    rows = ""
    for r in tbl["rows"]:
        rows += "<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>"
    return f"<table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table>"


def render_flow(steps):
    out = '<div class="flow">'
    for st in steps:
        out += f'<div class="s"><b>{esc(st["title"])}</b><span>{esc(st["detail"])}</span></div>'
    return out + "</div>"


def render_reqs(reqs):
    pri_class = {"MUST": "must", "SHOULD": "should", "COULD": "could"}
    out = ""
    for r in reqs:
        pc = pri_class.get(r["priority"], "could")
        out += (f'<div class="req"><span class="id">{esc(r["id"])}</span>'
                f'<span class="pri {pc}">{esc(r["priority"])}</span>'
                f'<p>{esc(r["text"])}</p></div>')
    return out


def render_callout(c):
    kind = c.get("kind", "info")
    return f'<div class="callout {kind}"><b>{esc(c.get("label",""))}</b> {esc(c.get("text",""))}</div>'


def render_pills(items):
    return "".join(f'<span class="pill">{esc(i)}</span>' for i in items)


def render_section(sec, base_dir):
    out = f'<h2 id="{esc(sec["id"])}"><span class="n">{esc(sec.get("number",""))}</span>{esc(sec["title"])}</h2>'
    for block in sec.get("blocks", []):
        t = block["type"]
        if t == "p":
            out += f"<p>{block['html']}</p>"
        elif t == "h3":
            out += f"<h3>{esc(block['text'])}</h3>"
        elif t == "h4":
            out += f"<h4>{esc(block['text'])}</h4>"
        elif t == "ul":
            out += "<ul>" + "".join(f"<li>{i}</li>" for i in block["items"]) + "</ul>"
        elif t == "figure":
            out += render_figure(block, base_dir)
        elif t == "table":
            out += render_table(block)
        elif t == "flow":
            out += render_flow(block["steps"])
        elif t == "reqs":
            out += render_reqs(block["items"])
        elif t == "callout":
            out += render_callout(block)
        elif t == "pills":
            out += "<p>" + render_pills(block["items"]) + "</p>"
    return out


def render_transcript(segs, engine="PocketSphinx"):
    out = (f'<p class="fnote">Auto-transcribed ({esc(engine)}) and cleaned against '
           'on-screen content. Timestamps approximate; operational paraphrase, not '
           'verbatim.</p><div class="transcript">')
    for s in segs:
        out += (f'<div class="seg"><span class="ts">[{esc(s["ts"])}]</span>'
                f'{esc(s["text"])}</div>')
    return out + "</div>"


CSS = """
:root{{--ink:#0f172a;--mut:#64748b;--line:#e2e8f0;--bg:#f8fafc;--acc:{acc};--acc2:#1d4ed8;}}
*{{box-sizing:border-box}}body{{font-family:'Segoe UI',-apple-system,system-ui,sans-serif;color:var(--ink);background:var(--bg);margin:0;line-height:1.6}}
.wrap{{max-width:1000px;margin:0 auto;padding:0 24px 80px}}
header{{background:linear-gradient(135deg,#0f172a,{acc});color:#fff;padding:48px 24px}}
header .inner{{max-width:1000px;margin:0 auto}}
header .badge{{display:inline-block;background:{acc};padding:4px 12px;border-radius:6px;font-size:12px;font-weight:700;letter-spacing:.5px;margin-bottom:14px;mix-blend-mode:screen}}
header h1{{font-size:30px;margin:0 0 8px;font-weight:800;line-height:1.2}}
header .sub{{color:#cbd5e1;font-size:15px;max-width:780px}}
header .meta{{margin-top:18px;display:flex;gap:18px;flex-wrap:wrap;font-size:12px;color:#94a3b8}}
header .meta b{{color:#e2e8f0;font-weight:600}}
nav.toc{{background:#fff;border:1px solid var(--line);border-radius:12px;padding:20px 24px;margin:28px 0;columns:2;column-gap:32px}}
nav.toc a{{display:block;color:var(--acc2);text-decoration:none;font-size:13px;padding:3px 0;break-inside:avoid}}
nav.toc a:hover{{text-decoration:underline}}
h2{{font-size:23px;margin:48px 0 8px;padding-top:16px;border-top:3px solid var(--acc);font-weight:800}}
h2 .n{{color:var(--acc);font-size:15px;display:block;margin-bottom:2px;font-weight:700}}
h3{{font-size:17px;margin:28px 0 8px;color:var(--acc);font-weight:700}}
h4{{font-size:14px;margin:18px 0 6px;color:var(--mut);text-transform:uppercase;letter-spacing:.5px}}
p{{margin:8px 0}}
figure{{margin:18px 0;border:1px solid var(--line);border-radius:10px;overflow:hidden;background:#fff;box-shadow:0 2px 12px rgba(0,0,0,.06)}}
figure img{{width:100%;display:block}}
figcaption{{padding:8px 14px;font-size:12px;color:var(--mut);background:#f1f5f9;border-top:1px solid var(--line);font-weight:600}}
table{{width:100%;border-collapse:collapse;margin:14px 0;font-size:13px}}
th{{background:#0f172a;color:#fff;text-align:left;padding:8px 10px;font-weight:600}}
td{{border:1px solid var(--line);padding:7px 10px;vertical-align:top}}
tr:nth-child(even) td{{background:#f8fafc}}
.req{{background:#fff;border:1px solid var(--line);border-left:4px solid var(--acc);border-radius:8px;padding:12px 16px;margin:10px 0}}
.req .id{{font-family:monospace;font-size:11px;font-weight:700;color:var(--acc);background:#f1f5f9;padding:2px 7px;border-radius:4px}}
.req .pri{{font-size:10px;font-weight:800;padding:2px 7px;border-radius:10px;margin-left:6px}}
.must{{background:#fee2e2;color:#991b1b}}.should{{background:#fef3c7;color:#92400e}}.could{{background:#f1f5f9;color:#475569}}
.req p{{margin:6px 0 0;font-size:13px}}
ul{{margin:8px 0;padding-left:22px}}li{{margin:4px 0;font-size:14px}}
.callout{{border-radius:8px;padding:14px 18px;margin:16px 0;font-size:13px;border:1px solid}}
.callout.info{{background:#eff6ff;border-color:#bfdbfe}}
.callout.warn{{background:#fffbeb;border-color:#fde68a}}
.callout.ok{{background:#f0fdf4;border-color:#bbf7d0}}
.pill{{display:inline-block;background:#e2e8f0;color:#475569;font-size:11px;font-weight:700;padding:2px 8px;border-radius:10px;margin:2px}}
.flow{{counter-reset:step;margin:14px 0}}
.flow .s{{position:relative;padding:8px 0 8px 42px;border-left:2px solid var(--line);margin-left:14px}}
.flow .s:before{{counter-increment:step;content:counter(step);position:absolute;left:-14px;top:6px;width:28px;height:28px;background:var(--acc);color:#fff;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:13px}}
.flow .s b{{display:block;font-size:14px}}.flow .s span{{font-size:13px;color:var(--mut)}}
.transcript{{background:#fff;border:1px solid var(--line);border-radius:10px;padding:8px 0;margin:14px 0}}
.transcript .seg{{padding:10px 18px;border-bottom:1px solid #f1f5f9;font-size:13px}}
.transcript .seg:last-child{{border-bottom:none}}
.transcript .ts{{font-family:monospace;font-size:11px;color:var(--acc);font-weight:700;margin-right:8px}}
.fnote{{font-size:12px;color:var(--mut);font-style:italic;margin-top:6px}}
.xref{{background:#0f172a;color:#fff;border-radius:10px;padding:14px 18px;margin:16px 0;font-size:13px}}
footer{{text-align:center;color:var(--mut);font-size:12px;padding:40px 0 0;border-top:1px solid var(--line);margin-top:50px}}
@media(max-width:700px){{nav.toc{{columns:1}}header h1{{font-size:23px}}}}
"""


def build(spec, base_dir):
    acc = ACCENTS.get(spec.get("accent", "slate"), ACCENTS["slate"])
    css = CSS.format(acc=acc)

    meta = spec.get("meta", {})
    meta_html = "".join(
        f"<span><b>{esc(k)}:</b> {esc(v)}</span>" for k, v in meta.items()
    )

    toc = '<nav class="toc">'
    for sec in spec["sections"]:
        toc += f'<a href="#{esc(sec["id"])}">{esc(sec["title"])}</a>'
    if spec.get("transcript"):
        toc += '<a href="#transcript">Full Transcript</a>'
    toc += "</nav>"

    xref = f'<div class="xref">{spec["xref"]}</div>' if spec.get("xref") else ""

    body = "".join(render_section(s, base_dir) for s in spec["sections"])

    transcript = ""
    if spec.get("transcript"):
        transcript = ('<h2 id="transcript"><span class="n">TRANSCRIPT</span>'
                      'Full Narration Transcript</h2>'
                      + render_transcript(spec["transcript"], spec.get("asr_engine", "PocketSphinx")))

    footer = f'<footer>{esc(spec.get("footer",""))}</footer>'

    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(spec["title"])}</title><style>{css}</style></head><body>
<header><div class="inner">
<div class="badge">{esc(spec.get("badge",""))}</div>
<h1>{esc(spec["title"])}</h1>
<div class="sub">{esc(spec.get("subtitle",""))}</div>
<div class="meta">{meta_html}</div>
</div></header>
<div class="wrap">{xref}{toc}{body}{transcript}{footer}</div></body></html>"""


def main():
    if len(sys.argv) != 3:
        print("usage: build_srs.py <spec.json> <output.html>", file=sys.stderr)
        return 2
    spec_path, out_path = sys.argv[1], sys.argv[2]
    with open(spec_path, encoding="utf-8") as f:
        spec = json.load(f)
    base_dir = os.path.dirname(os.path.abspath(spec_path))
    html = build(spec, base_dir)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Wrote {out_path} ({len(html):,} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
