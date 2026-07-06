# investigate(A08, Opus): parked design decisions from the CLP(Q/R)/Z3/ortools audit

Session A08 ran non-interactively; per the audit override these design
questions were parked instead of asked. Full statements with options and
recommendations: `docs/superpowers/audits/2026-07-05-fable-partition/08-clpqr-z3/design-questions.md`.

| ID | One-liner | Recommendation | Blocking |
|----|-----------|----------------|----------|
| A08-D001 | `//`/`%` semantics in Z3 & CP-SAT adapters: Python floor-div/mod vs backend-native (Euclidean / truncated) | Translate faithfully to Python semantics | fix-A08-z3-floordiv-mod-translation.md, fix-A08-ortools-floordiv-mod-translation.md |
| A08-D002 | Should Z3_KEY/OR_KEY/LP_KEY register attr hooks so Clausal bindings reach the backend store? | Yes — post `const == value` on unification; watch A04-D001 hook semidet limits | investigate-A08-solver-store-sync-hooks.md |
| A08-D003 | Float literals reaching CLP(Q): TypeError (docs), decimal conversion, or silent binary-exact Fraction (current)? | TypeError per docs | fix-A08-clpq-float-mixing-enforcement.md |
| A08-D004 | CLP(Q) strict inequalities: Holzbaur epsilon-rationals vs passive diseq (current, unsound) | Epsilon-rationals, staged with the F002 bound rework; interim aliasing fixes first | investigate-A08-clpq-strict-inequalities.md |
| A08-D005 | Optimization contracts: FEASIBLE-as-optimal (CP-SAT), non-attained suprema (Z3 `opt.upper`), objective permanently installed on shared CpModel, maximize_z3 not binding vars | Unify on clpq.maximize's contract (bind vars, proven optimum only) for the mirror-named predicates | (doc/design only — A08-F018) |

Do not resolve these piecemeal inside unrelated fixes; each fix todo above
notes which decision it is pending on.
