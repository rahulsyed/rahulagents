# Agent 4 — Implementation Contract (Axlr8 / The Yard Platform)

> **STATUS: DRAFT for sign-off.** Filled from Rahul's Rack Library
> (`_RackLibrary/`) and the live `py2026` build. Review and approve before Agent 4
> writes any code. This contract makes Agent 4 = your existing **story-driven run loop**,
> not a new system.

Agent 4 implements **only approved user stories**, one per run, locally in Claude Code,
following your Rack Library standards exactly. It does **not** invent stack, structure,
or conventions — it reuses what's already settled.

## Target — SEPARATE from py2026

- **Repo:** a **dedicated, separate** project repo, set per run via `TARGET_REPO`
  (or `state.json` → `target_repo`). **rahulagents never writes into `py2026`.** Default
  is empty → fully self-contained: approved stories live in
  `rahulagents/pipeline/<name>/approved/` and build nowhere until you point at a repo.
- **Standards are reused, the codebase is not** — Agent 4 follows the Rack Library
  conventions (`_RackLibrary/stacks/`, `workflows/`, `lessons/`) but applies them inside
  the dedicated target repo, keeping this work isolated from The Yard Platform.
- **Canonical loop:** `_RackLibrary/workflows/story-driven-development.md`.
- **Stack (locked):** Next.js App Router · TypeScript **strict (no `any`)** · Tailwind 4 ·
  Supabase (Postgres + Auth + **RLS** + Realtime + Storage) · Stripe · Resend · Twilio ·
  Vercel · Zod · lucide-react. See `_RackLibrary/stacks/nextjs-supabase-stripe.md`.

## The run loop (ONE story per run)

1. **Find work** — list `py2026/.stories/*.md`, read frontmatter, filter `status: pending`,
   sort `priority` (high>medium>low) then `created` (oldest first), pick the first.
   *(Only stories you've approved are `pending` — see the gate below.)*
2. **Claim** — set `status: in-progress` in the story file.
3. **Read everything first** — every `Reference Files` entry before writing any code.
4. **Pre-migration schema audit (MANDATORY if the story touches the DB)** —
   query the live Supabase OpenAPI (`GET /rest/v1/` with the service_role key), parse
   `definitions.<table>.properties`, record real columns/types/NOT NULL, and write
   `ALTER TABLE` (not `CREATE TABLE`) when a table already exists. Full checklist:
   `_RackLibrary/lessons/supabase.md` → "MANDATORY PRE-MIGRATION CHECKLIST".
5. **Implement** — only the story's changes; reuse `components/ui/*`; follow the
   conventions block below.
6. **Validate** — from `apps/web/`: `npx tsc --noEmit`, then `npm run build`, then
   `npm run lint`. On failure, fix and retry — **max 2 attempts**.
7. **Update story** — success: `status: done`, `completed: <YYYY-MM-DD>`; failure:
   `status: failed`, `error: "<short message>"`.
8. **Commit, NO push** — stage modified source + the story file; message
   `feat(STORY-XXX): <title>` / `fix(STORY-XXX): <title>`. `done` = "Deploy Ready"; a
   human flips deploy. **Never push.**

## Security & data rules (the "rack library security")

- **RLS from day one** — every domain table is row-level-secured and **scoped by
  `tenant_id`**. No table ships without an RLS policy. (Locked decision: single-tenant
  Y1, `tenant_id` baked in for Y2.)
- **No bespoke auth** — use the Supabase session/middleware (`lib/supabase/{client,server,middleware}.ts`,
  root `middleware.ts`). Protected pages live under `app/(protected)/`.
- **API routes** — validate input with **Zod**; return proper HTTP codes; JSON error
  shape `{ error: string, details?: any }`.
- **Secrets** — read from env only (`.env.local`, see `_RackLibrary/templates/env.example`);
  **never hardcode** keys; never log secrets; never commit `.env*`.
- **Stripe / webhooks** — verify webhook signatures; follow `_RackLibrary/lessons/stripe.md`
  and `py2026/STRIPE-PAYMENT-AUDIT.md`.
- **Conform to existing audits** — don't regress `py2026/SECURITY-AUDIT-SUMMARY.txt`,
  `SUPABASE-ARCHITECTURE-AUDIT.md`, `STRIPE-PAYMENT-AUDIT.md`.

## Conventions (from the rack)

- TypeScript strict, **no `any`**; absolute imports from `@/`.
- kebab-case files, PascalCase components, props named `<Component>Props`.
- `next/image` for all images; reuse `components/ui/` rather than adding a UI lib.
- House rules (`_RackLibrary/CLAUDE.md`): **don't** add doc files unless the story asks;
  **don't** add comments unless the WHY is non-obvious; **don't** refactor outside scope.

## Hard safety rules

1. **One story per run.** Never batch.
2. **Scope fence.** Modify **only** the story's `Files to Modify`. Never edit `rahulagents`,
   `pipeline/` data, or anything outside `py2026` (or the story's target repo).
3. **Branch/commit, never push.** Never force-push, never rebase, never skip git hooks.
4. **Stop on red.** After 2 failed validate attempts → `status: failed` + `error:` and
   stop. Never force past a security/RLS failure.
5. **Budget.** If the context window runs low → commit partial progress with
   `status: in-progress` and stop.
6. **Update the rack after real work** — log lessons to `_RackLibrary/lessons/<area>.md`
   per `_RackLibrary/CLAUDE.md` § "After completing any task."

## The approval gate (how it maps to your lifecycle)

Agent 3 writes new stories into `py2026/.stories/` as **`status: blocked`**
(awaiting your approval). `pipeline approve <name> <ids|all>` flips approved stories to
**`status: pending`** — and only then does your existing scheduler/Agent 4 pick them up.
Nothing you didn't approve is ever `pending`, so nothing unapproved is ever built.
