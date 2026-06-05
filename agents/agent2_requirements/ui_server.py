#!/usr/bin/env python3
"""ui_server.py - Local + hostable web UI to launch the Video2Spec workflow.

Run locally:
    python scripts/ui_server.py            # http://localhost:8765

Run hosted (Docker / cloud): the entrypoint sets HOST=0.0.0.0 and PORT from the
platform. Optionally set VIDEO2SPEC_TOKEN to require a shared access token.

What it does:
  * Serves a single-page UI. The user either UPLOADS a video (hosted mode) or pastes
    a server-side file PATH (local mode), picks a Whisper model, and clicks Run.
  * Runs Stages 1-4 (scripts/pipeline.py - cross-platform) as a background job and
    streams the live log to the browser.
  * On completion shows the generated contact sheets and a ready-to-paste hand-off
    prompt for Stages 5-6 (the screenshot-reading + SRS authoring Claude Code does).

Standard library only (incl. a minimal multipart parser, since `cgi` was removed in
Python 3.13).
"""
import json
import os
import re
import subprocess
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPELINE = os.path.join(ROOT, "scripts", "pipeline.py")
AGENT = os.path.join(ROOT, "scripts", "agent_srs.py")
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(ROOT, "out"))
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8765"))
TOKEN = os.environ.get("VIDEO2SPEC_TOKEN", "")
MAX_UPLOAD = int(os.environ.get("MAX_UPLOAD_MB", "512")) * 1024 * 1024
import sys
PYEXE = sys.executable or "python"

JOBS = {}
LOCK = threading.Lock()


def slugify(name):
    base = os.path.splitext(os.path.basename(name))[0].lower()
    return re.sub(r"[^a-z0-9]+", "-", base).strip("-") or "video"


def parse_multipart(body, boundary):
    """Minimal multipart/form-data parser -> (fields{name:str}, files{name:(filename,bytes)})."""
    fields, files = {}, {}
    delim = b"--" + boundary
    for part in body.split(delim):
        part = part.strip(b"\r\n")
        if not part or part == b"--":
            continue
        if b"\r\n\r\n" not in part:
            continue
        head, data = part.split(b"\r\n\r\n", 1)
        head_txt = head.decode("utf-8", "replace")
        m = re.search(r'name="([^"]*)"', head_txt)
        if not m:
            continue
        name = m.group(1)
        fm = re.search(r'filename="([^"]*)"', head_txt)
        if fm:
            files[name] = (fm.group(1), data)
        else:
            fields[name] = data.decode("utf-8", "replace").strip()
    return fields, files


def _stream(cmd, job, env=None):
    with LOCK:
        job["lines"].append("$ " + " ".join(cmd))
    proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, bufsize=1,
                            encoding="utf-8", errors="replace", env=env)
    for line in proc.stdout:
        with LOCK:
            job["lines"].append(line.rstrip("\n"))
    proc.wait()
    return proc.returncode


def run_job(job_id, video, out, slug, model):
    job = JOBS[job_id]
    try:
        # Stages 1-4
        job["rc"] = _stream([PYEXE, PIPELINE, video, out, slug, model], job)

        # Stages 5-6 (autonomous authoring) when enabled + a key is available
        api_key = job.get("api_key") or os.environ.get("ANTHROPIC_API_KEY", "")
        if job["rc"] == 0 and job.get("auto") and api_key:
            env = dict(os.environ, ANTHROPIC_API_KEY=api_key)
            if job.get("agent_model"):
                env["AGENT_MODEL"] = job["agent_model"]
            with LOCK:
                job["lines"].append("")
                job["lines"].append("=== Autonomous authoring (Claude API) ===")
            rc2 = _stream([PYEXE, AGENT, video, out, slug, env.get("AGENT_MODEL", "claude-opus-4-8")],
                          job, env=env)
            srs = os.path.join(out, f"{slug}-SRS.html")
            if rc2 == 0 and os.path.isfile(srs):
                job["srs"] = srs
            else:
                with LOCK:
                    job["lines"].append(f"[authoring exited {rc2}]")
        elif job["rc"] == 0 and job.get("auto") and not api_key:
            with LOCK:
                job["lines"].append("[auto-author requested but no ANTHROPIC_API_KEY available]")
    except Exception as exc:  # noqa: BLE001
        with LOCK:
            job["lines"].append(f"[runner error] {exc}")
        job["rc"] = -1
    finally:
        job["done"] = True


def find_contacts(out):
    try:
        return sorted(f for f in os.listdir(out)
                      if f.startswith("contact_") and f.endswith(".jpg"))
    except OSError:
        return []


def handoff_prompt(video, out, slug):
    return (
        f"Process the video at {video} into an SRS following the Video2Spec workflow "
        f"(CLAUDE.md). Stages 1-4 are already done; their outputs are in {out} "
        f"(slug '{slug}'): audio, frames, contact sheets (contact_*.jpg), and "
        f"{slug}.transcript_raw.txt.\n\n"
        f"Now do Stages 5-6:\n"
        f"1. View every contact_*.jpg in {out} to understand the video's structure.\n"
        f"2. For each important screen, grab an HD frame, view it, and read every "
        f"label/field/button into notes.\n"
        f"3. Optimize keepers into {out}/shots/NN-<name>.jpg.\n"
        f"4. Clean {slug}.transcript_raw.txt against the on-screen content (keep the fidelity note).\n"
        f"5. Author spec.json and render with scripts/build_srs.py (see prompts/srs-authoring.md)."
    )


PAGE = """<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Video2Spec - Run Workflow</title>
<style>
 :root{--accent:#2563eb;--bg:#f6f7f9;--card:#fff;--bd:#e3e6ea;--ink:#1f2430;--mut:#6b7280}
 *{box-sizing:border-box}
 body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:var(--bg);color:var(--ink)}
 .wrap{max-width:900px;margin:0 auto;padding:28px 20px 60px}
 h1{font-size:22px;margin:0 0 2px} .sub{color:var(--mut);margin:0 0 22px;font-size:14px}
 .badge{display:inline-block;background:var(--accent);color:#fff;font-size:11px;font-weight:600;
   padding:3px 9px;border-radius:20px;letter-spacing:.04em;margin-bottom:10px}
 .card{background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:20px;margin-bottom:18px}
 label{display:block;font-weight:600;font-size:13px;margin:12px 0 5px}
 input,select{width:100%;padding:10px 12px;border:1px solid var(--bd);border-radius:8px;font-size:14px;font-family:inherit;background:#fff}
 .row{display:flex;gap:14px}.row>div{flex:1}
 .hint{color:var(--mut);font-size:12px;margin-top:4px}
 .tabs{display:flex;gap:8px;margin-bottom:6px}
 .tab{padding:7px 14px;border:1px solid var(--bd);border-radius:8px;cursor:pointer;font-size:13px;font-weight:600;background:#fff}
 .tab.on{background:var(--accent);color:#fff;border-color:var(--accent)}
 button{margin-top:18px;background:var(--accent);color:#fff;border:0;border-radius:8px;
   padding:12px 22px;font-size:15px;font-weight:600;cursor:pointer}
 button:disabled{opacity:.5;cursor:not-allowed}
 pre{background:#0d1117;color:#d1d5db;border-radius:10px;padding:14px;overflow:auto;max-height:340px;
   font:12.5px/1.5 ui-monospace,Consolas,monospace;white-space:pre-wrap}
 .ok{color:#16a34a}.err{color:#dc2626}
 .shots{display:flex;flex-wrap:wrap;gap:10px;margin-top:10px}
 .shots img{width:260px;border:1px solid var(--bd);border-radius:8px}
 .handoff{background:#eef4ff;border:1px solid #c7dbff;border-radius:10px;padding:14px;font-size:13px}
 .handoff pre{background:#fff;color:var(--ink);border:1px solid var(--bd);max-height:none}
 .copy{margin:8px 0 0;background:#fff;color:var(--accent);border:1px solid var(--accent);padding:7px 14px;font-size:13px}
 .hidden{display:none}
</style></head><body><div class=wrap>
 <span class=badge>VIDEO2SPEC</span>
 <h1>Run the Video2Spec workflow</h1>
 <p class=sub>Upload a screen-recording (or paste a server path), pick a model, and launch Stages 1-4. Then hand off to the Claude Code agent for the SRS.</p>

 <div class=card>
  <div class=tabs>
   <div class="tab on" id=tabUpload onclick="mode('upload')">Upload a file</div>
   <div class=tab id=tabPath onclick="mode('path')">Server path</div>
  </div>
  <div id=paneUpload>
   <label>Video file</label>
   <input id=file type=file accept="video/*">
   <div class=hint>.mp4 / .mov / .mkv / .webm. Uploaded to the server for processing.</div>
  </div>
  <div id=panePath class=hidden>
   <label>Video file path (on the server)</label>
   <input id=video placeholder="C:\\path\\to\\demo.mp4" autocomplete=off>
   <div class=hint>Absolute path to a file already on the machine running this server.</div>
  </div>
  <div class=row>
   <div><label>Slug</label><input id=slug placeholder="auto from filename"></div>
   <div><label>Whisper model</label><select id=model>
     <option value=tiny>tiny - fastest, rough</option>
     <option value=base>base - fast</option>
     <option value=small selected>small - recommended (accurate)</option>
     <option value=medium>medium - slow, most accurate</option>
   </select></div>
  </div>
  <div style="margin-top:14px;padding:12px;border:1px solid var(--bd);border-radius:8px;background:#fafbfc">
   <label style="margin:0"><input type=checkbox id=auto style="width:auto;margin-right:8px" onchange="document.getElementById('keyrow').style.display=this.checked?'block':'none'">Auto-author the full SRS with Claude (Stages 5-6)</label>
   <div class=hint>Uses the Anthropic API (pay-per-use, ~$0.10-0.40/run). Produces the finished SRS HTML automatically - no hand-off needed.</div>
   <div id=keyrow class=hidden>
    <label>Anthropic API key <span class=hint style="font-weight:400">(leave blank to use the server's ANTHROPIC_API_KEY)</span></label>
    <input id=apikey type=password placeholder="sk-ant-..." autocomplete=off>
    <label>Authoring model</label>
    <select id=amodel>
      <option value="claude-opus-4-8" selected>Opus 4.8 - most capable (default)</option>
      <option value="claude-sonnet-4-6">Sonnet 4.6 - cheaper / faster</option>
    </select>
   </div>
  </div>
  <button id=go onclick=run()>Run</button>
 </div>

 <div id=result class="card hidden">
  <div id=state></div>
  <pre id=log></pre>
  <div id=shotsWrap class=hidden><label>Contact sheets (agent reviews these)</label><div id=shots class=shots></div></div>
  <div id=srsWrap class="handoff hidden">
   <b>Your SRS is ready.</b>
   <div class=hint>Authored autonomously by Claude from the screenshots + transcript.</div>
   <p><a id=srsLink target=_blank><button class=copy>Open the finished SRS</button></a></p>
  </div>
  <div id=handoffWrap class="handoff hidden">
   <b>Hand off to the Claude Code agent for Stages 5-6.</b>
   <div class=hint>Open the project in Claude Code and paste the prompt below (or run the <code>/video2spec</code> skill).</div>
   <pre id=handoff></pre>
   <button class=copy onclick=copyHandoff()>Copy prompt</button>
  </div>
 </div>
</div>
<script>
let job=null, off=0, timer=null, curMode='upload';
const $=id=>document.getElementById(id);
const TOKEN=new URLSearchParams(location.search).get('token')||'';
function mode(m){curMode=m;
  $('tabUpload').classList.toggle('on',m=='upload');$('tabPath').classList.toggle('on',m=='path');
  $('paneUpload').classList.toggle('hidden',m!='upload');$('panePath').classList.toggle('hidden',m!='path');}
function startPoll(){timer=setInterval(poll,1000);poll();}
function begin(){$('go').disabled=true;$('result').classList.remove('hidden');
  $('log').textContent='';$('state').textContent='Starting...';off=0;
  $('shotsWrap').classList.add('hidden');$('handoffWrap').classList.add('hidden');}
function fail(msg){$('state').innerHTML='<span class=err>'+msg+'</span>';$('go').disabled=false;}
function qs(){return TOKEN?('?token='+encodeURIComponent(TOKEN)):'';}
function run(){
  const slug=$('slug').value.trim(), model=$('model').value;
  const auto=$('auto').checked, api_key=$('apikey').value.trim(), agent_model=$('amodel').value;
  if(curMode=='path'){
    const video=$('video').value.trim(); if(!video){alert('Enter a server path');return;}
    begin();
    fetch('/run'+qs(),{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({video,slug,model,auto,api_key,agent_model})}).then(r=>r.json()).then(d=>{
        if(d.error){fail(d.error);return;} job=d.job_id;startPoll();});
  } else {
    const f=$('file').files[0]; if(!f){alert('Choose a video file');return;}
    begin(); $('state').textContent='Uploading '+f.name+' ...';
    const fd=new FormData(); fd.append('slug',slug); fd.append('model',model); fd.append('file',f);
    fd.append('auto',auto?'1':'0'); fd.append('api_key',api_key); fd.append('agent_model',agent_model);
    fetch('/run'+qs(),{method:'POST',body:fd}).then(r=>r.json()).then(d=>{
      if(d.error){fail(d.error);return;} job=d.job_id;startPoll();}).catch(e=>fail(''+e));
  }
}
function poll(){
  fetch('/log?job='+job+'&off='+off+(TOKEN?('&token='+encodeURIComponent(TOKEN)):'')).then(r=>r.json()).then(d=>{
    if(d.lines&&d.lines.length){$('log').textContent+=d.lines.join('\\n')+'\\n';off+=d.lines.length;
      $('log').scrollTop=$('log').scrollHeight;}
    if(d.done){clearInterval(timer);$('go').disabled=false;
      $('state').innerHTML=d.rc===0?'<span class=ok>Stages 1-4 complete.</span>':'<span class=err>Exited with code '+d.rc+'.</span>';
      if(d.contacts&&d.contacts.length){$('shotsWrap').classList.remove('hidden');
        $('shots').innerHTML=d.contacts.map(c=>'<img src="/img?path='+encodeURIComponent(c)+qs().replace("?","&")+'">').join('');}
      if(d.srs_ready){$('srsWrap').classList.remove('hidden');
        $('srsLink').href='/srs?job='+job+(TOKEN?('&token='+encodeURIComponent(TOKEN)):'');}
      if(d.handoff){$('handoffWrap').classList.remove('hidden');$('handoff').textContent=d.handoff;}}
  });
}
function copyHandoff(){navigator.clipboard.writeText($('handoff').textContent);}
</script></body></html>"""


def authorized(query):
    if not TOKEN:
        return True
    return query.get("token", [""])[0] == TOKEN


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass

    def _start(self, video, slug, model, opts=None):
        opts = opts or {}
        slug = slug or slugify(video)
        out = os.path.join(DATA_DIR, slug)
        job_id = uuid.uuid4().hex[:8]
        JOBS[job_id] = {"lines": [], "done": False, "rc": None, "srs": None,
                        "out": out, "slug": slug, "video": video, "model": model,
                        "auto": bool(opts.get("auto")),
                        "api_key": (opts.get("api_key") or "").strip(),
                        "agent_model": (opts.get("agent_model") or "").strip()}
        threading.Thread(target=run_job, args=(job_id, video, out, slug, model), daemon=True).start()
        return job_id

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path == "/":
            return self._send(200, PAGE, "text/html; charset=utf-8")
        if u.path == "/healthz":
            return self._send(200, json.dumps({"ok": True}))
        if not authorized(q):
            return self._send(401, json.dumps({"error": "unauthorized"}))
        if u.path == "/log":
            job = JOBS.get(q.get("job", [""])[0])
            if not job:
                return self._send(404, json.dumps({"error": "unknown job"}))
            off = int(q.get("off", ["0"])[0])
            with LOCK:
                new = job["lines"][off:]
            resp = {"lines": new, "done": job["done"], "rc": job["rc"]}
            if job["done"]:
                resp["contacts"] = [os.path.join(job["out"], c) for c in find_contacts(job["out"])]
                resp["handoff"] = handoff_prompt(job["video"], job["out"], job["slug"])
                resp["srs_ready"] = bool(job.get("srs"))
            return self._send(200, json.dumps(resp))
        if u.path == "/srs":
            job = JOBS.get(q.get("job", [""])[0])
            if job and job.get("srs") and os.path.isfile(job["srs"]):
                with open(job["srs"], "rb") as f:
                    return self._send(200, f.read(), "text/html; charset=utf-8")
            return self._send(404, json.dumps({"error": "no SRS"}))
        if u.path == "/img":
            path = q.get("path", [""])[0]
            ap = os.path.abspath(path)
            if ap.startswith(os.path.abspath(DATA_DIR)) and ap.lower().endswith(".jpg") and os.path.isfile(ap):
                with open(ap, "rb") as f:
                    return self._send(200, f.read(), "image/jpeg")
            return self._send(403, b"forbidden", "text/plain")
        return self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        u = urlparse(self.path)
        if u.path != "/run":
            return self._send(404, json.dumps({"error": "not found"}))
        if not authorized(parse_qs(u.query)):
            return self._send(401, json.dumps({"error": "unauthorized"}))
        ctype = self.headers.get("Content-Type", "")
        n = int(self.headers.get("Content-Length", 0))
        if n > MAX_UPLOAD:
            return self._send(200, json.dumps({"error": f"Upload exceeds {MAX_UPLOAD // (1024*1024)} MB limit"}))

        if ctype.startswith("multipart/form-data"):
            m = re.search(r"boundary=(.+)$", ctype)
            if not m:
                return self._send(400, json.dumps({"error": "no boundary"}))
            body = self.rfile.read(n)
            fields, files = parse_multipart(body, m.group(1).strip().strip('"').encode())
            if "file" not in files or not files["file"][1]:
                return self._send(200, json.dumps({"error": "No file uploaded"}))
            fname, fdata = files["file"]
            slug = fields.get("slug") or slugify(fname)
            model = fields.get("model") or "small"
            out = os.path.join(DATA_DIR, slug)
            os.makedirs(out, exist_ok=True)
            ext = os.path.splitext(fname)[1] or ".mp4"
            saved = os.path.join(out, f"source{ext}")
            with open(saved, "wb") as f:
                f.write(fdata)
            opts = {"auto": fields.get("auto") in ("1", "true", "on"),
                    "api_key": fields.get("api_key", ""),
                    "agent_model": fields.get("agent_model", "")}
            return self._send(200, json.dumps({"job_id": self._start(saved, slug, model, opts)}))

        # JSON path mode
        try:
            data = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return self._send(400, json.dumps({"error": "bad json"}))
        video = (data.get("video") or "").strip().strip('"')
        if not video or not os.path.isfile(video):
            return self._send(200, json.dumps({"error": f"Video not found: {video}"}))
        opts = {"auto": bool(data.get("auto")), "api_key": data.get("api_key", ""),
                "agent_model": data.get("agent_model", "")}
        return self._send(200, json.dumps(
            {"job_id": self._start(video, data.get("slug", ""), data.get("model") or "small", opts)}))


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    shown = "localhost" if HOST in ("127.0.0.1", "0.0.0.0") else HOST
    print(f"Video2Spec UI -> http://{shown}:{PORT}  (Ctrl+C to stop)"
          + ("  [token required]" if TOKEN else ""), flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
