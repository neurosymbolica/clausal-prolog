# Audit 2026-07-05 — queued todos

Fixes are QUEUED here, never applied by the audit sessions.

- `fix-<ID>-<slug>.md` — remediation understood; any implementer.
- `investigate-<ID>-<slug>.md` — needs deeper root-cause/design work; tagged for Opus.

Completed todos move to `todo/done/` (repo convention). Session 12 dedups and
maintains this index.

| Todo | Kind | Severity | Finding | Owning subsystem | Status |
|------|------|----------|---------|------------------|--------|
| `fix-A01-occurs-check-compound-blindness.md` | fix | correctness | A01-F001 | A01 term-layer | queued |
| `fix-A01-capi-put-attr-promote-path.md` | fix | correctness (latent C; unconfirmed — capi-only) | A01-F002 | A01 term-layer | queued |
| `fix-A01-compound-var-functor.md` | fix | correctness | A01-F003 | A01 term-layer | queued — direction blocked on parked A01-D004 |
| `fix-A01-kwterm-unify-hook.md` | fix | correctness | A01-F004 | A01 term-layer | queued |
| `fix-A01-seg-unify-gens-retention.md` | fix | memory | A01-F005 | A01 term-layer | queued |
| `fix-A01-seglist-element-var-ground-path.md` | fix | correctness | A01-F006 | A01 term-layer | queued |
| `fix-A01-seglist-bytes-target.md` | fix | correctness | A01-F007 | A01 term-layer | queued |
| `investigate-A01-walk-vs-deref-walk-split.md` | investigate (Opus) | design/correctness | A01-F008 (+ `_deref_walk` seam → A04/A09) | A01 ↔ A04/A09 | queued |
| `fix-A01-segstring-scalar-varseg-guard.md` | fix | error-path | A01-F009 | A01 term-layer | queued |
| `fix-A01-seg-getitem-slice-in-prefix.md` | fix | design (low) | A01-F010 | A01 term-layer | queued |
| `fix-A01-terms-all-exports.md` | fix | doc-drift | A01-F011 | A01 term-layer | queued |
| `investigate-A01-parked-design-decisions.md` | investigate (**USER**, not Opus) | design | A01-D001 / A01-D002 / A01-D004 | A01 (D001 cross-cuts A02/A04) | parked by user 2026-07-05 |
