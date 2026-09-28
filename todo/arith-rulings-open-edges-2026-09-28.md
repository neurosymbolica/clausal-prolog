# Arithmetic rulings of 2026-09-28: open edges

**Status: OPEN. Found while implementing Q1-Q4 (branch
feat/arith-scryer-rulings-2026-09-28). Nothing here changes an answer the
rulings decided; each item is a place the implementation had to pick a
reading.**

## Rulings

1. **Zero divisor inside a CLP(FD) constraint -- RULED Q14 2026-09-28,
   DONE.** A constraint over an expression with no value FAILS, as in
   Scryer, in every goal order ("(#=)/2 is a relation: failure means that
   there are no solutions for these arguments" -- Markus Triska); plain
   arithmetic (is/2, the ISO comparisons, eval_/2) keeps raising
   `evaluation_error(zero_divisor)`. Implemented with no C change: the ground
   post fails (`fd_eq`/`fd_ne`/`fd_lt`/`fd_le` wrapped), propagation empties
   the domain (`_expr_domain`) or fails the Python `!=` arm, the C `!=`
   propagator is handed `clpfd._eval_ground_for_c` (a no-value sentinel that
   differs from nothing), and a reified test (`reify_fd`) is false. The
   goal-order dependence roborev job 288 found is gone.

2. **`/` -- RULED Q15 2026-09-28, DONE.** In EVALUATION (is/2, eval_/2, the
   ISO comparisons, compiled eval_) a bare `/` is Python's true division
   (`7 / 2` is 3.5, `6 / 2` is 3.0; a Fraction over an int stays a Fraction,
   a Decimal over an int is Python's Decimal quotient) and the quoted `'/'`
   Scryer's (always a float). `rdiv/2` is now IN the evaluable table as the
   exact spelling (`rdiv(6, 2)` is 3, `rdiv(7, 2.0)` is 7/2 as in Scryer).
   Inside CLP posts `/` stays rational (`X == 7 / 2` is 7/2). Kept engine
   rules where Python has no single answer: a Decimal beside a Fraction
   divides exactly (Python raises TypeError); a float beside a Fraction or a
   Decimal raises type_error(exact_number) (Q5 of 2026-09-17; Python would
   give a float / raise). is/2 and the ISO comparisons now evaluate through
   `exact_arith.evaluate` (as eval_ does), not the CLP evaluator.
   Still open: between/3 evaluates its bounds with the CLP evaluator, so
   `between(1, 6 / 2, X)` keeps the rational reading (3) where evaluation
   would give 3.0.

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
   operand with a quoted `'//'` inside those solvers can differ. CLP(Q) too:
   `_is_rational_arg` sends a `'//'` over a CLP(Q) variable there, and its
   linearisers match the `FloorDiv` base class.
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
10. **The `.pl` importer (experimental, ruling Q9) maps Prolog `**` and `^`
    onto the BARE `**`**, which is now Python's power: an imported
    `X is 2 ** 3` answers the integer 8 (Scryer: 8.0) and `2 ^ -1` answers
    0.5 (Scryer: `type_error(float, 2)`); `div` maps onto the bare `//`
    (floor, numerically ISO div). It should emit the quoted cells (`'**'`,
    `'^'`, `div`, and `'//'` in place of `prolog.TruncDiv`). Q16 (2026-09-28)
    unblocked it: the quoted cells need no declaration now. NOT done on this
    branch: the change rewrites the importer's expression emitter and its
    golden snapshots (tests/fixtures/prolog_golden), so it is its own step.
