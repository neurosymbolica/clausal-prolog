# Launch runbook — 2026-07-05 Fable partition audit

## How to launch one audit
1. Open a **new Claude Code session** in `/workspace/clausal`.
2. Set the session model to **Fable** (`/model` → Fable).
3. Paste the entire contents of the subsystem's prompt file
   (`prompts/NN-slug.md`). Each file is self-contained.
4. Answer design questions when the session asks; they are recorded for you.

## Order (later sessions inherit earlier design decisions)
- **Wave 1 — core engine:** 01 → 02 → 03 → 04
- **Wave 2 — constraints:** 05 → 06 → 07 → 08
- **Wave 3 — surface:** 09 → 10 → 11
- **Last — seams & synthesis:** 12 (only after 01–11 finish)

Sessions write to disjoint paths, so several can run at once — run as many as
you can attend to (each may block on a question). Landing wave-1 decisions in
`DESIGN-DECISIONS.md` first reduces duplicate questions later.

## After all sessions
- Session 12 has deduped findings/todos, culled false positives, and rolled
  design decisions into `DESIGN-DECISIONS.md` + `todo/audit-2026-07-05/README.md`.
- Triage `todo/audit-2026-07-05/`: `fix-*` (any implementer) vs `investigate-*`
  (Opus). Fixes are a separate, later effort — this round applied none.
