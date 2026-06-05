# SRS Authoring Guide (Stage 6)

This is the agent's reference for turning what it read on screen into the JSON spec
that `build_srs.py` renders. Work through it after Stages 1–5 are done.

## Inputs you have at this point
- `contact_*.jpg` — you've **viewed** these; you know the video's structure.
- `shots/NN-*.jpg` — 8–12 optimized screenshots you **viewed and read**.
- `*.transcript_raw.txt` — the raw ASR output.
- Your notes: every label/field/button/column/state you read off each screen.

## Step A — Clean the transcript
Turn the raw ASR into 10–34 timestamped segments. For each segment:
- fix obvious ASR errors using the on-screen context as ground truth;
- keep it to one idea / one screen;
- assign an approximate `ts` ("M:SS").
For videos > 20 min, organize **by module** rather than literal sentences.

## Step B — Decide structure
Pick the volume/surface (see CLAUDE.md table). List the functional sections —
one per module you saw. Order them the way the video did, or logically
(setup → core → admin → reference).

## Step C — Write requirements
For each section, write atomic, testable requirements:
- `FR-<AREA>-NN`, priority `MUST | SHOULD | COULD`.
- One statement each. No compound "and also" requirements.
- Trace each to something visible in a screenshot.

## Step D — Derive the data model
From the fields/columns you read, list entities, key attributes, and relationships.
Put this in a `table` block in a "Data Model" section.

## Step E — Assemble the JSON spec
Schema (see `examples/example_spec.json` for a full instance):

```jsonc
{
  "title": "Club Management Platform — <Surface>",
  "badge": "SRS — VOL. N (<SURFACE>)",
  "subtitle": "One-paragraph scope statement.",
  "accent": "blue|green|purple|red|teal|slate",
  "meta": {"Source": "...", "Duration": "MM:SS", "Prepared for": "...", "Version": "1.0"},
  "xref": "Optional HTML cross-reference box for multi-volume sets.",
  "footer": "Provenance line.",
  "sections": [
    {
      "id": "purpose", "number": "SECTION 1", "title": "Purpose & Scope",
      "blocks": [
        {"type": "p", "html": "Prose with <b>inline html</b> allowed."},
        {"type": "figure", "image": "shots/01-foo.jpg", "caption": "What this shows."},
        {"type": "h4", "text": "Sub-heading"},
        {"type": "ul", "items": ["point one", "point two"]},
        {"type": "table", "headers": ["Field","Notes"], "rows": [["A","B"],["C","D"]]},
        {"type": "flow", "steps": [{"title":"Step","detail":"what happens"}]},
        {"type": "reqs", "items": [
          {"id":"FR-AREA-01","priority":"MUST","text":"The system shall ..."}
        ]},
        {"type": "callout", "kind": "ok", "label": "Client relevance:", "text": "..."},
        {"type": "pills", "items": ["Tag A","Tag B"]}
      ]
    }
  ],
  "transcript": [
    {"ts": "0:00", "text": "Cleaned segment ..."}
  ]
}
```

Block types: `p` (html allowed), `h3`, `h4`, `ul`, `figure`, `table`, `flow`,
`reqs`, `callout` (kind = info|warn|ok), `pills`.

`figure.image` paths are relative to the spec file's directory — use bare filenames if the spec sits next to its images.

## Step F — Render and present
```
python3 scripts/build_srs.py spec.json <project>-<surface>-SRS.html
```
Then present the HTML, the transcript `.txt`, and the `shots/` folder to the user.

## Quality bar before you ship
- Every screen you describe has a figure you actually viewed.
- No verbatim narration dumps; requirements are your own wording.
- Transcript fidelity note present (the renderer adds it automatically).
- Requirements atomic, numbered, prioritized.
- Data model + NFRs present.
