# clause/2 refuses a `.pl` dynamic clause whose body calls a user predicate

**Status: OPEN. Pre-existing. It reproduces cut-free on canonical main 64551448. It was found while writing the Task 5 (D59, cut in `.pl`) tests, 2026-10-14.**

## What happens

    p(1). p(2).
    :- dynamic(d/1).
    d(X) :- p(X), q.
    q.
    m(B) :- clause(d(_), B).

`m(B)` raises:

    error(permission_error(access, private_procedure, d/1), clause/2):
      d/1 has a clause whose body has no term form -- its body cannot be
      built as a term (... existence_error(procedure, p/1): Predicate 'p/1'
      is not in scope: nothing declares the functor p/1, so p(...) builds
      no term ...)

Scryer answers `B = (p(_), q)`. ISO 8.8.1 lets clause/2 inspect a dynamic procedure.

The same goes for `retract((d(_) :- p(_), q))` and for any body goal that names a predicate the module defines rather than a builtin. Bodies made only of builtins (`X = 1, X > 0`, `member/2`) build fine.

## Where

Body term construction (`clause_ops.clause_terms` → `_spell_as_cells` / `_needs_cell` → term construction). In a `.pl` module, a call to a predicate the module defines has no declared functor, so building the term `p(X)` is refused.

## Notes

- This is not the thunk case (`todo/clause-2-carry-the-thunk-in-the-body-term-2026-09-25.md`).
- `tests/iso_l3/test_l3_cut_meta.py` (CLAUSE_SRC, ITE_CLAUSE_SRC) works around it with builtin-only bodies. When this is fixed, add a row there with `d(X) :- p(X), !.`
