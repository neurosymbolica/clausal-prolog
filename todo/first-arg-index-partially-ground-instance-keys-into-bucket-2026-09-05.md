# First-arg index: a partially-ground term-instance argument keys into a bucket it can't satisfy

Found during P3-2 Task 4 fix round 1 (controller review), while fixing the
CELL half of this exact bug class (`_is_deeply_ground` gating
`_runtime_arg_key`'s cell branch). Reviewer's Important-2 finding; the
controller ruled the `is_term_instance` half OUT of Task 4's scope and
reverted it — this todo is the record for whoever picks it up.

## The bug

`_runtime_arg_key` (`clausal/logic/compiler/arg_index.py`) keys a term
INSTANCE (`is_term_instance(a)`) as `(cls.__name__, len(term_field_names(a)))`
unconditionally — it does not check whether the instance's own fields are
fully ground. Verified directly, on this branch, at the reverted commit:

```python
from clausal.logic.predicate import make_predicate
from clausal.logic.variables import Var
from clausal.logic.compiler.arg_index import _runtime_arg_key

Wrap = make_predicate("Wrap", ["sub"])
_runtime_arg_key(Wrap(sub=Var()))   # -> ('Wrap', 1) -- WRONG, should be _INDEX_VAR
```

## Mechanism (identical to the cell case Task 4 fixed)

The bucket that key routes to embeds each of a matching clause's own
elements as a plain, equality-only `MatchValue` pattern whenever that
clause's corresponding element is a ground literal
(`head_to_match_pattern` recurses into a term-instance argument's fields
with no `== or $unify` hybrid fallback, unlike a TOP-level indexed
argument, which gets exactly that hybrid). A caller passing a term
instance with an UNBOUND field can therefore never match a bucket clause
whose corresponding field is a ground literal — even though the un-indexed
fallback's full `unify()` would happily bind it.

This is the exact same mechanism `_is_deeply_ground` was built to guard
against for CELLS (see `_runtime_arg_key`'s cell branch, guarded by
`_is_deeply_ground(a)`); the class-instance branch shares the bug but was
deliberately left unguarded.

## Why it's parked, not fixed, here

Controller ruling (Task 4 fix round 1, reviewer Important-2):
- It is a PRE-EXISTING bug — verified present before any of Task 4's
  changes (checked directly against unmodified `19c58bb7`), not something
  the cell-indexing work introduced.
- It is not exercised by the red test that forced `_is_deeply_ground` to
  exist in the first place (`tests/test_head_match_imported_compound.py::
  test_indexed_imported_compound_at_second_position_enumerates_all_rows`)
  — that repro is a CELL, post-flip; no `.clausal` module mints a term
  instance any more (R6), so this path is Python-producer-only.
- Fixing it would convert an exactly-O(1) branch into O(term-size) on the
  dispatch hot path, with no compensating capability gained for the work
  Task 4 was scoped to do.

## Where the revert landed

`clausal/logic/compiler/arg_index.py`, the `is_term_instance` branch near
the end of `_runtime_arg_key` — reverted from:

```python
    if is_term_instance(a):
        cls = type(a)
        if _is_deeply_ground(a):
            return (cls.__name__, len(term_field_names(a)))
        return _INDEX_VAR
```

back to the unconditional:

```python
    if is_term_instance(a):
        cls = type(a)
        return (cls.__name__, len(term_field_names(a)))
```

`_is_deeply_ground` itself (and its budgeted, complete walk over
tuple/list/Compound/DictTerm/KWTerm/SetTerm/SegList/term-instance shapes)
stays — it is still used, and needed, by the cell branch just above.

The dropped test coverage: the third assertion in each of
`tests/test_first_arg_index.py::TestCellIndexKey::test_a_cell_with_an_unbound_slot_is_unindexable`
and `::test_a_fully_ground_cell_still_keys_normally` (the `Wrap`-instance
assertions) — removed rather than inverted, per the controller's
instruction, with a comment at each site pointing here.

## Follow-up, for whoever picks this up

Reusing `_is_deeply_ground(a)` to gate this branch (mirroring the cell
fix exactly) is the straightforward repair — the budgeted walk already
handles `is_term_instance` values recursively. Before doing that,
measure whether this branch is actually reachable from any current
Python producer's hot path (the class-instance construction routes
listed in project memory: `clausal.reflection`, `clausal.logic.clpb`,
`make_predicate` callers) with an argument large/deep enough for the
O(term-size) cost to matter, since the controller's ruling weighed "no
compensating capability" against "hot path cost" for THIS repo's actual
usage, not in the abstract.
