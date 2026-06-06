# rahulagents

A **5-agent pipeline** that turns a **video** into **reviewed, tested feature work** on
The Yard Platform — with a human approval gate before any code is written and an optional
nightly build run. It plugs into the existing **story-driven-development** workflow and
**Rack Library** standards (Next.js + Supabase + Stripe; RLS-scoped security). Everything
runs **locally**, on your machine. Target build: `C:\workspace\py2026`.

```
Agent 1 ─► Agent 2 ─► Agent 3 ─►  ⛔ APPROVAL GATE  ─► Agent 4 (nightly) ─► Agent 5
download    SRS +       project +   you approve in chat    implement on a        test +
(yt-dlp)    screenshots  user        (per story)            feature branch using  validate,
                         stories                            your Rack sec lib     open PR
```

See **[ARCHITECTURE.md](ARCHITECTURE.md)** for the full design.

## Layout

```
rahulagents/
├── ARCHITECTURE.md                 # the design (state machine, gate, nightly, safety)
├── orchestrator/pipeline.py        # state machine: new / status / approve / build / night
├── dashboard/build_dashboard.py    # → dashboard/index.html: link → SRS → stories → traces
├── agents/
│   ├── agent1_download.py          # ✅ download a video (yt-dlp)
│   ├── agent2_requirements/        # ✅ vendored video2spec (SRS + screenshots)
│   ├── agent3_stories.py           # ✅ SRS → epics/user-stories backlog (Claude API)
│   ├── agent4_contract.md          # ⏳ implementation contract (PENDING your Rack sec lib)
│   └── agent5_review.md            # ⏳ test + validate spec (PENDING your green commands)
├── .claude/commands/pipeline.md    # /pipeline controller for Claude Code
└── pipeline/                       # (gitignored) per-project run state + artifacts
```

## Usage (once activated)

```bash
# create a project; runs Agents 1→2→3, then STOPS at the approval gate
python orchestrator/pipeline.py new <video-url-or-path> --name pickleyard

# review pipeline/pickleyard/stories/backlog.md, then approve specific stories
python orchestrator/pipeline.py approve pickleyard STORY-01 STORY-03

# build approved stories (manual) — Agent 4 implements + Agent 5 reviews → PR per story
python orchestrator/pipeline.py build pickleyard

# the scheduled nightly entry point builds approved-unbuilt stories across all projects
python orchestrator/pipeline.py night

# visualize every run: which link ran, its SRS, story count, and traceability
python dashboard/build_dashboard.py            # static → open dashboard/index.html
python dashboard/build_dashboard.py --serve    # live, auto-refreshing → http://localhost:8770
#   live mode: per-run "Open SRS" + "Browse stories" (each story in-browser) + a
#   Requirement → stories reverse map; rebuilds on every page load as new runs land.
```

## Separation from py2026

This pipeline is **completely self-contained**. All run data lives under
`rahulagents/pipeline/<name>/`, and approved stories are written to
`pipeline/<name>/approved/` — **nothing is ever written into `py2026`**. It only mirrors
into an external repo if you *deliberately* set `TARGET_REPO` to a **dedicated, separate**
project (not py2026). The Rack Library *standards* are reused; the py2026 *codebase* is not
touched.

In Claude Code you can drive the same flow with **`/pipeline new …`**, **`/pipeline
approve …`**, etc.

## Status

| Stage | Ready? |
|---|---|
| Agents 1–3 (download → SRS → stories) + approval gate | ✅ scaffolded, emits your `.stories/*.md` format |
| Agent 4 (implementation) | 📝 contract **drafted from your Rack Library** — awaiting your sign-off |
| Agent 5 (review) | ✅ `tsc --noEmit` + `build` + `lint` + RLS/security/pre-migration checks |
| Nightly schedule | ⏳ set a time once you sign off the contract |

**Validation (Agent 5), from `apps/web/`:** `npx tsc --noEmit` → `npm run build` → `npm run lint`,
plus the Supabase pre-migration audit + RLS/secret checks (see `agents/agent5_review.md`).

**To activate Agent 4:** review `agents/agent4_contract.md` (drafted from `_RackLibrary/`
+ `py2026`), then change its header to `STATUS: APPROVED`. The orchestrator refuses to
build until it's signed. Recommended: run the first story together in daylight, then
enable the nightly run.

## Safety

- `pipeline/` run data, secrets, and API keys are gitignored — this public repo holds the
  **framework only**, never run artifacts or customer data.
- Agent 4 follows the story-driven loop **exactly**: one story per run, scoped to the
  story's `Files to Modify`, RLS-scoped Supabase, validate → commit, **never push**.
  `status: done` = "Deploy Ready"; you flip deploy. Nothing unapproved is ever `pending`.
