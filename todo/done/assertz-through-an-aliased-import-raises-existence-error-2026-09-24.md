# assertz through an aliased -import_from raises existence_error

**Found:** 2026-09-24, F1 row 60 roborev round. **Pre-existing** (reproduced on
main c68d6552, class era, owner loaded; with and without the importer
re-declaring the alias `-dynamic`).

`tests/fixtures/row60_alias_user.clausal` imports
`alias(gd_p, gd_loc)` from `gate_dyn_owner` and defines
`gd_loc_add(X) <- assertz(gd_loc(X))`.  Calling `gd_loc_add(42)` raises

    existence_error(procedure, gd_p/1)  -- "assertz/1: no predicate gd_p/1 is
    known here, and a cell argument does not create one ..."

The body's `gd_loc(X)` compiles to a `gd_p` cell (clause heads/cells take the
owner's name), and the assert then looks `gd_p/1` up in the IMPORTER's
namespace/database, where only `gd_loc` is bound and adopted.  The write
should land on the owner's row, as the non-aliased `gate_dyn_user` case does
(rows 58/59).

Likely shape: the assert target resolution (`database_ops` `_find_pred_cls`
/ `_home_db`) needs the importer's spelling for an aliased cell, or the cell
should keep the local spelling.  Needs checking against ruling D1 in both
eras.  `tests/test_listing_indicator_both_eras.py::test_an_aliased_import_lists_the_owner`
primes through the owner's module to avoid this.

## Resolved (2026-09-24, branch fix/small-todos-batch-2026-09-24)

Kept the cell's OWNER spelling (it is deliberate: `terms_to_ast._functor_spelling`,
"matching the alias's local spelling would build a term the owner's clauses
can never match") and added the reverse step on the write side:

* `Database.adopted_spelling(functor, arity)` -- the importer's spelling under
  which this db adopted a row whose OWN key is `(functor, arity)`; `None` when
  none, or when DISTINCT rows qualify (two owners' same-named predicates
  aliased apart -- the cell cannot say which).
* `database_ops._find_pred_cls`: when the cell's name is bound to NOTHING here,
  resolve through that local spelling (a local `gd_p` keeps its own meaning).
* `database_ops._adopted_row_named_by`: the same reverse step for the popped-
  owner handle route (flipped era, owner out of `sys.modules`).

Every consumer of `_find_pred_cls` benefits: `assertz`, `asserta`, `retract`,
and `call/1` (`higher_order`) -- which, for `call(gd_loc(X))`, used to answer
NOTHING silently, not even an error.

Tests: `tests/test_assert_through_aliased_import_both_eras.py` -- assertz,
retract, call/1 x (class | `mint_predicate_handle` handle) x (owner loaded |
popped), plus an unrelated cell still refused and the two-owner ambiguity.
Mutations: dropping the `_find_pred_cls` leg fails all 12 era cases; dropping
the `_adopted_row_named_by` leg fails exactly the 3 flipped-popped ones.
