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
