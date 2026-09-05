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

## Update, fix round 2 (2026-09-05)

The BUCKET-SIDE half of this hazard (a bucket ARM whose lifted pattern
carries a literal sub-value, which is what actually makes a
partially-ground caller's key dangerous to trust) is now covered
uniformly for BOTH cells and term instances by
`list_dispatch._lifted_head_arg_needs_deep_gate` (fix round 2's
compile-time flag computation) -- see
`tests/test_first_arg_index.py::TestDeepGateFlagComputation::
test_term_instance_ground_field_needs_the_gate` and
`::TestDeepGateWiredThroughCompiler::
test_lifted_literal_instance_position_flags_on`. That flag decides
whether `_runtime_arg_key`'s bounded walk runs AT ALL for a given
predicate/position, for whichever key branch (cell OR
`is_term_instance`) reaches it.

What is still open, exactly as filed above: the KEY-SIDE
`is_term_instance` branch in `_runtime_arg_key` (arg_index.py, near the
end of the function) is UNCONDITIONAL -- it does not consult the flag at
all, because it was reverted to its pre-round-1 shape rather than
threaded. So a partially-ground term-INSTANCE caller still keys into a
bucket without any check today; the flag machinery that WOULD gate it
correctly (mirroring the cell branch exactly) exists and is tested, it
is just not wired to this one key-side branch. That wiring -- add
`deep_gate` to the `is_term_instance` branch's `return`, exactly
parallel to the cell branch a few lines above it -- is the two-line
follow-up this todo already named.

## Resolution (2026-09-05, P3-3 Task 4)

Done, as the two-line follow-up this todo named. `_runtime_arg_key`'s
`is_term_instance` branch (`clausal/logic/compiler/arg_index.py`) now carries
the same `deep_gate and not _is_deeply_ground(a)` condition the cell branch a
few lines above it carries, so a partially-ground term INSTANCE keys
`_INDEX_VAR` and reaches the un-indexed fallback's full `unify()` instead of a
bucket whose arms it can never satisfy.

The gate is the compile-time flag, not an unconditional walk: the O(term-size)
cost the controller weighed against this fix at P3-2 fix round 1 is paid only
for a predicate/position whose lifted arms actually carry a literal sub-value
(`list_dispatch._lifted_head_arg_needs_deep_gate`, which already computed the
flag for term instances — see this file's "Update, fix round 2" above). A
position that needs no gate passes `deep_gate=False` and keeps the exactly-O(1)
key, which is why the "no compensating capability for hot-path cost" objection
no longer applies.

The dropped coverage this todo recorded is restored, with the repro as the
test: the third assertion in each of
`tests/test_first_arg_index.py::TestCellIndexKey::
test_a_cell_with_an_unbound_slot_is_unindexable` (the `Wrap(sub=Var())` →
`_INDEX_VAR` repro, verbatim from "The bug" above) and
`::test_a_fully_ground_cell_still_keys_normally` (`Wrap(sub="direct")` still
keys `("Wrap", 1)`, plus `deep_gate=False` keeping the O(1) key). The P3-2
driven-bucket tests are untouched and green; the 4-tuple plan shape
`(pos, idx_dict, default_fn, deep_gate)` is unchanged.
