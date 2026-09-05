# `listing(foo)` lists only `foo/0`; ISO/SWI list every arity of `foo`

**Filed:** 2026-09-06 at P3-3 Task 8 (listing/1 migrated to `db.row(name, arity)`), reviewer F7.

`listing/1` now accepts a bare atom and resolves it as `db.row(name, 0)`. When
`foo/0` does not exist but `foo/1` does, the user gets
`existence_error(procedure, foo/0)` — correct under the Task 8 ruling
("str atom → name/0"), but SWI-Prolog and the ISO spirit of `listing/1` treat a
bare atom as "every predicate with this name, any arity".

**To close.** Give `listing/1`'s atom arm an enumeration: all rows in the
calling module's db whose functor == name, in arity order, each printed with
the existing header/clause format; existence_error only when NONE exists.
This is the first genuine consumer for the `predicate_rows(module)` helper
the P3-3 plan sketched for database.py (`Iterable[(name, arity, PredRow)]`)
and Task 8 declined to add for lack of a consumer — add it then, not before.
Byte-identity of the single-arity output must hold (a golden exists in
tests/test_listing.py).

Cost of leaving it: a confusing error for the common `listing(foo)` habit.
