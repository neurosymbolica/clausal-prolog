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

**Closed 2026-09-25 -- the other way.** The operator ruled "do what Scryer
does" (ISO Prolog; SWI is not a target). Scryer's `listing/1` does not
enumerate arities: `listing(fib)` is
`error(type_error(predicate_indicator, fib), listing/1)`, observed on Scryer.
So a bare atom is now that type_error (it no longer lists `foo/0`), and the
`predicate_rows(module)` helper this todo proposed stays unbuilt -- it has no
consumer. The same change makes a compound (`listing(color(R, H))`) and a
string a `type_error(predicate_indicator, …)`, an unbound argument and an
indicator naming no predicate (or one with no clauses) FAIL, a malformed
operand raise `functor/3`'s error, and `Name//N` list `Name/(N+2)`.
Implementation: `clausal/logic/builtins/io.py` (`_pi_parts`,
`_checked_indicator`, `listing/1`); tests:
`tests/test_listing.py::TestListingFollowsScryersContract`.
