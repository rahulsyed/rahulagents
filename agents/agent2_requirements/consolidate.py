#!/usr/bin/env python3
"""consolidate.py — merge multiple per-volume SRS specs into one MASTER SRS.

Usage:
    consolidate.py <master_meta.json> <vol1_spec.json> <vol2_spec.json> ... <output.html>

What it produces (a single self-contained HTML):
  1. Volume index — every source volume with its surface + source.
  2. Consolidated requirements register — all FR/NFR across volumes, DEDUPED.
     Duplicates are detected by normalized requirement text; merged rows list
     every source volume + original IDs, and get a fresh master ID (MR-####).
  3. Unified data model — entities merged across volumes; attributes unioned;
     relationships collected. Same-named entities are combined.
  4. Cross-surface map — which volumes/surfaces each requirement AREA spans.
  5. Per-volume requirement appendix (traceability).

The master_meta.json controls title/branding and may add narrative sections.
See prompts/consolidation-authoring.md for the schema and conventions.

This reuses build_srs.py's CSS/renderers so the master matches the volume style.
"""
import json
import os
import re
import sys
import difflib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_srs as B  # reuse CSS + renderers


# ---------- normalization & dedup ----------

_STOP = re.compile(r"[^a-z0-9 ]+")
_WS = re.compile(r"\s+")


def norm(text):
    """Normalize a requirement statement for fuzzy duplicate detection."""
    t = text.lower()
    t = t.replace("the system shall", "").replace("must", "").replace("should", "")
    t = _STOP.sub(" ", t)
    t = _WS.sub(" ", t).strip()
    return t


def similar(a, b, threshold=0.86):
    return difflib.SequenceMatcher(None, a, b).ratio() >= threshold


def area_of(req_id):
    """FR-SCHED-02 -> SCHED ; NFR-03 -> NFR."""
    m = re.match(r"FR-([A-Z]+)-", req_id)
    if m:
        return m.group(1)
    if req_id.startswith("NFR"):
        return "NFR"
    return "MISC"


# ---------- extraction from volume specs ----------

def extract_requirements(spec, vol_label):
    """Pull every {id,priority,text} from a volume spec, tagged with its volume."""
    out = []
    for sec in spec.get("sections", []):
        sec_title = sec.get("title", "")
        for block in sec.get("blocks", []):
            if block.get("type") == "reqs":
                for r in block["items"]:
                    out.append({
                        "vol": vol_label,
                        "section": sec_title,
                        "id": r["id"],
                        "priority": r.get("priority", "COULD"),
                        "text": r["text"],
                        "norm": norm(r["text"]),
                        "area": area_of(r["id"]),
                    })
    return out


def extract_entities(spec):
    """Find data-model tables (headers starting with 'Entity') and parse rows."""
    entities = {}
    for sec in spec.get("sections", []):
        for block in sec.get("blocks", []):
            if block.get("type") == "table":
                heads = [h.lower() for h in block.get("headers", [])]
                if heads and heads[0].startswith("entity"):
                    for row in block["rows"]:
                        name = re.sub(r"<[^>]+>", "", str(row[0])).strip()
                        if not name:
                            continue
                        attrs = row[1] if len(row) > 1 else ""
                        rels = row[2] if len(row) > 2 else ""
                        e = entities.setdefault(name, {"attrs": set(), "rels": set()})
                        for a in re.split(r"[;,]", re.sub(r"<[^>]+>", "", str(attrs))):
                            a = a.strip()
                            if a:
                                e["attrs"].add(a)
                        for r in re.split(r"[;]", re.sub(r"<[^>]+>", "", str(rels))):
                            r = r.strip()
                            if r:
                                e["rels"].add(r)
    return entities


# ---------- dedup register ----------

PRI_RANK = {"MUST": 3, "SHOULD": 2, "COULD": 1}


def dedup_requirements(all_reqs):
    """Cluster near-duplicate requirements across volumes. Returns master rows."""
    clusters = []  # each: {norm, members:[req,...]}
    for req in all_reqs:
        placed = False
        for c in clusters:
            if similar(req["norm"], c["norm"]):
                c["members"].append(req)
                placed = True
                break
        if not placed:
            clusters.append({"norm": req["norm"], "members": [req]})

    master = []
    for i, c in enumerate(sorted(clusters, key=lambda c: c["members"][0]["area"]), 1):
        members = c["members"]
        # highest priority wins; longest text is usually the most complete
        top_pri = max(members, key=lambda m: PRI_RANK.get(m["priority"], 0))["priority"]
        best_text = max(members, key=lambda m: len(m["text"]))["text"]
        vols = sorted({m["vol"] for m in members})
        src_ids = ", ".join(f'{m["id"]} ({m["vol"]})' for m in members)
        master.append({
            "mid": f"MR-{i:04d}",
            "area": members[0]["area"],
            "priority": top_pri,
            "text": best_text,
            "vols": vols,
            "sources": src_ids,
            "dup": len(members) > 1,
        })
    return master


# ---------- HTML section builders ----------

def sec_volume_index(volumes):
    rows = [[v["label"], v["surface"], v.get("source", ""), str(v["req_count"])]
            for v in volumes]
    tbl = B.render_table({"headers": ["Volume", "Surface", "Source", "Reqs"], "rows": rows})
    return ('<h2 id="index"><span class="n">SECTION 1</span>Volume Index</h2>'
            '<p>Source volumes consolidated into this master specification.</p>' + tbl)


def sec_register(master):
    pri_class = {"MUST": "must", "SHOULD": "should", "COULD": "could"}
    rows = []
    for m in master:
        badge = f'<span class="pri {pri_class.get(m["priority"],"could")}">{m["priority"]}</span>'
        dupflag = ' <span class="pill">merged</span>' if m["dup"] else ""
        rows.append([m["mid"], m["area"], badge + dupflag, B.esc(m["text"]),
                     B.esc(m["sources"])])
    tbl = B.render_table({
        "headers": ["Master ID", "Area", "Priority", "Requirement", "Source(s)"],
        "rows": rows,
    })
    n_total = len(master)
    n_merged = sum(1 for m in master if m["dup"])
    note = (f'<p>{n_total} consolidated requirements ('
            f'{n_merged} merged from duplicates across volumes). '
            'Each master requirement traces back to its originating volume IDs.</p>')
    return ('<h2 id="register"><span class="n">SECTION 2</span>'
            'Consolidated Requirements Register</h2>' + note + tbl)


def sec_data_model(entities):
    rows = []
    for name in sorted(entities):
        e = entities[name]
        attrs = ", ".join(sorted(e["attrs"])) or "—"
        rels = "; ".join(sorted(e["rels"])) or "—"
        rows.append([f"<b>{B.esc(name)}</b>", B.esc(attrs), B.esc(rels)])
    tbl = B.render_table({
        "headers": ["Entity", "Attributes (unioned across volumes)", "Relationships"],
        "rows": rows,
    })
    return ('<h2 id="datamodel"><span class="n">SECTION 3</span>'
            'Unified Data Model</h2>'
            '<p>Entities merged across all volumes; attributes unioned, '
            'relationships collected. This is the single schema the clone builds against.</p>'
            + tbl)


def sec_cross_surface(master, volumes):
    """Area × Volume matrix: where each requirement area appears."""
    areas = sorted({m["area"] for m in master})
    vols = [v["label"] for v in volumes]
    header = ["Area"] + vols
    rows = []
    for a in areas:
        row = [a]
        present = {m_vol for m in master if m["area"] == a for m_vol in m["vols"]}
        for v in vols:
            row.append("●" if v in present else "")
        rows.append(row)
    tbl = B.render_table({"headers": header, "rows": rows})
    return ('<h2 id="crosssurface"><span class="n">SECTION 4</span>'
            'Cross-Surface Map</h2>'
            '<p>Which volumes each requirement area spans (● = covered). '
            'Areas spanning multiple volumes are the shared spine of the product.</p>'
            + tbl)


def sec_appendix(all_reqs, volumes):
    pri_class = {"MUST": "must", "SHOULD": "should", "COULD": "could"}
    out = ('<h2 id="appendix"><span class="n">SECTION 5</span>'
           'Per-Volume Requirement Appendix</h2>'
           '<p>Full traceability — every original requirement, grouped by volume.</p>')
    for v in volumes:
        out += f'<h3>{B.esc(v["label"])} — {B.esc(v["surface"])}</h3>'
        vol_reqs = [r for r in all_reqs if r["vol"] == v["label"]]
        for r in vol_reqs:
            pc = pri_class.get(r["priority"], "could")
            out += (f'<div class="req"><span class="id">{B.esc(r["id"])}</span>'
                    f'<span class="pri {pc}">{r["priority"]}</span>'
                    f'<p>{B.esc(r["text"])}</p></div>')
    return out


# ---------- main ----------

def main():
    args = sys.argv[1:]
    if len(args) < 3:
        print("usage: consolidate.py <master_meta.json> <vol1.json> [vol2.json ...] <output.html>",
              file=sys.stderr)
        return 2
    meta_path, out_path = args[0], args[-1]
    vol_paths = args[1:-1]

    meta = json.load(open(meta_path))
    meta_dir = os.path.dirname(os.path.abspath(meta_path))

    volumes, all_reqs, entities = [], [], {}
    vol_meta = {v["spec"]: v for v in meta.get("volumes", [])}

    for i, vp in enumerate(vol_paths, 1):
        spec = json.load(open(vp))
        key = os.path.basename(vp)
        vm = vol_meta.get(key, {})
        label = vm.get("label", f"Vol. {i}")
        surface = vm.get("surface", spec.get("title", key))
        source = vm.get("source", spec.get("meta", {}).get("Source", ""))
        reqs = extract_requirements(spec, label)
        all_reqs.extend(reqs)
        # merge entities
        for name, e in extract_entities(spec).items():
            tgt = entities.setdefault(name, {"attrs": set(), "rels": set()})
            tgt["attrs"] |= e["attrs"]
            tgt["rels"] |= e["rels"]
        volumes.append({"label": label, "surface": surface,
                        "source": source, "req_count": len(reqs)})

    master = dedup_requirements(all_reqs)

    # assemble body
    body = (sec_volume_index(volumes)
            + sec_register(master)
            + sec_data_model(entities)
            + sec_cross_surface(master, volumes)
            + sec_appendix(all_reqs, volumes))

    # optional extra narrative sections from meta (rendered via build_srs)
    extra = ""
    for sec in meta.get("extra_sections", []):
        extra += B.render_section(sec, meta_dir)

    acc = B.ACCENTS.get(meta.get("accent", "slate"), B.ACCENTS["slate"])
    css = B.CSS.format(acc=acc)
    meta_html = "".join(f"<span><b>{B.esc(k)}:</b> {B.esc(v)}</span>"
                        for k, v in meta.get("meta", {}).items())
    toc_links = [
        ("index", "1. Volume Index"), ("register", "2. Requirements Register"),
        ("datamodel", "3. Unified Data Model"), ("crosssurface", "4. Cross-Surface Map"),
        ("appendix", "5. Per-Volume Appendix"),
    ]
    toc = '<nav class="toc">' + "".join(
        f'<a href="#{i}">{t}</a>' for i, t in toc_links) + "</nav>"
    xref = f'<div class="xref">{meta["xref"]}</div>' if meta.get("xref") else ""

    stats = (f'{len(all_reqs)} source requirements → {len(master)} consolidated · '
             f'{len(entities)} entities · {len(volumes)} volumes')

    html = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{B.esc(meta["title"])}</title><style>{css}</style></head><body>
<header><div class="inner">
<div class="badge">{B.esc(meta.get("badge","MASTER SRS"))}</div>
<h1>{B.esc(meta["title"])}</h1>
<div class="sub">{B.esc(meta.get("subtitle",""))}</div>
<div class="meta">{meta_html}<span><b>Consolidated:</b> {stats}</span></div>
</div></header>
<div class="wrap">{xref}{toc}{body}{extra}
<footer>{B.esc(meta.get("footer",""))}</footer></div></body></html>"""

    open(out_path, "w").write(html)
    print(f"Wrote {out_path} ({len(html):,} chars)")
    print(f"  volumes={len(volumes)}  source_reqs={len(all_reqs)}  "
          f"consolidated={len(master)}  merged={sum(1 for m in master if m['dup'])}  "
          f"entities={len(entities)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
