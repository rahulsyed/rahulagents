#!/usr/bin/env python3
"""pipeline.py - orchestrator for the 5-agent video->backend pipeline.

State machine over a per-project pipeline/<name>/state.json. Stages 1-3 are
automated and stop at an approval gate; stages 4-5 run only on approved stories.

Usage:
    python orchestrator/pipeline.py new <url-or-path> [--name NAME] [--model small]
    python orchestrator/pipeline.py status [NAME]
    python orchestrator/pipeline.py approve <NAME> <STORY-ID...|all>
    python orchestrator/pipeline.py build <NAME>          # manual Agent 4->5 run
    python orchestrator/pipeline.py night                 # scheduled entry point

Stages 4-5 are gated on agents/agent4_contract.md being filled in from your Rack
security library (see ARCHITECTURE.md). Until then `build` prints what it WOULD do.
"""
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENTS = os.path.join(ROOT, "agents")
PIPE = os.path.join(ROOT, "pipeline")
PY = sys.executable or "python"


def log(m):
    print(m, flush=True)


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", os.path.splitext(os.path.basename(s))[0].lower()).strip("-") or "project"


def proj_dir(name):
    return os.path.join(PIPE, name)


def load_state(name):
    p = os.path.join(proj_dir(name), "state.json")
    return json.load(open(p, encoding="utf-8")) if os.path.isfile(p) else None


def save_state(name, st):
    d = proj_dir(name)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "state.json"), "w", encoding="utf-8") as f:
        json.dump(st, f, indent=2, ensure_ascii=False)


def run(cmd, **kw):
    log("$ " + " ".join(cmd))
    return subprocess.run(cmd, check=True, **kw)


def cmd_new(source, name, model):
    name = name or slugify(source)
    d = proj_dir(name)
    os.makedirs(os.path.join(d, "inbox"), exist_ok=True)
    st = load_state(name) or {"name": name, "source": source, "stage": "created",
                              "stories": [], "approved": [], "built": [], "runs": []}
    save_state(name, st)
    log(f"== Project '{name}' ==")

    # Agent 1 - download (or accept a local file)
    if os.path.isfile(source):
        video = source
        log(f"[Agent 1] using local file: {video}")
    else:
        log("[Agent 1] download")
        out = run([PY, os.path.join(AGENTS, "agent1_download.py"), source, os.path.join(d, "inbox")],
                  capture_output=True, text=True).stdout.strip()
        video = out.splitlines()[-1] if out else ""
    st["video"] = video; st["stage"] = "downloaded"; save_state(name, st)

    # Agent 2 - requirements (vendored video2spec): Stages 1-4 + autonomous authoring if key present
    log("[Agent 2] requirements + screenshots")
    a2 = os.path.join(AGENTS, "agent2_requirements")
    run([PY, os.path.join(a2, "pipeline.py"), video, d, name, model])
    if os.environ.get("ANTHROPIC_API_KEY"):
        run([PY, os.path.join(a2, "agent_srs.py"), video, d, name])
        st["srs"] = os.path.join(d, f"{name}-SRS.html")
    else:
        log("    (no ANTHROPIC_API_KEY: Stages 1-4 done; author the SRS in Claude Code)")
    st["stage"] = "requirements_done"; save_state(name, st)

    # Agent 3 - user stories
    log("[Agent 3] project + user stories")
    if os.environ.get("ANTHROPIC_API_KEY") and st.get("srs"):
        run([PY, os.path.join(AGENTS, "agent3_stories.py"), st["srs"], os.path.join(d, "stories")])
        backlog = os.path.join(d, "stories", "backlog.json")
        if os.path.isfile(backlog):
            st["stories"] = [s["id"] for s in json.load(open(backlog, encoding="utf-8"))["stories"]]
    st["stage"] = "AWAITING_APPROVAL"; save_state(name, st)

    log("")
    log(f"== Stopped at APPROVAL GATE. Review pipeline/{name}/stories/ ==")
    log(f"   Approve with:  pipeline approve {name} <STORY-ID...|all>")


def cmd_status(name=None):
    if not os.path.isdir(PIPE):
        return log("no projects yet.")
    names = [name] if name else sorted(os.listdir(PIPE))
    for n in names:
        st = load_state(n)
        if not st:
            continue
        log(f"== {n} == stage={st['stage']}")
        log(f"   stories={len(st['stories'])} approved={len(st['approved'])} built={len(st['built'])}")


def cmd_approve(name, ids):
    st = load_state(name)
    if not st:
        return log(f"unknown project: {name}")
    ids = st["stories"] if ids == ["all"] else ids
    st["approved"] = sorted(set(st["approved"]) | set(i for i in ids if i in st["stories"]))
    if st["stage"] == "AWAITING_APPROVAL":
        st["stage"] = "approved"
    save_state(name, st)
    log(f"approved {len(st['approved'])} stories for '{name}': {', '.join(st['approved'])}")
    log(f"build now with:  pipeline build {name}   (or wait for the nightly run)")


def cmd_build(name):
    st = load_state(name)
    if not st:
        return log(f"unknown project: {name}")
    todo = [s for s in st["approved"] if s not in st["built"]]
    if not todo:
        return log(f"[{name}] nothing to build (no approved-unbuilt stories).")
    contract = os.path.join(AGENTS, "agent4_contract.md")
    filled = os.path.isfile(contract) and "PENDING:" not in open(contract, encoding="utf-8").read()
    if not filled:
        log(f"[{name}] Agent 4 is NOT YET ACTIVATED.")
        log("   agents/agent4_contract.md must be filled from your Rack security library first.")
        log(f"   Would build these stories on feature branches: {', '.join(todo)}")
        return
    # Activated path is intentionally left to the Claude Code agent driving this repo,
    # following agent4_contract.md + agent5_review.md. The orchestrator records intent:
    log(f"[{name}] Agent 4/5 should now implement+review: {', '.join(todo)}")
    log("   (driven by Claude Code per agent4_contract.md; PRs opened per story.)")


def cmd_night():
    if not os.path.isdir(PIPE):
        return log("[night] no projects.")
    for n in sorted(os.listdir(PIPE)):
        st = load_state(n)
        if st and [s for s in st.get("approved", []) if s not in st.get("built", [])]:
            log(f"[night] {n}: has approved work")
            cmd_build(n)


def main():
    a = sys.argv[1:]
    if not a:
        log(__doc__); return 2
    c = a[0]
    if c == "new":
        src = a[1]
        name = None; model = "small"
        if "--name" in a:
            name = a[a.index("--name") + 1]
        if "--model" in a:
            model = a[a.index("--model") + 1]
        cmd_new(src, name, model)
    elif c == "status":
        cmd_status(a[1] if len(a) > 1 else None)
    elif c == "approve":
        cmd_approve(a[1], a[2:])
    elif c == "build":
        cmd_build(a[1])
    elif c == "night":
        cmd_night()
    else:
        log(f"unknown command: {c}"); return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
