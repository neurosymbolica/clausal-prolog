# investigate(A10) [Opus]: parked design decisions — rewriting/templating/import

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
  Recommendation: load-time error; explicit assertz stays the mutation path.
  Joint with A11 module semantics + A03 compile_module sync
  (investigate-A10-imported-head-clobber.md).
- **A10-D004 — TermExpansion pattern vocabulary (q(head) vs Predicate
  items).** Recommendation: match bare-term patterns against `item.head` now,
  docs fix immediately; reflection-vocabulary reification is the long-term
  answer but is blocked on A03-D001/A01-D004 (Compound↔instance unification).
