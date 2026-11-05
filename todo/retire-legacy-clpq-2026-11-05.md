# Retire the legacy CLP(Q) solver

**Date:** 2026-11-05. **Operator ruling 2026-11-05:** "we should retire
legacy CLPQ".

## State

`CLAUSAL_CLPQ` selects the solver (`clausal/logic/clpq/__init__.py`):
`legacy` (the default, the solver from before 2026-10-12) or `holzbaur`
(the port of clp(q,r) 1.3.3, see `clausal/logic/clpq/PROVENANCE.md`).
Both solvers' attribute hooks are registered whichever is selected
(ruling R1). The full suite is gated under both.

## Plan

1. Make `holzbaur` the default. Gate it, and have the corpus and harness
   re-checked, since every CLP(Q) answer can change wording or order.
2. Remove `legacy.py` and the code only it uses, the `legacy` value of
   `CLAUSAL_CLPQ` (a named error for it, not a silent fallback), the legacy
   attribute hooks, and the tests and fixtures that pin legacy-only
   behaviour.
3. Close or reject the legacy-only todos (`legacy-clpq-*`) as the code they
   describe goes.
4. Check what still imports legacy-only private names (`__init__.py`
   re-exports them for Q_KEY users, the tests and the CLI), and CLP(R).
5. Update `docs/` and the CHANGELOG.
