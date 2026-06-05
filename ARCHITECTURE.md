# rahulagents — 5-Agent Video→Backend Pipeline

Turn a **video** into a **reviewed, tested backend implementation** through five
staged agents, with **one human approval gate** before any code is written, and an
optional **nightly** build run. Everything security-sensitive runs **locally** on
your machine, where your Ruby/Rack security library lives.

```
Agent 1 ─► Agent 2 ─► Agent 3 ─►  ⛔ APPROVAL GATE  ─► Agent 4 (nightly) ─► Agent 5
download    SRS +       project +   you approve in chat    implement on a        test +
(yt-dlp)    screenshots  user        (per story)            feature branch using  validate,
                         stories                            your Rack sec lib     open PR
```

## Design principles

1. **Local-first for anything sensitive.** Agents 4–5 (implementation + review) run
   on this machine in Claude Code, where your internal Rack security library lives.
   Nothing security-sensitive is shipped to a cloud container.
2. **One hard approval gate.** Agents 1–3 are fully automated. **No code is written
   until you approve specific user stories.** The nightly job only builds approved,
   not-yet-built stories.
3. **Branch-only, PR-per-story.** Agent 4 never commits to `main`. Each approved
   story becomes `feature/<story-id>` and a pull request. You merge; nothing lands
   without you.
4. **State folder = single source of truth.** Every run lives under
   `pipeline/<project>/` with a `state.json` that records stage, approvals, branches,
   and run logs. The pipeline is resumable and auditable.
5. **Budgeted night runs.** Agent 4 respects a time/token budget so an overnight run
   can't run away, and stops-and-logs on test failure rather than forcing through.

## The state machine

`orchestrator/pipeline.py` drives a per-project `state.json`:

```
created → downloaded → requirements_done → stories_done → AWAITING_APPROVAL
        → approved → implementing → review → pr_open → (you merge)
```

| Command | Does |
|---|---|
| `pipeline new <url-or-path> [--name X]` | create project, run Agents 1→2→3, stop at the gate |
| `pipeline status [name]` | show stage, stories, approvals, open PRs |
| `pipeline approve <name> <STORY-IDs… \| all>` | mark stories approved for build |
| `pipeline build <name>` | run Agent 4→5 over approved-unbuilt stories (manual trigger) |
| `pipeline night` | the scheduled entry point — `build` across all projects with approvals |

## The agents

| # | Agent | Local? | Implementation | Status |
|---|---|---|---|---|
| 1 | **Download** | yes | `agents/agent1_download.py` (yt-dlp) | ✅ ready |
| 2 | **Requirements + screenshots** | yes | `agents/agent2_requirements/` (vendored video2spec) | ✅ ready |
| 3 | **Project + user stories** | yes | `agents/agent3_stories.py` (Claude API, reads the SRS) | ✅ ready |
| ⛔ | **Approval gate** | you | `pipeline approve` in chat | ✅ ready |
| 4 | **Implementation** | yes | `agents/agent4_contract.md` — the contract Agent 4 follows | ⏳ needs your Rack security library |
| 5 | **Reviewer** | yes | `agents/agent5_review.md` — test + validate spec | ⏳ needs your test/lint commands |

## What's pending your input (Agents 4 & 5)

Agent 4 implements against **your** conventions, so before it writes a line of code:

1. **Point me at your Ruby/Rack security library** (repo URL or local path). I read it
   and fill in `agents/agent4_contract.md` — the explicit rules Agent 4 must follow
   (auth/session middleware, route protection, error handling, test setup). **You
   sign off on that contract before any implementation runs.**
2. **Tell me the green commands** for Agent 5 (e.g. `bundle exec rspec`, `rake test`,
   `brakeman`).
3. **Nightly time** (e.g. 01:00) and the **target backend repo** for the PRs.

Recommended: run Agent 4 **once in the daytime together** on the first story to tune
the contract, then enable the nightly schedule.

## Security & safety boundaries

- The pipeline `pipeline/` run data, any API keys, and downloaded videos are
  **gitignored** — this public repo holds the framework only, never run artifacts.
- Agent 4 is constrained by `agent4_contract.md`: branch-only, one story per PR,
  must use the security middleware, no edits outside the backend repo, hard
  time/token budget, stop-on-red.
- Approvals are explicit and per-story; "approve all" still only covers the stories
  currently in the backlog.
