# Agent 5 — Reviewer / Validation Spec

> **STATUS: PENDING** the green commands for your backend (test + security lint).

Agent 5 runs after Agent 4 on each `feature/<STORY-ID>` branch. It validates the work,
writes a report, and opens (or updates) the pull request. It is the gate between
"implemented" and "ready for your morning review."

## What it checks (in order)

1. **Build / boot.** App boots clean. `PENDING: <command, e.g. bundle exec rackup --dry-run>`
2. **Tests.** Full suite green. `PENDING: <e.g. bundle exec rspec>`
   - Plus: each acceptance criterion of the story maps to at least one passing test.
3. **Security lint.** `PENDING: <e.g. brakeman -q>` — no new warnings.
4. **Security-contract conformance.** Every new/changed route goes through the security
   middleware from `agent4_contract.md` (no unprotected endpoints, no bespoke auth).
5. **Diff hygiene.** Change is scoped to the story; no stray files; no secrets committed
   (scan the diff for keys/tokens).

## Outputs

- `pipeline/<name>/runs/<date>/<STORY-ID>-review.md` — verdict + evidence (test output,
  lint output, acceptance-criteria coverage table).
- **PR per story** with the review report in the body, labeled `needs-human-review`.
- Updates `state.json`: story → `built` on green, or `in_progress` + reason on red.

## Verdict rules

- **GREEN** → PR opened, story marked built, ready for you to merge.
- **RED** → branch kept, PR draft (or none), story left `in_progress`, failure logged.
  Agent 4 does **not** auto-retry security failures — those wait for you.

## How I fill this in

Tell me your green commands (test run, security lint, boot check). I wire them here and
into the orchestrator so the nightly run validates exactly the way you do by hand.
