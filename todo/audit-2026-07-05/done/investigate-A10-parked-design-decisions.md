# investigate(A10) [Opus]: parked design decisions — rewriting/templating/import

**Status: FIXED 2026-08-25 (commits 956672fe, 4555be9a, a4269463, eb566ffb).** All four parked A10 decisions were taken as recommended and shipped: embedded-Python names are Python names, stdlib shadowing warns and defers, an imported-head clause is a load-time error, and TermExpansion q(head) patterns match item.head. Pinned in tests/audit_2026_07_05/test_10_rewriting_import.py.

Per the standing user preference, these were parked rather than asked
interactively. Full option analyses in
`docs/superpowers/audits/2026-07-05-fable-partition/10-rewriting-import/design-questions.md`.

- **A10-D001 — are logic-var-shaped names reserved in embedded Python?**
  Recommendation: no — skip Store/Del in `EmbedTransformer.visit_Name`
  (fix-A10-embed-visitname-store-context.md) and keep Load-unboxing.
- **A10-D002 — stdlib shadowing by extension finders.** Recommendation:
  warn on `sys.stdlib_module_names` hits + fix import.md
  (fix-A10-stdlib-shadowing-docs-guard.md).
- **A10-D003 — semantics of a clause head naming an imported predicate.**
  **ANSWERED 2026-08-25 as recommended: load-time error**; explicit assertz
  stays the mutation path (and already refused — `permission_error`). Shipped
  on `fix/imported-functor-clause-list-2026-08-25`; the refusal is narrowed to
  functors that already have clauses, so declare-here/implement-there still
  works. See `done/investigate-A10-imported-head-clobber.md` and
  `todo/done/imported-functor-clause-list-replaced-not-extended.md`.
- **A10-D004 — TermExpansion pattern vocabulary (q(head) vs Predicate
  items).** Recommendation: match bare-term patterns against `item.head` now,
  docs fix immediately; reflection-vocabulary reification is the long-term
  answer but is blocked on A03-D001/A01-D004 (Compound↔instance unification).
