# Orderable date/datetime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Guarantee date/datetime/time are orderable via `<`/`>`/`<=`/`>=` (already true) with regression tests and docs, and convert the raw Python `TypeError` from an incomparable ground comparison into a catchable `error(type_error(orderable, _), _)`.

**Architecture:** No new ordering machinery — the operators already order ground dates through the generic `_both_ground → l < r` fallback in `fd_lt`/`fd_le`. The only code change hardens the incomparable-comparison error path in two places (the C-accelerated wrapper and the pure-Python fallback), reusing the `type_error(orderable, …)` vocabulary that `min_list/2`/`max_list/2` already use. The rest is tests and documentation.

**Tech Stack:** Python 3.13, pytest, Clausal logic runtime; C extension `_clpfd_propagate` (active in this environment, so `fd_lt`/`fd_le` resolve to the C impls unless wrapped).

## Global Constraints

- Run everything with the clone's interpreter and PYTHONPATH:
  `PYTHONPATH=/workspace/clausal-bug-fix /home/node/.pyenv/versions/3.13.3/bin/python` (the shared venv lacks pytest and may shadow the clone).
- No C source (`clausal/logic/*.c`) changes in this plan — only Python wrappers — so **no `build_ext` rebuild is required**.
- Clausal uses Python comparison tokens in source: `<`, `>`, `<=`, `>=` (NOT Prolog `=<`).
- Error terms use `clausal.logic.exceptions.type_error(expected, culprit, context)` → `Compound("error", (Compound("type_error", (expected, culprit)), context))`, carried by `LogicException`.
- `Compound` exposes `.functor` and `.args`.

---

### Task 1: Structured `type_error` for incomparable comparisons

**Files:**
- Modify: `clausal/logic/clpfd.py` — add `_incomparable_order_error` helper (before `fd_eq`, ~line 1607); harden the `_both_ground` branch of `fd_lt` (~line 1723) and `fd_le` (~line 1752); replace `fd_lt = _c_fd_lt` / `fd_le = _c_fd_le` in the `if _USE_C_PROPAGATE:` block (~lines 2932-2933) with wrapper functions.
- Create: `tests/test_date_time_ordering.py`

**Interfaces:**
- Consumes: `clausal.logic.clpfd.deref`, `is_var`, `_any_rational`, `_any_real` (all already module-level in `clpfd.py`); `clausal.logic.exceptions.LogicException`, `type_error`.
- Produces: module-level `clpfd.fd_lt`, `fd_le`, `fd_gt`, `fd_ge` (unchanged signatures `(l, r, trail) -> bool`) that raise `LogicException(error(type_error(orderable, <culprit>), <context>))` for incomparable ground operands; helper `_incomparable_order_error(culprit, context) -> LogicException`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_date_time_ordering.py`:

```python
"""Ordering of date/datetime/time via the comparison operators and the
sort/collection predicates, plus the incomparable-comparison error path.

date/datetime/time are real Python objects; the comparison operators reach
clpfd.fd_lt/fd_le/fd_gt/fd_ge, which order any comparable ground values.
"""

from __future__ import annotations

import datetime as dt
from fractions import Fraction

import pytest

from clausal.logic.variables import Var, Trail, deref
from clausal.logic.clpfd import (
    fd_lt, fd_le, fd_gt, fd_ge, _incomparable_order_error,
)
from clausal.logic.builtins.lists import (
    _sort__2, _msort__2, _min_list__2, _max_list__2,
)
from clausal.logic.exceptions import LogicException
from clausal.logic.trampoline import DONE


# ── Helpers ──────────────────────────────────────────────────────────────

def _run_list_builtin(fn, in_list):
    """Drive a (this_generator, _proceed, _fail, _catcher, lst, out, trail)
    list builtin; return one dereferenced output list per solution."""
    trail = Trail()
    out = Var()
    results = []
    for _cont, val in fn(None, "proceed", "fail", None, in_list, out, trail):
        if val is DONE:
            break
        results.append([deref(x) for x in deref(out)])
    return results


def _assert_orderable_error(exc_info, context):
    term = exc_info.value.term
    assert term.functor == "error"
    inner = term.args[0]
    assert inner.functor == "type_error"
    assert inner.args[0] == "orderable"
    assert term.args[1] == context


# ── Comparison operators order dates/datetimes/times ─────────────────────

class TestComparisonOperators:
    def test_date_lt(self):
        assert fd_lt(dt.date(2020, 1, 1), dt.date(2021, 1, 1), Trail()) is True
        assert fd_lt(dt.date(2021, 1, 1), dt.date(2020, 1, 1), Trail()) is False

    def test_date_le_equal(self):
        assert fd_le(dt.date(2021, 1, 1), dt.date(2021, 1, 1), Trail()) is True
        assert fd_lt(dt.date(2021, 1, 1), dt.date(2021, 1, 1), Trail()) is False

    def test_date_gt_ge(self):
        assert fd_gt(dt.date(2022, 1, 1), dt.date(2021, 1, 1), Trail()) is True
        assert fd_ge(dt.date(2021, 1, 1), dt.date(2021, 1, 1), Trail()) is True

    def test_datetime_lt(self):
        a = dt.datetime(2020, 1, 1, 10, 0, 0)
        b = dt.datetime(2020, 1, 1, 11, 0, 0)
        assert fd_lt(a, b, Trail()) is True

    def test_time_lt(self):
        assert fd_lt(dt.time(9, 0, 0), dt.time(17, 0, 0), Trail()) is True


# ── Sort / collection predicates order dates ─────────────────────────────

class TestCollectionOrdering:
    def test_msort_orders_dates(self):
        a, b, c = dt.date(2021, 1, 1), dt.date(2019, 5, 5), dt.date(2020, 3, 3)
        assert _run_list_builtin(_msort__2, [a, b, c]) == [[b, c, a]]

    def test_sort_dedups_and_orders_dates(self):
        a, b, a2 = dt.date(2021, 1, 1), dt.date(2019, 5, 5), dt.date(2021, 1, 1)
        assert _run_list_builtin(_sort__2, [a, b, a2]) == [[b, a]]

    def test_min_list_dates(self):
        a, b = dt.date(2021, 1, 1), dt.date(2019, 5, 5)
        assert _run_list_builtin(_min_list__2, [a, b]) == [[b]]

    def test_max_list_dates(self):
        a, b = dt.date(2021, 1, 1), dt.date(2019, 5, 5)
        assert _run_list_builtin(_max_list__2, [a, b]) == [[a]]


# ── Incomparable comparisons raise a catchable type_error ────────────────

class TestIncomparableRaises:
    def test_date_vs_datetime(self):
        with pytest.raises(LogicException) as ei:
            fd_lt(dt.date(2020, 1, 1), dt.datetime(2020, 1, 1, 0, 0, 0), Trail())
        _assert_orderable_error(ei, "(<)/2")

    def test_naive_vs_aware(self):
        naive = dt.datetime(2020, 1, 1)
        aware = dt.datetime(2020, 1, 1, tzinfo=dt.timezone.utc)
        with pytest.raises(LogicException) as ei:
            fd_le(naive, aware, Trail())
        _assert_orderable_error(ei, "(=<)/2")

    def test_date_vs_int(self):
        with pytest.raises(LogicException) as ei:
            fd_lt(dt.date(2020, 1, 1), 5, Trail())
        _assert_orderable_error(ei, "(<)/2")

    def test_gt_surfaces_lt_context(self):
        # fd_gt delegates to fd_lt with swapped operands.
        with pytest.raises(LogicException) as ei:
            fd_gt(dt.date(2020, 1, 1), dt.datetime(2020, 1, 1), Trail())
        _assert_orderable_error(ei, "(<)/2")

    def test_culprit_is_second_operand(self):
        target = dt.datetime(2020, 1, 1, 0, 0, 0)
        with pytest.raises(LogicException) as ei:
            fd_lt(dt.date(2020, 1, 1), target, Trail())
        assert ei.value.term.args[0].args[1] == target


class TestLegitimateTypeErrorPreserved:
    def test_mixed_rational_real_not_swallowed(self):
        # This must stay a plain TypeError with its "cannot mix" message,
        # NOT be converted to a type_error(orderable, ...).
        with pytest.raises(TypeError) as ei:
            fd_lt(Fraction(1, 2), 0.9, Trail())
        assert "mix" in str(ei.value).lower()


class TestHelper:
    def test_incomparable_order_error(self):
        culprit = dt.datetime(2020, 1, 1)
        exc = _incomparable_order_error(culprit, "(<)/2")
        assert isinstance(exc, LogicException)
        assert exc.term.functor == "error"
        assert exc.term.args[0].functor == "type_error"
        assert exc.term.args[0].args[0] == "orderable"
        assert exc.term.args[0].args[1] == culprit
        assert exc.term.args[1] == "(<)/2"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /workspace/clausal-bug-fix && PYTHONPATH=/workspace/clausal-bug-fix /home/node/.pyenv/versions/3.13.3/bin/python -m pytest tests/test_date_time_ordering.py -q -p no:cacheprovider`

Expected: FAIL. `TestComparisonOperators`, `TestCollectionOrdering`, and `TestLegitimateTypeErrorPreserved` pass immediately (documenting existing behavior). The `TestIncomparableRaises` tests fail because `fd_*` currently raise a raw `TypeError` (not `LogicException`), and `TestHelper` fails at import (`_incomparable_order_error` undefined) — the collection error may also surface as an ImportError until the helper exists. That import error is the first failure to clear in Step 3.

- [ ] **Step 3: Implement the hardening**

In `clausal/logic/clpfd.py`, add the helper immediately before `def fd_eq(` (~line 1607):

```python
def _incomparable_order_error(culprit, context: str) -> "LogicException":
    """Catchable error for an order comparison of two ground values that are
    each orderable but not orderable against each other (e.g. a ``date`` vs a
    ``datetime``, a naive vs a tz-aware ``datetime``, or a ``date`` vs an
    ``int``).  Reuses the ``type_error(orderable, Culprit, Context)`` shape
    that ``min_list/2`` / ``max_list/2`` already raise, so one handler
    catches them all.  *culprit* is the right-hand operand; *context* names
    the primitive operator (``"(<)/2"`` or ``"(=<)/2"``)."""
    from clausal.logic.exceptions import LogicException, type_error  # noqa: PLC0415
    return LogicException(type_error("orderable", culprit, context))
```

Harden the pure-Python fallback. Replace the `_both_ground` branch in `fd_lt` (currently `if _both_ground(l, r): return l < r`, ~line 1723):

```python
    if _both_ground(l, r):
        try:
            return l < r
        except TypeError:
            raise _incomparable_order_error(r, "(<)/2")
```

Replace the `_both_ground` branch in `fd_le` (currently `if _both_ground(l, r): return l <= r`, ~line 1752):

```python
    if _both_ground(l, r):
        try:
            return l <= r
        except TypeError:
            raise _incomparable_order_error(r, "(=<)/2")
```

Harden the C path. In the `if _USE_C_PROPAGATE:` block, replace the two lines
`fd_lt = _c_fd_lt` and `fd_le = _c_fd_le` (~lines 2932-2933) with:

```python
    def fd_lt(l, r, trail, _c_impl=_c_fd_lt):
        # The C fd_lt does no clean type-checking: an incomparable ground
        # comparison escapes as a raw Python TypeError. Convert those to a
        # catchable type_error, while preserving the legitimate mixed
        # CLP(Q)/CLP(R) TypeError and any error involving an unbound operand.
        try:
            return _c_impl(l, r, trail)
        except TypeError:
            dl, dr = deref(l), deref(r)
            if is_var(dl) or is_var(dr):
                raise
            if _any_rational(dl, dr) and _any_real(dl, dr):
                raise
            raise _incomparable_order_error(dr, "(<)/2")

    def fd_le(l, r, trail, _c_impl=_c_fd_le):
        try:
            return _c_impl(l, r, trail)
        except TypeError:
            dl, dr = deref(l), deref(r)
            if is_var(dl) or is_var(dr):
                raise
            if _any_rational(dl, dr) and _any_real(dl, dr):
                raise
            raise _incomparable_order_error(dr, "(=<)/2")
```

(`fd_gt`/`fd_ge` are the pure-Python defs that call the module-global
`fd_lt`/`fd_le`, so they inherit the hardened behavior with swapped operands —
no separate change.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd /workspace/clausal-bug-fix && PYTHONPATH=/workspace/clausal-bug-fix /home/node/.pyenv/versions/3.13.3/bin/python -m pytest tests/test_date_time_ordering.py -q -p no:cacheprovider`

Expected: PASS (all tests in the file).

- [ ] **Step 5: Run the CLP(FD) suite to confirm no regression**

Run: `cd /workspace/clausal-bug-fix && PYTHONPATH=/workspace/clausal-bug-fix /home/node/.pyenv/versions/3.13.3/bin/python -m pytest tests/test_clpfd.py tests/test_clpq.py tests/test_clpz.py -q -p no:cacheprovider`

Expected: PASS (no failures introduced).

- [ ] **Step 6: Commit**

```bash
git add clausal/logic/clpfd.py tests/test_date_time_ordering.py
git commit -m "$(cat <<'EOF'
fix(clpfd): incomparable order comparison raises type_error(orderable)

Comparing two ground values that Python cannot order (date vs datetime,
naive vs tz-aware datetime, date vs int, etc.) leaked a raw TypeError from
</>/<=/>=. Convert it to a catchable error(type_error(orderable, Culprit),
Context), matching what min_list/2 and max_list/2 already raise. Hardens
both the C wrapper and the pure-Python fallback; the mixed CLP(Q)/CLP(R)
TypeError is preserved. Adds date/datetime/time ordering regression tests.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01FjnC9bLQwFUAPDk7PcPXZD
EOF
)"
```

---

### Task 2: End-to-end `.clausal` ordering fixture

**Files:**
- Create: `tests/fixtures/date_time_ordering.clausal`
- Modify: `tests/test_date_time_ordering.py` (append an end-to-end test class)

**Interfaces:**
- Consumes: `clausal.testing.load_clausal_module`, `collect_tests`, `run_test` (returns an object with `.passed`); the fixture uses `date_time` predicates `date/4`, `datetime/7`, `time/4` and the builtins `min_list/2`, `max_list/2`, `catch/3`.
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Write the failing end-to-end test**

Append to `tests/test_date_time_ordering.py`:

```python
class TestEndToEnd:
    def test_fixture_ordering(self):
        from clausal.testing import (
            load_clausal_module, collect_tests, run_test,
        )
        mod = load_clausal_module("tests/fixtures/date_time_ordering.clausal")
        descs = collect_tests(mod)
        assert descs, "fixture defined no Test/1 clauses"
        for desc in descs:
            result = run_test(mod, desc)
            assert result.passed, f"fixture test {desc!r} failed"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd /workspace/clausal-bug-fix && PYTHONPATH=/workspace/clausal-bug-fix /home/node/.pyenv/versions/3.13.3/bin/python -m pytest tests/test_date_time_ordering.py::TestEndToEnd -q -p no:cacheprovider`

Expected: FAIL — the fixture file does not exist yet (`load_clausal_module` raises).

- [ ] **Step 3: Create the fixture**

Create `tests/fixtures/date_time_ordering.clausal` (note: Clausal uses `<=`/`>=`, not `=<`):

```
# Ordering of date/datetime/time via the standard comparison operators,
# plus min_list/max_list on dates and catchability of an incomparable
# comparison. Companion to tests/test_date_time_ordering.py.

-import_from(date_time, [date, datetime, time])

Test("date lt") <- (date(2020,1,1,A), date(2021,1,1,B), A < B)  # nv
Test("date gt") <- (date(2022,1,1,A), date(2021,1,1,B), A > B)  # nv
Test("date le equal") <- (date(2021,1,1,A), date(2021,1,1,B), A <= B)  # nv
Test("date ge equal") <- (date(2021,1,1,A), date(2021,1,1,B), A >= B)  # nv
Test("datetime lt") <- (datetime(2020,1,1,10,0,0,A), datetime(2020,1,1,11,0,0,B), A < B)  # nv
Test("time lt") <- (time(9,0,0,A), time(17,0,0,B), A < B)  # nv
Test("min_list earliest") <- (date(2021,1,1,A), date(2019,5,5,B), min_list([A,B], M), M == B)  # nv
Test("max_list latest") <- (date(2021,1,1,A), date(2019,5,5,B), max_list([A,B], M), M == A)  # nv
Test("catch incomparable") <- catch((date(2020,1,1,A), datetime(2020,1,1,0,0,0,B), A < B), _E, writeln("caught"))  # nv
```

- [ ] **Step 4: Run it to verify it passes**

Run: `cd /workspace/clausal-bug-fix && PYTHONPATH=/workspace/clausal-bug-fix /home/node/.pyenv/versions/3.13.3/bin/python -m pytest tests/test_date_time_ordering.py::TestEndToEnd -q -p no:cacheprovider`

Expected: PASS. (You can also eyeball it directly: `... -m clausal.testing tests/fixtures/date_time_ordering.clausal` prints `9 tests: 9 passed`.)

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/date_time_ordering.clausal tests/test_date_time_ordering.py
git commit -m "$(cat <<'EOF'
test(date_time): end-to-end ordering fixture for date/datetime/time

Exercises </>/<=/>= on constructed date/datetime/time values, min_list/
max_list on a date list, and catchability of an incomparable comparison,
through the full compiler path.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01FjnC9bLQwFUAPDk7PcPXZD
EOF
)"
```

---

### Task 3: Documentation

**Files:**
- Modify: `docs/date_time.md` (add an "Ordering & comparison" section after the Python Interop section, before `## Predicates` at line 63)
- Modify: `clausal/modules/py/datetime.py` (add an Ordering note to the module docstring)

**Interfaces:**
- Consumes: nothing. Produces: nothing.

- [ ] **Step 1: Add the docs section to `docs/date_time.md`**

Insert immediately before the `## Predicates` line (line 63):

```markdown
## Ordering & comparison

`date`, `time`, and `datetime` values are orderable with the standard
comparison operators — `<`, `>`, `<=`, `>=` — because they are real Python
objects with a natural chronological order:

```clausal
-import_from(date_time, [date])

Earlier(A, B) <- (date(2020, 1, 1, A), date(2021, 1, 1, B), A < B)  # succeeds
```

The same values sort chronologically through `sort/2`, `msort/2`,
`min_list/2`, and `max_list/2`.

Only *comparable* values can be ordered against each other. Comparing a `date`
with a `datetime`, a naive `datetime` with a tz-aware one, or a date with a
number raises a catchable `error(type_error(orderable, Culprit), (<)/2)` —
the same error `min_list/2` and `max_list/2` raise for a non-orderable list:

```clausal
catch(
    (date(2020, 1, 1, D), datetime(2020, 1, 1, 0, 0, 0, DT), D < DT),
    error(type_error(orderable, _), _),
    Recover
)
```

(`>` and `>=` are the flipped `<` / `<=`, so their errors report the `(<)/2`
/ `(=<)/2` context.)

---
```

- [ ] **Step 2: Add the Ordering note to the module docstring**

In `clausal/modules/py/datetime.py`, in the module docstring, after the
"Bidirectional predicates" paragraph (ends just before the closing `"""` at
line 41), add:

```
Ordering
--------
``date``, ``time`` and ``datetime`` values are orderable with the standard
comparison operators ``<``, ``>``, ``<=``, ``>=`` and sort chronologically
through ``sort/2``, ``msort/2``, ``min_list/2`` and ``max_list/2``.  Comparing
two values that are not orderable against each other (``date`` vs
``datetime``, naive vs tz-aware ``datetime``, ``date`` vs a number) raises a
catchable ``error(type_error(orderable, Culprit), (<)/2)``.
```

- [ ] **Step 3: Verify docs build / render (sanity)**

Run: `cd /workspace/clausal-bug-fix && PYTHONPATH=/workspace/clausal-bug-fix /home/node/.pyenv/versions/3.13.3/bin/python -c "import clausal.modules.py.datetime as m; assert 'Ordering' in m.__doc__; print('docstring OK')"`

Expected: prints `docstring OK`.

- [ ] **Step 4: Commit**

```bash
git add docs/date_time.md clausal/modules/py/datetime.py
git commit -m "$(cat <<'EOF'
docs(date_time): document date/datetime/time ordering & comparison

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01FjnC9bLQwFUAPDk7PcPXZD
EOF
)"
```

---

## Self-Review

**Spec coverage:**
- Part 1 (harden incomparable → structured `type_error`, both C and pure-Python paths, preserve mixed CLP(Q)/CLP(R), `orderable` vocabulary) → Task 1.
- Part 2 (regression tests: operators on date/datetime/time; sort/msort/min_list/max_list; incomparable raises structured error; catch/3; both paths) → Task 1 (Python level) + Task 2 (end-to-end fixture).
- Part 3 (docstring + `docs/date_time.md`) → Task 3.
- Out-of-scope items (no `compare/3`/`@<`, no var-operand FD semantics, no change to numeric/string ground behavior beyond error hardening) → respected; no task touches them.

**Placeholder scan:** none — every code and command step is concrete.

**Type consistency:** `_incomparable_order_error(culprit, context)` is defined in Task 1 and referenced only there. Test helpers `_run_list_builtin` / `_assert_orderable_error` are defined and used within the same file. Builtin names `_sort__2`, `_msort__2`, `_min_list__2`, `_max_list__2` and `fd_lt`/`fd_le`/`fd_gt`/`fd_ge` match the source. Error term shape (`error(type_error(orderable, Culprit), Context)`) is consistent across implementation, tests, and docs.
