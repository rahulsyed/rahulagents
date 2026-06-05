---
description: Drive the 5-agent video→backend pipeline (download → SRS → stories → approve → build → review)
---

You are the controller for the rahulagents pipeline (see ARCHITECTURE.md). Map the
user's request to `orchestrator/pipeline.py` and the per-agent scripts.

Arguments: `$ARGUMENTS`

## Routing

- **"new <url-or-path>"** → run `python orchestrator/pipeline.py new <src> [--name N]`.
  This runs Agents 1→2→3 and STOPS at the approval gate. Then show the user the
  generated backlog (`pipeline/<name>/stories/backlog.md`) and ask which stories to
  approve. Do not proceed to implementation.

- **"status [name]"** → `python orchestrator/pipeline.py status [name]`.

- **"approve <name> <ids|all>"** → `python orchestrator/pipeline.py approve <name> <ids>`.

- **"build <name>"** → only if `agents/agent4_contract.md` has NO `PENDING:` markers.
  If it still has `PENDING:`, STOP and tell the user Agent 4 isn't activated yet —
  you need their Rack security library to fill the contract, and their sign-off.
  When activated: for each approved-unbuilt story, follow `agents/agent4_contract.md`
  exactly — create `feature/<STORY-ID>`, implement, then run Agent 5 per
  `agents/agent5_review.md`, open a PR, and update state. One story per branch/PR.
  Never commit to main. Stop-on-red.

## Hard rules

- Never write implementation code before the approval gate is passed AND the Agent 4
  contract is filled and signed off.
- Security-sensitive work runs locally only.
- Keep `pipeline/` run data and secrets out of git (already gitignored).
- If `ANTHROPIC_API_KEY` is unset, Agents 2/3's autonomous steps degrade to the
  Claude-Code hand-off; say so rather than failing silently.
