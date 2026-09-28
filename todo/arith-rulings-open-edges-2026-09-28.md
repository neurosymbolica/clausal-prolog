# Arithmetic rulings of 2026-09-28: open edges

**Status: OPEN. Found while implementing Q1-Q4 (branch
feat/arith-scryer-rulings-2026-09-28). Nothing here changes an answer the
rulings decided; each item is a place the implementation had to pick a
reading.**

## Needs an operator ruling

1. **Zero divisor inside a CLP(FD) constraint.** Implemented reading: a
   GROUND expression with a zero divisor RAISES at the post
   (`X == 1 // 0` is `evaluation_error(zero_divisor)`; the brief said
   "everywhere ... the CLP paths if reachable", and before the branch it
   SUCCEEDED silently with X unconstrained). A divisor that becomes 0 while
   PROPAGATING (labelling) makes the expression's domain empty, so the
   constraint FAILS and the search goes on -- Scryer's clpz behaviour:

       ?- X #= 10 // Y, Y in 0..2, label([Y]).   % Y = 1 ; Y = 2 (both)

   Scryer FAILS the ground post too (`X #= 1 // 0` is `false`), so the ground
   raise is the one place the engine is louder than Scryer: ruling wanted.
   **Known gap:** the C-accelerated `!=` propagator
   (`clausal/logic/_clpfd_propagate.c`, the both-ground arm of the Ne
   propagator) calls `_eval_ground` directly, so `10 // Y != 3` still RAISES
   when labelling reaches Y = 0. Fixing it is a C change (call
   `_eval_propagating`, or treat the zero-divisor error as failure there);
   pinned as a strict xfail in tests/test_arith_operator_rulings.py.
   Reified comparisons (`reify_fd` -> `_resolve` -> `_eval_ground`) also
   still raise when their divisor becomes 0 while labelling.

2. **Seam `/` over integers.** "Operators in seam follow Python semantics
   unless quoted": Python's `7 / 2` is the float 3.5, the engine's (bare or
   quoted) is the exact rational 7/2 (RULED 2026-09-17, "arithmetic IS
   RATIONAL"). The branch keeps 7/2; the docs table says so.

## Deliberate deviations from Scryer (pinned as DEVIATIONS rows)

3. Evaluation-error culprits name the OPERATOR everywhere: `div(1, 0)` names
   `(div)/2` (Scryer: `(mod)/2`, how its div is implemented); `'**'(0, -1)`,
   `'^'(0, -1)`, `'^'(0.0, -1)` name `(**)/2`/`(^)/2` (Scryer: the caller,
   `(is)/2`).
4. `'^'` over an exact rational base stays exact: `'^'(1/2, 2)` is 1/4
   (Scryer: 0.25).

## Known gaps, not decided by the rulings

4b. A GROUND `'**'` cell in a comparison folds to its float before the
    CLP(Q)/CLP(R) dispatch (`X == '**'(2, 3)` is 8.0); Scryer's clpz raises
    `domain_error(clpz_expression, 2**3)` for `X #= 2**3`. Over a CLP(FD)
    variable (`X == '**'(Y, 2)`) the engine raises that error, as Scryer.

5. The `'//'` cell, rewritten into a node for a CLP post, is `IsoIntDiv`, a
   `FloorDiv` subclass; CLP(FD) evaluates it by its own entry (truncating),
   but CLP(R) interval propagation (`clpr._ifloordiv`), CLP(Z3) and
   clportools match `isinstance(x, FloorDiv)` and FLOOR it. Only a negative
   operand with a quoted `'//'` inside those solvers can differ.
6. A bare `**` in a CLP(FD) post is Python's integer power and posts
   (`X == Y ** 2`); Scryer's clpz rejects `**` (`domain_error`). By the
   rulings a bare operator is Python's, so this stands; the quoted `'**'`
   raises `domain_error(clpz_expression, T)` like Scryer.
7. Ground-vs-ground CLP rows are unchanged: `'#='(1, foo)` still FAILS and
   `'#<'(1, foo)` still raises `type_error(orderable, foo)`, where Scryer
   raises `domain_error(clpz_expression, foo)` for both (see
   tests/iso/test_iso_compare_errors.py::test_hash_family_error_surface_OPEN_iso_divergence).
   Q3 changed the variable-side rows only.
8. `'//'`, `div`, `mod` take integers only, as Scryer: a Decimal or Fraction
   operand is `type_error(integer, X)`. A bare `//`/`%` over a Decimal is
   Python's `Decimal` operator, which TRUNCATES `//` and gives `%` the sign of
   the dividend (`Decimal(-7) // 2` is -3) -- Python's meaning, as ruled, but
   unlike `-7 // 2` over ints.
9. `^` in a clause body is Python's XOR node (CLP(B) uses it: `sat(X ^ Y)`),
   so the integer power has only the quoted spelling `'^'(A, B)` today; the
   future Clausal Prolog syntax will give bare `^` its ISO meaning.
10. The `.pl` importer still routes Prolog `//` to `prolog.TruncDiv`; it could
    now emit the `'//'` cell instead.
