#!/usr/bin/env python3
"""agent_srs.py - Autonomous Stages 5-6 via the Claude API (vision + authoring).

Usage:
    python scripts/agent_srs.py <video> <out_dir> <slug> [model]

Runs the part a human/agent would otherwise do by hand, using the Anthropic API:
  1. PLAN  - sends the contact sheet(s) + transcript to Claude and asks which
             distinct screens matter and at what timestamps (vision).
  2. GRAB  - extracts an HD frame for each planned screen (ffmpeg) and optimizes
             it into out/<slug>/shots/NN-<name>.jpg (deterministic filenames).
  3. AUTHOR- sends every HD screenshot + the transcript back to Claude and asks it
             to author the full SRS spec.json (matching scripts/build_srs.py's
             schema), referencing the exact shot filenames.
  4. RENDER- writes spec.json and renders the self-contained SRS HTML via build_srs.

Requires ANTHROPIC_API_KEY in the environment (pay-per-use, billed to your
Anthropic account). Default model is claude-opus-4-8; override with the 4th arg or
AGENT_MODEL. Prompt caching is used on the stable system prompt to cut cost across
the two calls and across runs.

Progress is printed line-by-line to stdout so ui_server.py can stream it.
"""
import base64
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MODEL = os.environ.get("AGENT_MODEL", "claude-opus-4-8")


def log(msg):
    print(msg, flush=True)


def _augment_windows_path():
    if os.name != "nt":
        return
    try:
        import winreg
        extra = []
        for root, sub in ((winreg.HKEY_CURRENT_USER, r"Environment"),
                          (winreg.HKEY_LOCAL_MACHINE,
                           r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment")):
            try:
                with winreg.OpenKey(root, sub) as k:
                    val, _ = winreg.QueryValueEx(k, "Path")
                    extra.append(os.path.expandvars(val))
            except OSError:
                pass
        if extra:
            os.environ["PATH"] = os.environ.get("PATH", "") + os.pathsep + os.pathsep.join(extra)
    except Exception:
        pass


_augment_windows_path()


def img_block(path):
    with open(path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode()
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}}


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40] or "screen"


def ffmpeg_grab(video, ts, dest):
    subprocess.run(["ffmpeg", "-ss", str(ts), "-i", video, "-frames:v", "1",
                    "-q:v", "2", dest, "-y", "-loglevel", "error"], check=True)


def magick_optimize(src, dest):
    tool = "magick" if shutil.which("magick") else "convert"
    subprocess.run([tool, src, "-resize", "1200x", "-quality", "82", dest], check=True)


SYSTEM = """You are an expert business analyst producing a Software Requirements \
Specification (SRS) from a product/tutorial screen recording, following the \
Video2Spec house method.

HARD RULES:
- Read the UI from the screenshots; the visible screen is the source of truth. The \
transcript is secondary support. Never invent fields, labels, tabs, or columns that \
are not visible in a screenshot you were given.
- Requirements are original analysis in your own words - never paste transcript \
verbatim. One requirement = one atomic, testable statement.
- ID format FR-<AREA>-NN (functional) and NFR-NN (non-functional); priority MUST / \
SHOULD / COULD. Keep requirement AREA codes consistent.

The SRS is rendered by build_srs.py from a JSON "spec". You must output that spec.

SPEC SCHEMA (output valid JSON, this exact shape):
{
  "title": str, "badge": str, "subtitle": str,
  "accent": one of "blue"|"green"|"purple"|"red"|"teal"|"slate",
  "meta": { "Source": str, "Duration": str, "Prepared for": str, "Version": str },
  "footer": str,
  "sections": [ { "id": str, "number": "SECTION N", "title": str, "blocks": [ ... ] } ],
  "transcript": [ { "ts": "m:ss", "text": str } ]
}
Each block is one of:
  {"type":"p","html": str}                      (inline <b> allowed)
  {"type":"h3","text":str} / {"type":"h4","text":str}
  {"type":"ul","items":[str,...]}
  {"type":"figure","image": "shots/NN-name.jpg","caption": str}
  {"type":"table","headers":[str,...],"rows":[[str,...],...]}
  {"type":"flow","steps":[{"title":str,"detail":str},...]}
  {"type":"reqs","items":[{"id":str,"priority":"MUST|SHOULD|COULD","text":str},...]}
  {"type":"callout","kind":"info|warn|ok","label":str,"text":str}
  {"type":"pills","items":[str,...]}

Recommended section order: Purpose & Scope; Actors & Roles (if any); one functional \
section per module (each with a figure of the relevant screenshot, prose, a \
fields/options table, a numbered flow, and reqs); Data Model (a table whose first \
header is "Entity"); Non-Functional Requirements. The transcript array should be a \
cleaned, timestamped paraphrase (~10-20 segments).

Reference screenshots ONLY by the exact filenames you are told are available."""


def call_plan(client, contacts, transcript):
    content = [{"type": "text", "text":
                "Here are contact sheet(s) (thumbnail grids of frames sampled across "
                "the video) and the rough transcript. Identify the 8-12 DISTINCT, "
                "important screens/modules worth capturing in HD for the SRS. For each, "
                "give a short kebab-case name, the approximate timestamp in SECONDS into "
                "the video where it is best shown, and one line on what it is."}]
    for c in contacts:
        content.append(img_block(c))
    content.append({"type": "text", "text": "TRANSCRIPT (rough):\n" + transcript[:6000]})

    schema = {
        "type": "object", "additionalProperties": False,
        "properties": {
            "shots": {
                "type": "array",
                "items": {
                    "type": "object", "additionalProperties": False,
                    "properties": {
                        "name": {"type": "string"},
                        "timestamp_seconds": {"type": "integer"},
                        "description": {"type": "string"},
                    },
                    "required": ["name", "timestamp_seconds", "description"],
                },
            }
        },
        "required": ["shots"],
    }
    resp = client.messages.create(
        model=MODEL, max_tokens=4000, thinking={"type": "adaptive"},
        system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": content}],
        output_config={"format": {"type": "json_schema", "schema": schema}},
    )
    text = next(b.text for b in resp.content if b.type == "text")
    return json.loads(text)["shots"]


def call_author(client, shots_meta, transcript, duration):
    content = [{"type": "text", "text":
                "Author the complete SRS spec.json now. The following HD screenshots are "
                "available (each labeled with its filename and what it shows). Read every "
                "one and write the SRS strictly from what is visible, supported by the "
                "transcript. Reference each screenshot by its exact filename in a figure "
                f"block. Video duration is {duration}. Output ONLY the JSON spec."}]
    for s in shots_meta:
        content.append({"type": "text", "text": f"FILE shots/{s['file']} - {s['description']}"})
        content.append(img_block(s["path"]))
    content.append({"type": "text", "text": "TRANSCRIPT (rough, clean it for the spec):\n" + transcript[:8000]})

    log("    authoring SRS spec (streaming)...")
    chunks = []
    with client.messages.stream(
        model=MODEL, max_tokens=32000, thinking={"type": "adaptive"},
        system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": content}],
    ) as stream:
        for text in stream.text_stream:
            chunks.append(text)
    raw = "".join(chunks).strip()
    # Strip code fences if present
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw).rstrip("`").rstrip()
    # Extract the outermost JSON object
    start, end = raw.find("{"), raw.rfind("}")
    return json.loads(raw[start:end + 1])


def main():
    if len(sys.argv) < 4:
        print("usage: agent_srs.py <video> <out_dir> <slug> [model]", file=sys.stderr)
        return 2
    video, out, slug = sys.argv[1], sys.argv[2], sys.argv[3]
    global MODEL
    if len(sys.argv) > 4:
        MODEL = sys.argv[4]
    if not os.environ.get("ANTHROPIC_API_KEY"):
        log("[agent] ANTHROPIC_API_KEY not set - cannot run autonomous authoring.")
        return 3

    try:
        import anthropic
    except ImportError:
        log("[agent] anthropic SDK not installed: pip install anthropic")
        return 1

    client = anthropic.Anthropic()
    shots_dir = os.path.join(out, "shots")
    hd_dir = os.path.join(out, "hd")
    os.makedirs(shots_dir, exist_ok=True)
    os.makedirs(hd_dir, exist_ok=True)

    transcript = ""
    tpath = os.path.join(out, f"{slug}.transcript_raw.txt")
    if os.path.isfile(tpath):
        transcript = open(tpath, encoding="utf-8").read()
    contacts = [os.path.join(out, f) for f in sorted(os.listdir(out))
                if f.startswith("contact_") and f.endswith(".jpg")]
    if not contacts:
        log("[agent] no contact sheets found - run Stages 1-4 first.")
        return 1

    # Duration via ffprobe (best-effort)
    duration = ""
    try:
        d = subprocess.check_output(["ffprobe", "-v", "quiet", "-show_entries",
                                     "format=duration", "-of", "csv=p=0", video], text=True).strip()
        s = int(float(d)); duration = f"{s // 60:02d}:{s % 60:02d}"
    except Exception:
        pass

    log(f"==> Stage 5: Planning screens with {MODEL} (vision)")
    shots = call_plan(client, contacts, transcript)
    log(f"    planned {len(shots)} screens")

    log("==> Stage 5: Capturing + optimizing HD frames")
    shots_meta = []
    for i, sh in enumerate(shots, 1):
        name = slugify(sh["name"])
        fname = f"{i:02d}-{name}.jpg"
        hd = os.path.join(hd_dir, f"{i:02d}-{name}.jpg")
        dest = os.path.join(shots_dir, fname)
        try:
            ffmpeg_grab(video, sh["timestamp_seconds"], hd)
            magick_optimize(hd, dest)
            shots_meta.append({"file": fname, "path": dest, "description": sh["description"]})
            log(f"    [{i}/{len(shots)}] {fname}  @ {sh['timestamp_seconds']}s")
        except Exception as exc:  # noqa: BLE001
            log(f"    [{i}] skipped ({exc})")

    if not shots_meta:
        log("[agent] no frames captured.")
        return 1

    log(f"==> Stage 6: Authoring SRS with {MODEL} (vision, reading {len(shots_meta)} screens)")
    spec = call_author(client, shots_meta, transcript, duration)
    spec.setdefault("asr_engine", "faster-whisper")

    spec_path = os.path.join(out, "spec.json")
    with open(spec_path, "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2, ensure_ascii=False)
    log(f"    wrote {spec_path}")

    out_html = os.path.join(out, f"{slug}-SRS.html")
    log("==> Stage 6: Rendering self-contained HTML")
    subprocess.run([sys.executable, os.path.join(HERE, "build_srs.py"), spec_path, out_html],
                   check=True)
    log("")
    log(f"==> SRS COMPLETE: {out_html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
