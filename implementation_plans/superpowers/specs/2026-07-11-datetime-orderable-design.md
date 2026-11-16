# Orderable date/datetime — design

**Date:** 2026-07-11
**Status:** Approved (design), pending implementation plan

## Goal

Make `date`, `datetime`, and `time` values orderable in Clausal using the
standard ordering operators (`<`, `>`, `=<`, `>=`), guarantee this with
regression tests, and harden the error path so an *incomparable* ground
comparison surfaces a clean, catchable Clausal error instead of a raw Python
`TypeError`.

## Key finding: ordering already works, and it is clean

Date/datetime/time are **already orderable** with `<`, `>`, `=<`, `>=` today,
verified end-to-end:

```
date(2020,1,1,A), date(2021,1,1,B), A < B                          % succeeds
datetime(2020,1,1,10,0,0,A), datetime(2020,1,1,11,0,0,B), A < B    % succeeds
```

The comparison operators compile to `FDCompare` IR ops, which lower to
`fd_lt` / `fd_le` (`clausal/logic/clpfd.py`). For two **ground** operands,
those functions fall through a generic branch:

```python
if _both_ground(l, r):
    return l < r        # Python-native comparison
```

This is **not** a date-specific overload of CLP(FD): it is the general
ground-comparison semantics of the operator, the identical path that strings
and every other comparable ground value take (`"abc" < "abd"` works the same
way). CLP(FD) constraint machinery only engages when an unbound variable is
present. Therefore ordering dates via the standard operators is clean with
respect to builtin CLP(Z)/FD — nothing touches FD internals.

Sorting already works too: `sort/2`, `msort/2`, `min_list/2`, `max_list/2`
order homogeneous date/datetime lists chronologically (they use Python
`sorted` / `min` / `max`).

Clausal has no `compare/3`, `@<`, `keysort`, or `predsort`; the
`<` / `>` / `=<` / `>=` family **are** Clausal's standard ordering operators.

Consequently, no new ordering machinery is built. The work is: confirm the
behavior with tests, harden the one rough edge, and document it.

## The rough edge

Comparing two ground values that Python cannot compare raises a raw Python
`TypeError`. This affects:

- `date` vs `datetime` — `'<' not supported between instances of 'datetime.date' and 'datetime.datetime'`
- naive vs timezone-aware `datetime` — `can't compare offset-naive and offset-aware datetimes`
- `date` vs `int`, and generically any incomparable ground pair (e.g. `1 < "a"`)

The `TypeError` is currently auto-wrapped into a catchable term
`TypeError("<message>")`, so `catch/3` already catches it — but the term is
opaque and inconsistent with the rest of Clausal's error taxonomy.

This is **pre-existing, generic behavior** — not something dates introduced.
`1 < "a"` behaves identically.

## Part 1 — Harden incomparable comparisons (behavior change)

Convert the raw `TypeError` into a structured, catchable Clausal error term,
**reusing the vocabulary Clausal already uses for this exact situation.**
`min_list/2` and `max_list/2` (`clausal/logic/builtins/lists.py`) already
convert an incomparable-`TypeError` into
`LogicException(type_error("orderable", Culprit, Context))`. The comparison
operators will raise the same shape:

```
error(type_error(orderable, <rhs-operand>), (<)/2)
```

Example: `date(...) < datetime(...)` throws
`error(type_error(orderable, <the datetime value>), (<)/2)`. The culprit is the
right-hand operand (the value that could not be ordered against the left); the
context names the primitive operator. Matching the existing `orderable`
vocabulary means a single handler —
`catch(G, error(type_error(orderable, _), _), R)` — uniformly catches
`min_list`, `max_list`, and the comparison operators. (This refines the
error-term shape agreed during brainstorming, which used the LHS type name as
the expected type; the `orderable` atom is preferred for consistency with the
pre-existing `min_list`/`max_list` behavior.)

`>` and `>=` are implemented as flipped `<` / `=<` (operands swapped), so an
incomparable `A > B` surfaces as `error(type_error(orderable, A), (<)/2)` —
same taxonomy, with the primitive operator/operand order reflecting the
underlying `<`. This is documented and asserted in tests.

### Where

Two implementations must be hardened because the C extension shadows the pure
Python functions when built (`_USE_C_PROPAGATE` is true in this environment):

1. **C path** (`clpfd.py`, the block that does `fd_lt = _c_fd_lt` /
   `fd_le = _c_fd_le`): wrap each in a thin Python function — exactly the
   pattern already used for `fd_eq` there — that catches `TypeError` from the
   C call and, **only when both operands are ground** (guarding against masking
   an unrelated `TypeError`), re-raises the structured error.

2. **Pure-Python fallback** (`fd_lt` / `fd_le` definitions): wrap the
   `_both_ground` `return l < r` / `return l <= r` branches the same way.

`fd_gt` / `fd_ge` delegate to `fd_lt` / `fd_le` (with swapped operands), so
they inherit the hardened behavior transitively and need no separate change.
A shared helper builds the error term from `(l, r, op_context)` after
dereferencing, so both paths stay consistent.

### Scope

This improves **all** incomparable ground comparisons, not only dates — a
deliberate consistency win, accepted during brainstorming. A structured
`type_error` was chosen over silent failure because silently failing a
`date`-vs-`datetime` comparison would hide a near-certain programming mistake,
and throwing matches how `==` already behaves.

### Compatibility

Code that catches the incomparable case with a catch-all
(`catch(G, _, R)`) is unaffected. Code that specifically matched the opaque
`TypeError(Msg)` term for a *comparison* would need to match
`error(type_error(_, _), _)` instead; this is the intended improvement.
`==` / `\=` are unaffected — for ground operands they use Python `==`, which
returns `False` for incomparable types rather than raising.

## Part 2 — Regression tests

New file `tests/test_date_time_ordering.py` (Python level) plus a
`tests/fixtures/date_time_ordering.seam` fixture run through
`load_clausal_module` / `collect_tests` / `run_test` (end-to-end).

Python level (exercises whichever `fd_*` implementation is active — the C
wrapper when built, the pure-Python branch otherwise):

- `fd_lt` / `fd_le` / `fd_gt` / `fd_ge` return the correct bool for `date`,
  `datetime`, and `time` operands, in both directions and at equality.
- `_sort__2` / `_msort__2` / `_min_list__2` / `_max_list__2` return date lists
  in chronological order.
- Incomparable pairs (`date` vs `datetime`, naive vs aware `datetime`,
  `date` vs `int`) raise `LogicException` whose term is
  `error(type_error(orderable, _), (<)/2)` (or `(=<)/2`).
- The legitimate mixed CLP(Q)/CLP(R) `TypeError` is **not** swallowed — it
  still propagates as a plain `TypeError` with its "cannot mix" message.
- The `_incomparable_order_error` helper builds the expected term.

End-to-end fixture:

- All four operators on `date`, `datetime`, `time` (constructed via `date/4`
  etc.), asserting chronological direction and equality.
- `min_list/2` and `max_list/2` on a date list bind the earliest/latest.
- `catch/3` catches the incomparable-comparison error.

Note: the fixture must **not** assert ordering via `Sorted == [V1, V2, …]`
against a literal list of bound variables — list-container structural equality
has a representation quirk unrelated to ordering (integer literals match but
var-bearing literals and `[H|T]` head-patterns do not reliably). Sorted-order
correctness is asserted at the Python level (`_sort__2`/`_msort__2` return
value) and end-to-end via `min_list`/`max_list`, which are proven to work.

## Part 3 — Documentation

- Add an "Ordering" note to the datetime module docstring
  (`clausal/modules/py/datetime.py`) and to `docs/date_time.md`: date/datetime/
  time are orderable via `<` / `>` / `=<` / `>=` and sortable via the standard
  sort predicates; incomparable pairs raise `type_error`.

## Out of scope

- Adding `compare/3`, `@<` / `@>` / `@=<` / `@>=`, `keysort`, or `predsort`.
- Ordering when an operand is an unbound variable (FD-constraint semantics over
  dates) — nonsensical for date values and explicitly excluded.
- Changing the ground-comparison behavior of numeric or string operands beyond
  the error-term hardening above.
