# Agent 4 — Implementation Contract (Ruby / Rack)

> **STATUS: PENDING.** This contract is a template. Agent 4 will NOT run until the
> `PENDING:` placeholders below are filled in from your actual Rack security library
> and you sign off. The orchestrator's `build` command refuses to implement while any
> `PENDING:` marker remains.

Agent 4 implements **only approved user stories**, one per branch, following the rules
below to the letter. It runs **locally** in Claude Code on this machine.

## Hard safety rules (non-negotiable)

1. **Branch-only.** Create `feature/<STORY-ID>` off the latest `main`. Never commit to
   `main`. Never force-push. Never touch other stories' branches.
2. **One story per PR.** Each approved story → its own branch and pull request.
3. **Security library is mandatory.** Every endpoint/route must go through the security
   middleware below. No bespoke auth.
4. **Scope fence.** Edit only files inside the target backend repo. Never modify this
   `rahulagents` repo, `pipeline/` run data, or anything outside the backend project.
5. **Stop on red.** If Agent 5's tests/lints fail, stop, write the failure to the run
   log, and leave the branch for morning review. Do not "fix forward" blindly past a
   security-check failure.
6. **Budget.** Respect the per-run time/token budget; if exhausted mid-story, commit
   WIP to the branch, mark the story `in_progress`, and stop.

## Target

- **Backend repo:** `PENDING: <git url or local path>`
- **Default branch:** `PENDING: main`
- **Language/runtime:** Ruby `PENDING: <version>`, Rack `PENDING: <version>`
- **App entry / structure:** `PENDING: <e.g. config.ru, app/ layout, router>`

## Security library (the "rack security" lib)

- **Where it lives:** `PENDING: <repo url or local path>`
- **How it's imported:** `PENDING: <gem name / require path>`
- **Auth/session middleware:** `PENDING: <middleware class + how it's mounted in config.ru>`
- **Route protection pattern:** `PENDING: <how a protected route declares its auth>`
- **Authorization / roles:** `PENDING: <how permissions are checked>`
- **Input validation / params:** `PENDING: <the sanctioned pattern>`
- **Error handling / responses:** `PENDING: <error shape, status codes>`
- **Secrets / config:** `PENDING: <how secrets are read; never hardcode>`

## Implementation conventions

- **Directory layout:** `PENDING:`
- **Naming:** `PENDING:`
- **Persistence layer:** `PENDING: <ORM / data access pattern>`
- **Tests:** `PENDING: <framework + where tests go + how to run one>`
- **Definition of done per story:** code + tests for every acceptance criterion +
  security middleware applied + Agent 5 green.

## How I fill this in

Point me at the Rack security library (repo URL or local path). I will read it, draft
every `PENDING:` above into concrete rules with file/line references, and show you the
completed contract for sign-off **before** Agent 4 writes any code.
