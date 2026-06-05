# rahulagents

A **5-agent pipeline** that turns a **video** into a **reviewed, tested backend
implementation** — with a human approval gate before any code is written and an
optional nightly build run. Security-sensitive work runs **locally**, on your machine,
using your own Ruby/Rack security library.

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
```

In Claude Code you can drive the same flow with **`/pipeline new …`**, **`/pipeline
approve …`**, etc.

## Status

| Stage | Ready? |
|---|---|
| Agents 1–3 (download → SRS → stories) + approval gate | ✅ scaffolded |
| Agent 4 (implementation) | ⏳ needs your Rack security library to fill `agent4_contract.md` (+ your sign-off) |
| Agent 5 (review) | ⏳ needs your green commands (test / security lint) |
| Nightly schedule | ⏳ set a time once Agent 4 is activated |

**To activate Agents 4–5:** point me at your Ruby/Rack security library and give me your
test/lint commands. I read the library, fill the contract with concrete file-referenced
rules, and you sign off **before** any code is written. Recommended: run the first story
together in daylight to tune the contract, then turn on the nightly run.

## Safety

- `pipeline/` run data, secrets, and API keys are gitignored — this public repo holds
  the **framework only**.
- Agent 4 is branch-only, one-story-per-PR, must use your security middleware, scoped to
  the backend repo, budgeted, and stops on red. Nothing lands on `main` without you.
