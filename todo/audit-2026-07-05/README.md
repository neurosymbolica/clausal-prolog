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
| `fix-A02-dispatch-partial-term-fallback.md` | fix | correctness | A02-F001 | A02 compiler-heads | queued |
| `fix-A02-list-dispatch-fallthrough.md` | fix | correctness | A02-F002 | A02 compiler-heads | queued |
| `fix-A02-head-wildcard-accept-all.md` | fix | correctness | A02-F003 | A02 compiler-heads (assertz seam → A09) | queued |
| `fix-A02-multistar-trailing-fixed.md` | fix | correctness | A02-F004 | A02 compiler-heads | queued |
| `fix-A02-dispatch-docstring-arg-offsets.md` | fix | doc-drift | A02-F005 | A02 compiler-heads | queued |
| `investigate-A02-parked-design-decisions.md` | investigate (**USER**, not Opus) | design | A02-D002 (depends on A01-D001) | A02 (cross-cuts A04 tabling keys) | parked by user preference 2026-07-05 |
| `fix-A03-tro-nondet-prefix.md` | fix | correctness (solution loss) | A03-F001 | A03 compiler-goals | queued |
| `fix-A03-dr-nondet-prefix.md` | fix | correctness (data corruption; same root as F001) | A03-F002 | A03 compiler-goals | queued |
| `fix-A03-tro-signal-bucket-not-generator.md` | fix | correctness (crash) | A03-F003 | A03 compiler-goals | queued |
| `fix-A03-catch-functor-catcher.md` | fix | correctness | A03-F004 | A03 compiler-goals (unify seam → A01-D004) | queued |
| `fix-A03-setof-not-sorted.md` | fix | correctness | A03-F005 | A03 compiler-goals | queued |
| `fix-A03-findall-template-sharing.md` | fix | correctness | A03-F006 | A03 compiler-goals (design A03-D002) | queued |
| `fix-A03-specialize-midbody-goals.md` | fix | correctness | A03-F007 | A03 specialization (design A03-D003) | queued |
| `fix-A03-deep-unfold-const-args.md` | fix | correctness | A03-F008 | A03 specialization | queued |
| `fix-A03-cpd-extension-chaining.md` | fix | correctness (solution loss) | A03-F009 | A03 specialization | queued |
| `fix-A03-readme-ctco-drift.md` | fix | doc-drift | A03-F010 | A03 compiler-goals | queued |
| `investigate-A03-parked-design-decisions.md` | investigate (**USER**, not Opus) | design | A03-D001 / A03-D002 / A03-D003 (+ determinism-table governance) | A03 (D001 cross-cuts A01) | parked by user preference 2026-07-05 |
