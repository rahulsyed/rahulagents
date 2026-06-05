#!/usr/bin/env python3
"""agent3_stories.py - turn an SRS into an epics -> user-stories backlog (Claude API).

Usage:
    python agents/agent3_stories.py <srs.html> <out_dir>

Reads the rendered SRS (Agent 2 output), extracts the requirements/text, and asks
Claude to produce a backlog of user stories grouped by epic, each with a stable id,
acceptance criteria, and a trace back to the FR-* requirement(s). Writes:
    <out_dir>/backlog.json   (machine-readable; the orchestrator reads ids from here)
    <out_dir>/backlog.md     (human review at the approval gate)

Requires ANTHROPIC_API_KEY. Default model claude-opus-4-8 (AGENT_MODEL to override).
Stories are sequenced shared-spine-first; the orchestrator gates implementation on
your per-story approval.
"""
import json
import os
import re
import sys

MODEL = os.environ.get("AGENT_MODEL", "claude-opus-4-8")

STORY_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "stories": {
            "type": "array",
            "items": {
                "type": "object", "additionalProperties": False,
                "properties": {
                    "id": {"type": "string"},          # e.g. STORY-01
                    "epic": {"type": "string"},
                    "title": {"type": "string"},
                    "as_a": {"type": "string"},
                    "i_want": {"type": "string"},
                    "so_that": {"type": "string"},
                    "acceptance_criteria": {"type": "array", "items": {"type": "string"}},
                    "traces_to": {"type": "array", "items": {"type": "string"}},
                    "priority": {"type": "string"},     # MUST/SHOULD/COULD
                    "depends_on": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["id", "epic", "title", "as_a", "i_want", "so_that",
                             "acceptance_criteria", "traces_to", "priority", "depends_on"],
            },
        }
    },
    "required": ["stories"],
}

SYSTEM = """You are a senior product owner. From a Software Requirements Specification \
you produce an implementation-ready backlog of user stories grouped by epic.

Rules:
- One story = one shippable slice. Give each a stable id STORY-NN.
- Every story must trace to one or more FR-*/NFR-* requirement ids from the SRS.
- Acceptance criteria are concrete and testable (Given/When/Then style is fine).
- Sequence foundational/shared stories first; set depends_on accordingly.
- Carry the requirement's priority (MUST/SHOULD/COULD).
- Do not invent scope beyond the SRS."""


def srs_text(path):
    html = open(path, encoding="utf-8").read()
    # crude tag strip - enough to feed requirements/prose to the model
    html = re.sub(r"<script.*?</script>", " ", html, flags=re.S)
    html = re.sub(r"<style.*?</style>", " ", html, flags=re.S)
    html = re.sub(r"data:image/[^\"']+", "", html)  # drop base64 blobs
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    return text[:60000]


def to_md(stories):
    out = ["# Backlog (review, then approve with `pipeline approve <name> <ids|all>`)\n"]
    by_epic = {}
    for s in stories:
        by_epic.setdefault(s["epic"], []).append(s)
    for epic, items in by_epic.items():
        out.append(f"\n## {epic}\n")
        for s in items:
            dep = f" (depends on {', '.join(s['depends_on'])})" if s["depends_on"] else ""
            out.append(f"### {s['id']} — {s['title']}  `{s['priority']}`{dep}")
            out.append(f"*As a* {s['as_a']}, *I want* {s['i_want']}, *so that* {s['so_that']}.")
            out.append("**Acceptance criteria:**")
            out += [f"- {c}" for c in s["acceptance_criteria"]]
            out.append(f"*Traces to:* {', '.join(s['traces_to'])}\n")
    return "\n".join(out)


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
        model=MODEL, max_tokens=16000, thinking={"type": "adaptive"},
        system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content":
                   "Produce the user-story backlog from this SRS:\n\n" + srs_text(srs)}],
        output_config={"format": {"type": "json_schema", "schema": STORY_SCHEMA}},
    )
    text = next(b.text for b in resp.content if b.type == "text")
    data = json.loads(text)
    with open(os.path.join(out, "backlog.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    with open(os.path.join(out, "backlog.md"), "w", encoding="utf-8") as f:
        f.write(to_md(data["stories"]))
    print(f"[agent3] wrote {len(data['stories'])} stories to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
