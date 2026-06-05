#!/usr/bin/env python3
"""agent3_stories.py - SRS -> story-driven backlog in the Rack Library format.

Usage:
    python agents/agent3_stories.py <srs.html> <out_dir>

Reads the rendered SRS (Agent 2) and asks Claude to produce user stories in Rahul's
exact story-driven-development format (see _RackLibrary/workflows/story-driven-development.md
and py2026/.stories/STORY-001.md). Writes, into <out_dir> (a STAGING area, not the live
repo):
    STORY-NNN.md        one file per story, frontmatter + body, status: blocked
    backlog.json        machine-readable index (orchestrator reads ids/priorities)
    backlog.md          human review for the approval gate

Stories are written `status: blocked` = AWAITING APPROVAL. The orchestrator's `approve`
copies approved stories into the target project's .stories/ flipped to `status: pending`,
where the existing scheduler / Agent 4 builds them. Nothing unapproved is ever pending.

Requires ANTHROPIC_API_KEY. Default model claude-opus-4-8 (AGENT_MODEL to override).
"""
import json
import os
import re
import sys

MODEL = os.environ.get("AGENT_MODEL", "claude-opus-4-8")

SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "stories": {
            "type": "array",
            "items": {
                "type": "object", "additionalProperties": False,
                "properties": {
                    "id": {"type": "string"},            # STORY-001
                    "title": {"type": "string"},
                    "epic": {"type": "string"},
                    "priority": {"type": "string"},       # high|medium|low
                    "description": {"type": "string"},
                    "acceptance_criteria": {"type": "array", "items": {"type": "string"}},
                    "files_to_modify": {"type": "array", "items": {"type": "string"}},
                    "reference_files": {"type": "array", "items": {"type": "string"}},
                    "traces_to": {"type": "array", "items": {"type": "string"}},
                    "depends_on": {"type": "array", "items": {"type": "string"}},
                    "notes": {"type": "string"},
                },
                "required": ["id", "title", "epic", "priority", "description",
                             "acceptance_criteria", "files_to_modify", "reference_files",
                             "traces_to", "depends_on", "notes"],
            },
        }
    },
    "required": ["stories"],
}

SYSTEM = """You are a senior product owner for Axlr8's The Yard Platform (a Next.js +
Supabase + Stripe SaaS for pickleball/padel/golf-sim venues). From an SRS you produce
an implementation-ready backlog in the team's exact story-driven-development format.

Rules:
- One story = one shippable slice. Stable id STORY-NN, sequential.
- Every story traces to one or more FR-*/NFR-* ids from the SRS (traces_to).
- Acceptance criteria are concrete and testable.
- Sequence foundational/shared stories first; set depends_on accordingly.
- priority is high|medium|low (map MUST->high, SHOULD->medium, COULD->low).
- files_to_modify / reference_files use the canonical Next.js monorepo layout
  (apps/web/src/app/(protected)/..., apps/web/src/lib/<feature>/...,
  packages/db/migrations/...). Best-effort paths the implementer will confirm.
- Respect locked decisions: Supabase RLS scoped by tenant_id, modular bounded contexts
  (booking, programs, lessons, leagues, waivers, comms), tenant_settings white-label.
- Do not invent scope beyond the SRS."""


def srs_text(path):
    html = open(path, encoding="utf-8").read()
    html = re.sub(r"<script.*?</script>", " ", html, flags=re.S)
    html = re.sub(r"<style.*?</style>", " ", html, flags=re.S)
    html = re.sub(r"data:image/[^\"']+", "", html)
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text)[:60000]


def yaml_list(key, items, indent=0):
    pad = " " * indent
    if not items:
        return f"{pad}{key}: []\n"
    out = f"{pad}{key}:\n"
    for it in items:
        out += f'{pad}  - "{str(it).replace(chr(34), chr(39))}"\n'
    return out


def story_md(s, created):
    fm = "---\n"
    fm += f'id: {s["id"]}\n'
    fm += f'title: "{s["title"].replace(chr(34), chr(39))}"\n'
    fm += f'epic: "{s["epic"]}"\n'
    fm += "status: blocked        # AWAITING APPROVAL — approve to flip to pending\n"
    fm += f'priority: {s["priority"]}\n'
    fm += f"created: {created}\n"
    fm += "completed:\n"
    fm += "error: null\n"
    fm += yaml_list("files_to_modify", s["files_to_modify"])
    fm += yaml_list("reference_files", s["reference_files"])
    fm += yaml_list("acceptance_criteria", s["acceptance_criteria"])
    if s.get("traces_to"):
        fm += yaml_list("traces_to", s["traces_to"])
    if s.get("depends_on"):
        fm += yaml_list("depends_on", s["depends_on"])
    fm += "---\n\n"
    body = f"## Description\n\n{s['description']}\n\n## Acceptance Criteria\n\n"
    body += "".join(f"- [ ] {c}\n" for c in s["acceptance_criteria"])
    body += "\n## Files to Modify\n\n" + "".join(f"- `{f}`\n" for f in s["files_to_modify"])
    if s.get("reference_files"):
        body += "\n## Reference Files\n\n" + "".join(f"- `{f}`\n" for f in s["reference_files"])
    if s.get("notes"):
        body += f"\n## Notes / Edge Cases\n\n{s['notes']}\n"
    return fm + body


def backlog_md(stories):
    out = ["# Proposed backlog — review, then `pipeline approve <name> <ids|all>`\n",
           "All stories are `status: blocked` (awaiting approval). Approving copies them",
           "into the target project's `.stories/` as `status: pending` for the build loop.\n"]
    by_epic = {}
    for s in stories:
        by_epic.setdefault(s["epic"], []).append(s)
    for epic, items in by_epic.items():
        out.append(f"\n## {epic}\n")
        for s in items:
            dep = f" — depends on {', '.join(s['depends_on'])}" if s.get("depends_on") else ""
            out.append(f"- **{s['id']}** ({s['priority']}) {s['title']}{dep}  ·  traces: {', '.join(s.get('traces_to', []))}")
    return "\n".join(out) + "\n"


def main():
    if len(sys.argv) != 3:
        print("usage: agent3_stories.py <srs.html> <out_dir>", file=sys.stderr)
        return 2
    srs, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("[agent3] ANTHROPIC_API_KEY not set", file=sys.stderr)
        return 3
    import anthropic
    client = anthropic.Anthropic()

    resp = client.messages.create(
        model=MODEL, max_tokens=20000, thinking={"type": "adaptive"},
        system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content":
                   "Produce the story-driven backlog from this SRS:\n\n" + srs_text(srs)}],
        output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
    )
    text = next(b.text for b in resp.content if b.type == "text")
    stories = json.loads(text)["stories"]

    # created date: pass via env to stay deterministic; fall back to a fixed placeholder
    created = os.environ.get("PIPELINE_DATE", "2026-06-05")
    for s in stories:
        with open(os.path.join(out, f"{s['id']}.md"), "w", encoding="utf-8") as f:
            f.write(story_md(s, created))
    with open(os.path.join(out, "backlog.json"), "w", encoding="utf-8") as f:
        json.dump({"stories": stories}, f, indent=2, ensure_ascii=False)
    with open(os.path.join(out, "backlog.md"), "w", encoding="utf-8") as f:
        f.write(backlog_md(stories))
    print(f"[agent3] wrote {len(stories)} story files (status: blocked) to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
