# W4b-3 slice 7: `_DatePattern` is deleted, not replaced (2026-09-26)

## The choice

`clausal/modules/py/datetime.py` defined `_DatePattern`, a
`metaclass=PredicateMeta` class with fields `(year, month, day)`, a hand-rolled
`__unify__` bridging a pattern to a real `datetime.date`, and an
`_index_transparent` flag read by `arg_index`. Slice 7 deletes the
`PredicateMeta` class, so `_DatePattern` had to go or be replaced.

The operator ruled that a date should keep behaving as it does now (no
redesign), and that the replacement is ours to pick. The replacement is
**deletion**: nothing reaches `_DatePattern` any more. `date/3` already builds
a cell `("date", Y, M, D)` in every mode, ground or partial, and the cell
unifies natively.

## Measured, not read off the docstring

A pytest plugin instrumented `_DatePattern` across the full suite (18,459
passed): construction (`PredicateMeta.__call__` with it as `cls`), its
`__unify__`, `isinstance(_, _DatePattern)` (the metaclass `__instancecheck__`),
and every attribute read on the class (`_index_transparent` included).

| reach | count |
|---|---|
| constructed | 0 |
| `__unify__` called | 0 |
| `isinstance` tested | 0 |
| attribute read | 0 |

Positive control: the same plugin in a script that touches the class once
each way counted `isinstance: 1, construct: 1, attr:_fields: 3`, so a zero is
a real zero.

`arg_index`'s `_index_transparent` hook is a generic protocol
(`getattr(type(arg), "_index_transparent", False)`). No in-tree type sets it
now. It stayed in 7a; review 188 had it removed in the slice 7 review-fix
commit (both branches, the compile-time key and the runtime key), since
nothing can reach them.

A raw Python `datetime.date` is not a term, before 7a and after: a pattern
cell does not unify with one, and a goal holding one is refused ("a Python
date is not a term"). What `_DatePattern.__unify__` described never
happened on 3a8697c2 either, because nothing built a `_DatePattern`.
`tests/test_date_term.py::TestARawPythonDateIsNotATerm` pins this.

## Answers are identical

"Before" is 3a8697c2 (a detached worktree built at that sha); "after" is the
slice 7 tree. Variable numbering is normalised in each diff.

* A date answer battery run on both trees (construct, decompose, partial
  pattern binding, a partial pattern grounded later, an impossible date's
  `domain_error`, `msort`, `compare`, `date_between`, `days_between`, the
  `ground(V), date(_, _, _) is V` test on an unbound value, a list triple and
  a date term, and Python `date`/`datetime` values handed in): 18 lines, no
  difference.
* The in-repo `.clausal` modules that import `date_time`
  (`tests/fixtures/date_time_ordering.clausal`,
  `tests/fixtures/docs/builtins_sig_tests.clausal`,
  `tests/fixtures/docs/date_time_sig_tests.clausal`), run with
  `clausal.testing`: 9, 125 and 22 tests, identical output.
* The date pytest files (`test_date_term`, `test_date_time`,
  `test_date_query_args`, `test_date_time_ordering`,
  `test_py_interop_type_notes`): the same 189 tests pass before and after.
  After also has 4 new tests.
* An out-of-tree consumer that uses `date(_, _, _) is V` behind a `ground`
  guard and `DAY is date(Y, M, D)`: its own suite gave identical output
  before and after (the same 36 results, including 4 failures unrelated to
  dates that already failed before).

The new in-repo tests (`tests/test_date_term.py::TestDateTermShapesInAModule`)
are a synthetic equivalent of the shapes such a consumer relies on. They
cover construct, decompose of a date term, the `ground` guard refusing an
unbound value (and a `[Y, M, D]` list), and the unguarded form binding an
unbound value to a pattern.
