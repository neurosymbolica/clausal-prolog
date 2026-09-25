# clausal-provenance: redesign, probably as a meta-interpreter (DISABLED meanwhile)

**Operator, 2026-09-25:** "for provenance, we might have to use a metainterpreter. Anything class-based can't map to ISO Prolog. Disable provenance for now, it will need a redesign."

## Why it was disabled
- The package registers predicates for bottom-up evaluation by putting flags on the predicate's CLASS: `bottom_up_(P)` and `pure_(P)`, and `is_bottom_up(cls)`.
- After the W4b-2d flip (e107929e), a binding is a handle (str) and a predicate is a Database row, so there is no class to carry a flag. W4b-3 deletes PredicateMeta outright.
- A migration that keeps the design was done on branch `fix/provenance-off-predicatemeta-2026-09-25` (3490374c, kept for reference, NOT landed):
  - flags move into the module namespace (`$provenance_flags`);
  - `is_bottom_up`/`is_pure` take `(functor, module)`.
  - It passes 138/140 of the package's own tests, and its answer A/B is identical to main.
  - The operator judged the design itself wrong for ISO.

## Redesign direction (to be designed; not ruled)
- A meta-interpreter over ISO `clause/2`, which has been on main since 4b5fae49 and round-trips `clause(H, B), call(B)`. It would carry a semiring tag through resolution, instead of registering classes.
- Things the redesign must answer: how facts arrive (the old `solve/4`), stratified negation / aggregation, the semiring interface (torch/jax tensors), and performance vs the old semi-naive bottom-up engine.
- The old branch also found an engine question to settle: a predicate exported by `-module(m, [edge(A, B)])` with NO clauses is treated as DATA (bound as the plain atom). Should a declared procedure stay a procedure (ISO)?

## What "disabled" means now
- `clausal.modules.provenance` raises ImportError on import, loudly.
- Its tests are not collected (`packages/clausal-provenance/tests/conftest.py`).
- It is removed from `tools/w3_package_gate.sh`.
- `docs/packages.md` and the package README carry a banner.
