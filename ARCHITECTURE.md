# rahulagents — 5-Agent Video→Backend Pipeline

Turn a **video** into **reviewed, tested feature work** on The Yard Platform through
five staged agents, with **one human approval gate** before any code is written, and an
optional **nightly** build run. It plugs into the existing **story-driven-development**
workflow and **Rack Library** standards (Next.js + Supabase + Stripe, RLS-scoped
security). Everything runs **locally**; the target build is `C:\workspace\py2026`.

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
| 4 | **Implementation** | yes | `agents/agent4_contract.md` — = your story-driven run loop | 📝 contract drafted, awaiting sign-off |
| 5 | **Reviewer** | yes | `agents/agent5_review.md` — `tsc`+`build`+`lint`+RLS/security | ✅ ready |

## Activation (Agents 4 & 5)

Both are now **filled from your Rack Library + `py2026`** — Next.js + Supabase + Stripe,
TS strict, RLS-scoped, validate with `npx tsc --noEmit` / `npm run build` / `npm run lint`,
commit-no-push. To switch Agent 4 on:

1. **Review `agents/agent4_contract.md`** and change its header to `STATUS: APPROVED`
   (the orchestrator refuses to build until then).
2. **Confirm target + schedule** — default target `C:\workspace\py2026`, nightly time TBD.

Recommended: run the **first story together in daylight** to tune the contract, then
enable the nightly schedule (your existing `claude-scheduler.sh` pattern, pointed at the
target repo's `.stories/`).

## Dashboard

`dashboard/build_dashboard.py` renders every run (link → SRS → stories → traceability)
either as a static `index.html` or as a live server that rebuilds on each request.
`--phone` binds it to the LAN and prints a QR code (`dashboard/qr.py`, a small
dependency-free encoder) so you can pull the dashboard up on a phone over the same Wi-Fi;
`/phone` shows the same code in the browser. LAN exposure is opt-in — plain `--serve`
stays on `127.0.0.1`.

## Security & safety boundaries

- The pipeline `pipeline/` run data, any API keys, and downloaded videos are
  **gitignored** — this public repo holds the framework only, never run artifacts.
- Agent 4 is constrained by `agent4_contract.md`: branch-only, one story per PR,
  must use the security middleware, no edits outside the backend repo, hard
  time/token budget, stop-on-red.
- Approvals are explicit and per-story; "approve all" still only covers the stories
  currently in the backlog.
