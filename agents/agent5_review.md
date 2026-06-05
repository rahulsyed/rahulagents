# Agent 5 — Reviewer / Validation Spec (Axlr8 / The Yard Platform)

> **STATUS: READY** (commands derived from `py2026` + the Rack Library).

Agent 5 runs after Agent 4 on each implemented story. Much of it is already the
"Validate" step of your story loop; Agent 5 adds the security/RLS conformance checks
and writes the verdict.

## Checks (in order), run from `apps/web/`

1. **Types** — `npx tsc --noEmit` → zero errors (TS strict, no `any`).
2. **Build** — `npm run build` (`next build`) → succeeds.
3. **Lint** — `npm run lint` (`eslint`) → no new errors.
4. **Acceptance criteria** — each criterion in the story maps to evidence (a test, a
   build artifact, or a verifiable code path).
5. **Security / RLS conformance:**
   - Any new/changed domain table has an **RLS policy scoped by `tenant_id`**.
   - DB changes followed the **pre-migration schema audit** (ALTER vs CREATE).
   - Protected routes go through Supabase middleware; API routes validate with **Zod**.
   - No regressions vs `py2026/SECURITY-AUDIT-SUMMARY.txt`,
     `SUPABASE-ARCHITECTURE-AUDIT.md`, `STRIPE-PAYMENT-AUDIT.md`.
6. **Diff hygiene** — change scoped to the story's `Files to Modify`; no stray files; no
   secrets in the diff (scan for keys/tokens); `.env*` not staged.

## Verdict

- **GREEN** → story `status: done`, `completed: <date>`, committed (NO push). "Deploy
  Ready" on the Story Board; you flip deploy.
- **RED** → story `status: failed` + `error: "<reason>"`, branch/work-in-place left for
  triage. Security/RLS failures are **never** auto-fixed past — they wait for you.

## Output

- A short report per story (types/build/lint output, acceptance-criteria coverage,
  security checklist) written alongside the story (mirrors the existing
  `STORY-0XX_Test_Report.html` pattern in `py2026/`).
- Lessons logged to `_RackLibrary/lessons/<area>.md` per the rack's "after any task" rule.
