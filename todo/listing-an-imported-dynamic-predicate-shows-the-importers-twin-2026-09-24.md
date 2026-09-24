# listing/1 of an imported predicate the importer re-declared -dynamic shows the importer's empty twin

**Found:** 2026-09-24, testing F1 rows 58/59. **Pre-existing, class era too.** Owner: F1 row 60.

`io._indicator_row(db, name, arity, pred_cls)` asks `db.row(name, arity)`
(leg 2) BEFORE `_find_pred_cls`/`_home_db` (leg 3). A module that imports a
predicate and re-declares it `-dynamic` (`tests/fixtures/gate_dyn_user.clausal`
imports `gd_p` and declares `-dynamic(gd_p/1)`) holds a LOCAL row under the
same key -- `Database.row()` prefers it over the adopted one -- so leg 2 returns
the importer's empty twin. Measured today (class binding, owner loaded):
`_indicator_row(user_db, "gd_p", 1, None)` is the twin with 0 clauses while
the owner's row holds the asserted clauses.

Fix shape: resolve through the binding (`_find_pred_cls` + `_home_db`) before
the bare `db.row` leg, or skip a local row that has no clauses and no source
when an adopted row exists (`Database.adopted_row`). Test with
`tests/test_find_pred_binding_both_eras.py`'s `pair` fixture, both eras.
