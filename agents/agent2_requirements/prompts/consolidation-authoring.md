# Consolidation Authoring Guide (Master SRS)

After every per-video Volume spec exists, run the **consolidation pass** to merge
them into one Master SRS. `scripts/consolidate.py` does the heavy lifting; this
guide explains the inputs and conventions.

## Command
```
python3 scripts/consolidate.py <master_meta.json> <vol1_spec.json> <vol2_spec.json> ... <output.html>
```
Pass the volume spec JSONs **in volume order**. The output is one self-contained
HTML (same house style as the volumes).

## What it does automatically
- **Requirements register (deduped).** Reads every `reqs` block from every volume,
  normalizes each statement, and clusters near-duplicates (≥0.86 similarity).
  Each cluster becomes one master requirement with a fresh `MR-####` id, the
  highest priority among its members, the most complete wording, and a
  **Source(s)** column listing every original `ID (Volume)` for traceability.
  Merged clusters get a "merged" tag.
- **Unified data model.** Reads every data-model table (any table whose first
  header starts with "Entity"). Same-named entities are combined; attributes are
  **unioned** and relationships collected. This is the single schema to build against.
- **Cross-surface map.** An Area × Volume matrix (● = covered) showing which
  requirement areas span which volumes — the shared spine of the product.
- **Per-volume appendix.** Full traceability: every original requirement, grouped
  by volume.

## For dedup to work well
- Keep requirement **areas consistent across volumes** (`FR-SCH-*` for scheduler in
  every volume, not `FR-SCHED-*` in one and `FR-CAL-*` in another). Area is parsed
  from the ID (`FR-<AREA>-NN`).
- Write each requirement as one atomic statement (the authoring guide already says this).
- It's fine if wording differs slightly between volumes — the fuzzy matcher handles it.

## For data-model merging to work
- In each volume, put the data model in a `table` block whose **first header is
  "Entity"** (e.g. headers `["Entity","Attributes","Relationships"]` or
  `["Entity","Key attributes","Relationships"]`).
- Use consistent entity names across volumes (`Member`, not `Player` in one and
  `Member` in another) so they merge instead of duplicating.

## master_meta.json schema
```jsonc
{
  "title": "Club Management Platform — MASTER SRS",
  "badge": "CONSOLIDATED MASTER SRS",
  "subtitle": "One-paragraph scope.",
  "accent": "red",
  "meta": {"Prepared for": "...", "Version": "1.0"},
  "xref": "Optional HTML box describing the series.",
  "footer": "Provenance line.",
  "volumes": [
    {"spec": "vol1_spec.json", "label": "Vol. 1", "surface": "Admin Console", "source": "Front-desk training (25m)"},
    {"spec": "vol2_spec.json", "label": "Vol. 2", "surface": "Member Portal",  "source": "Player tutorial (2m)"}
  ],
  "extra_sections": [
    // OPTIONAL: extra narrative sections rendered via build_srs.py block schema
    // (e.g. an "Architecture" or "Build Phasing" section you author by hand).
  ]
}
```
- `volumes[].spec` must match the **basename** of the spec file you pass on the CLI.
- `extra_sections` use the exact same block schema as `prompts/srs-authoring.md`
  (p, h3, h4, ul, figure, table, flow, reqs, callout, pills).

## After the master exists (optional follow-ons)
- **DB schema** — translate the Unified Data Model into Prisma/SQL.
- **Sprint backlog** — turn the master requirements register into epics → stories,
  sequenced by the cross-surface map (shared-spine areas first).

Offer these to the user; don't generate unprompted.
