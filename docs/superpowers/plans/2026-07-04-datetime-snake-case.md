# `py.datetime` snake_case Rename Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the `py.datetime` predicate surface to snake_case following Python `datetime` conventions, fold format+parse into one bidirectional `datetime_string/3`, and add `timestamp/2` plus ISO-8601 helpers.

**Architecture:** Flag-day rename (no TitleCase aliases). Predicate names bind to Python module *attributes* (`-import_from(py.datetime, [date])` → `from py.datetime import date`), so renaming the exported objects + their `_name` strings + all in-repo consumers (Python tests, `.clausal` fixtures, docs code-blocks) is the whole job. New predicates follow the module's existing bidirectional pattern with `simple_to_trampoline`.

**Tech Stack:** Python 3.13, Clausal runtime (`ModulePredicate`, `simple_to_trampoline`, `unify`/`deref`/`is_var`), pytest with the repo's `conftest.py` `.clausal`/docs collectors.

## Global Constraints

- **Design spec:** `docs/superpowers/specs/2026-07-04-datetime-snake-case-design.md` — authoritative for names/semantics.
- **Test runner (memory `running-tests-in-bug-fix-clone`):** ALWAYS use pyenv 3.13.3 with PYTHONPATH set to the clone. Never the venv python (its editable install shadows the clone).
  - Full: `cd /workspace/clausal-bug-fix && PYTHONPATH=/workspace/clausal-bug-fix /home/node/.pyenv/versions/3.13.3/bin/python -m pytest tests/ -q -p no:cacheprovider`
  - A single `.clausal` fixture: `PYTHONPATH=/workspace/clausal-bug-fix /home/node/.pyenv/versions/3.13.3/bin/python -m pytest "tests/fixtures/docs/date_time_sig_tests.clausal" -q -p no:cacheprovider`
  - A single docs page's blocks: `... -m pytest docs/date_time.md -q -p no:cacheprovider`
- **Baseline (2026-07-02):** full suite ≈ 8253 passed, 2 skipped, 1 xfailed, 0 failures. End state must have 0 new failures.
- **Module name stays `date_time`/`py.datetime`.** Do NOT alter `-import_from(date_time, …)` module names or the `_module="datetime"` value or the alias tables in `clausal/logic/compiler_v2.py:198` / `clausal/templating/term_rewriting.py:1316`. Only *predicate* identifiers change.
- **Word-boundary renames only, longest-token first.** Apply the rename map with `\b` boundaries and `DateTime`→`datetime` / `NowUTC`→`now_utc` / `DaysBetween`→`days_between` BEFORE the shorter `Date`/`Now` tokens so substrings aren't corrupted. Never touch `date_time` (module) or `dt.` (stdlib alias) — boundaries protect these, but verify.

### Rename map (old identifier → new identifier)

| old | new |
|---|---|
| `NowUTC` | `now_utc` |
| `Now` | `now` |
| `Today` | `today` |
| `DateTime` | `datetime` |
| `DateAdd` | `date_add` |
| `DateSub` | `date_sub` |
| `DateDiff` | `date_diff` |
| `DateBetween` | `date_between` |
| `DaysBetween` | `days_between` |
| `DateOf` | `date_of` |
| `Date` | `date` |
| `TimeDelta` | `timedelta` |
| `Time` | `time` |
| `DayOfWeek` | `weekday` |
| `FormatDate` | *removed → `datetime_string`* |
| `ParseDate` | *removed → `datetime_string`* |

Internal dispatch fn `_day_of_week_2` → `_weekday_2`. Removed: `_format_date_3`, `_parse_date_3`. New: `_datetime_string_3`, `_timestamp_2`, `_datetime_string_iso_2`, `_date_string_iso_2`.

---

## Task 1: Rename existing surface + fold format/parse into `datetime_string/3`

Atomic: the flag-day rename breaks the module and all its consumers at once, so they move together in one green commit. New *additive* predicates come in Tasks 2–3.

**Files:**
- Modify: `clausal/modules/py/datetime.py` (whole export block, docstring, `_day_of_week_2`→`_weekday_2`, replace `_format_date_3`+`_parse_date_3` with `_datetime_string_3`)
- Modify: `tests/test_date_time.py` (imports, `TestFormatDate`/`TestParseDate`→`TestDatetimeString`, `TestDayOfWeek` refs, `TestAdapters`, repr test)
- Modify: `tests/fixtures/docs/date_time_sig_tests.clausal`
- Modify: `tests/fixtures/docs/date_time_sigs.txt`
- Modify: `tests/test_transitive_py_module_import.py`
- Modify: `docs/date_time.md`, `docs/builtins.md`, `docs/compiler.md`, `docs/python_integration.md`

**Interfaces:**
- Produces (module attributes, all `ModulePredicate` with `module="datetime"`): `now/1`, `now_utc/1`, `today/1`, `date/4`, `time/4`, `datetime/7`, `timedelta/3`, `date_add/3`, `date_sub/3`, `date_diff/3`, `date_between/3`, `days_between/3`, `date_of/2`, `weekday/2`, `datetime_string/3`.
- Produces (dispatch fns, unchanged bodies unless noted): `_now_1`, `_now_utc_1`, `_today_1`, `_date_4`, `_time_4`, `_datetime_7`, `_timedelta_3`, `_date_add_3`, `_date_sub_3`, `_date_diff_3`, `_date_between_3`, `_days_between_3`, `_date_of_2`, `_weekday_2` (renamed), `_datetime_string_3` (new).
- `datetime_string(DATETIME, STRING, FORMAT)` — FORMAT is the trailing arg (simple-mode signature `_datetime_string_3(dt_obj, s, fmt, trail, k)`).

- [ ] **Step 1: Update the Python unit tests first (RED).**

In `tests/test_date_time.py`, replace the import block with:

```python
from clausal.modules.py.datetime import (
    now, now_utc, today, date, time, datetime, timedelta,
    date_add, date_sub, date_diff, date_between, date_of, days_between,
    weekday, datetime_string,
    _now_1, _now_utc_1, _today_1,
    _date_4, _time_4, _datetime_7, _timedelta_3,
    _date_add_3, _date_sub_3, _date_diff_3,
    _datetime_string_3, _weekday_2,
    _date_of_2, _days_between_3,
)
```

Replace the `TestFormatDate` and `TestParseDate` classes (lines ~363–442) with one class exercising the folded predicate (arg order DATETIME, STRING, FORMAT):

```python
class TestDatetimeString:
    def test_format_date(self):
        # nv — format mode
        s = Var()
        results, _ = simple_solutions(
            _datetime_string_3, dt.date(2026, 3, 16), s, "%Y-%m-%d"
        )
        assert len(results) == 1
        assert deref(s) == "2026-03-16"

    def test_format_datetime(self):
        # nv
        s = Var()
        results, _ = simple_solutions(
            _datetime_string_3,
            dt.datetime(2026, 3, 16, 14, 30, 0), s, "%Y-%m-%d %H:%M",
        )
        assert len(results) == 1
        assert deref(s) == "2026-03-16 14:30"

    def test_format_time(self):
        # nv
        s = Var()
        results, _ = simple_solutions(
            _datetime_string_3, dt.time(14, 30, 0), s, "%H:%M:%S"
        )
        assert len(results) == 1
        assert deref(s) == "14:30:00"

    def test_parse_to_datetime(self):
        # vn — parse mode
        v = Var()
        results, _ = simple_solutions(
            _datetime_string_3, v, "2026-03-16 14:30", "%Y-%m-%d %H:%M"
        )
        assert len(results) == 1
        assert deref(v) == dt.datetime(2026, 3, 16, 14, 30)

    def test_check_mode_matches(self):
        # nn — both ground, format matches
        results, _ = simple_solutions(
            _datetime_string_3, dt.date(2026, 3, 16), "2026-03-16", "%Y-%m-%d"
        )
        assert len(results) == 1

    def test_check_mode_mismatch_fails(self):
        # nn
        results, _ = simple_solutions(
            _datetime_string_3, dt.date(2026, 3, 16), "2026-03-17", "%Y-%m-%d"
        )
        assert len(results) == 0

    def test_parse_invalid_fails(self):
        # vn
        v = Var()
        results, _ = simple_solutions(
            _datetime_string_3, v, "not-a-date", "%Y-%m-%d"
        )
        assert len(results) == 0

    def test_both_unbound_fails(self):
        # vv
        results, _ = simple_solutions(_datetime_string_3, Var(), Var(), "%Y-%m-%d")
        assert len(results) == 0

    def test_unbound_format_fails(self):
        # format arg must be ground
        results, _ = simple_solutions(
            _datetime_string_3, dt.date(2026, 3, 16), Var(), Var()
        )
        assert len(results) == 0

    def test_date_roundtrips_to_midnight_datetime(self):
        """A date → string → back yields a midnight datetime (documented asymmetry)."""
        # nv then vn
        s = Var()
        simple_solutions(_datetime_string_3, dt.date(2026, 3, 16), s, "%Y-%m-%d")
        v = Var()
        simple_solutions(_datetime_string_3, v, deref(s), "%Y-%m-%d")
        assert deref(v) == dt.datetime(2026, 3, 16, 0, 0, 0)
```

In `TestDayOfWeek` (lines ~448–471) rename every `_day_of_week_2` → `_weekday_2` (behavior identical: 0=Mon..6=Sun). In `TestAdapters`, replace the `Now/Today/Date/Time/DateTime/TimeDelta/DateAdd/DateSub/DateDiff/FormatDate/ParseDate/DayOfWeek/DateBetween/DateOf/DaysBetween` references with the snake_case objects (`now, today, date, time, datetime, timedelta, date_add, date_sub, date_diff, weekday, date_between, date_of, days_between`), drop the `FormatDate`/`ParseDate` adapter tests, and add `test_datetime_string_has_dispatch` asserting `callable(datetime_string._get_dispatch())`. Replace the repr test body with:

```python
    def test_repr(self):
        # nv
        assert "datetime.date" in repr(date)
        assert "datetime.date_between" in repr(date_between)
```

Apply the rename map to every remaining TitleCase reference in the file (class docstrings/comments may stay descriptive, but all *code* identifiers must be snake_case).

- [ ] **Step 2: Run the unit tests to confirm they fail.**

Run: `cd /workspace/clausal-bug-fix && PYTHONPATH=/workspace/clausal-bug-fix /home/node/.pyenv/versions/3.13.3/bin/python -m pytest tests/test_date_time.py -q -p no:cacheprovider`
Expected: FAIL — `ImportError: cannot import name 'now' from clausal.modules.py.datetime` (module not yet renamed).

- [ ] **Step 3: Rewrite the module.**

In `clausal/modules/py/datetime.py`:

(a) Rename `_day_of_week_2` → `_weekday_2` (body unchanged).

(b) Delete `_format_date_3` and `_parse_date_3`; add the folded predicate:

```python
# ── datetime_string/3 — bidirectional strftime/strptime ──────────────────


def _datetime_string_3(dt_obj, s, fmt, trail, k):
    """datetime_string/3: bidirectional — datetime_string(DateTime, String, Format).

    Format mode (DateTime has ``strftime``): String = DateTime.strftime(Format);
    with String bound this is a check.
    Parse mode (DateTime unbound, String a string): DateTime =
    datetime.strptime(String, Format).

    Format must be a ground string in both modes.  Note: ``strftime`` accepts a
    ``date``/``time``/``datetime`` but ``strptime`` always yields a ``datetime``,
    so a date round-trips to a midnight datetime.
    """
    dt_obj, s, fmt = deref(dt_obj), deref(s), deref(fmt)
    if not isinstance(fmt, str):
        return
    if hasattr(dt_obj, 'strftime'):
        try:
            out = dt_obj.strftime(fmt)
        except (TypeError, ValueError):
            return
        if unify(s, out, trail):
            yield None
    elif is_var(dt_obj) and isinstance(s, str):
        try:
            out = _dt.datetime.strptime(s, fmt)
        except (TypeError, ValueError):
            return
        if unify(dt_obj, out, trail):
            yield None
```

(c) Replace the entire "Build and export predicate objects" block (lines ~393–441) with the snake_case registrations:

```python
now = ModulePredicate("now", module="datetime")
now._register(1, simple_to_trampoline(_now_1))

now_utc = ModulePredicate("now_utc", module="datetime")
now_utc._register(1, simple_to_trampoline(_now_utc_1))

today = ModulePredicate("today", module="datetime")
today._register(1, simple_to_trampoline(_today_1))

date = ModulePredicate("date", module="datetime")
date._register(4, simple_to_trampoline(_date_4))

time = ModulePredicate("time", module="datetime")
time._register(4, simple_to_trampoline(_time_4))

datetime = ModulePredicate("datetime", module="datetime")
datetime._register(7, simple_to_trampoline(_datetime_7))

timedelta = ModulePredicate("timedelta", module="datetime")
timedelta._register(3, simple_to_trampoline(_timedelta_3))

date_add = ModulePredicate("date_add", module="datetime")
date_add._register(3, simple_to_trampoline(_date_add_3))

date_sub = ModulePredicate("date_sub", module="datetime")
date_sub._register(3, simple_to_trampoline(_date_sub_3))

date_diff = ModulePredicate("date_diff", module="datetime")
date_diff._register(3, simple_to_trampoline(_date_diff_3))

datetime_string = ModulePredicate("datetime_string", module="datetime")
datetime_string._register(3, simple_to_trampoline(_datetime_string_3))

date_of = ModulePredicate("date_of", module="datetime")
date_of._register(2, simple_to_trampoline(_date_of_2))

days_between = ModulePredicate("days_between", module="datetime")
days_between._register(3, simple_to_trampoline(_days_between_3))

weekday = ModulePredicate("weekday", module="datetime")
weekday._register(2, simple_to_trampoline(_weekday_2))

date_between = ModulePredicate("date_between", module="datetime")
date_between._register(3, _date_between_3)
```

(d) Update the module docstring's `-import_from` example (lines ~6–9) and the "Prefer these declarative predicates" prose (lines ~36–40) to snake_case, and replace the `FormatDate(...)`/`ParseDate(...)` mentions with `datetime_string(DT, S, "%Y-%m-%d")`. Update the `Date/4 ↔` bullet list casing to `date/4`, `time/4`, `datetime/7`, `timedelta/3`, `date_of/2`.

- [ ] **Step 4: Run the unit tests to confirm they pass.**

Run: `cd /workspace/clausal-bug-fix && PYTHONPATH=/workspace/clausal-bug-fix /home/node/.pyenv/versions/3.13.3/bin/python -m pytest tests/test_date_time.py -q -p no:cacheprovider`
Expected: PASS (all classes green).

- [ ] **Step 5: Update the `.clausal` fixture (collected & run by pytest).**

In `tests/fixtures/docs/date_time_sig_tests.clausal`: apply the rename map to the `-import_from(date_time, [...])` list and every predicate call. Replace the import list with:

```
-import_from(date_time, [now, now_utc, today, date, time, datetime,
                         timedelta, date_add, date_sub, date_diff, days_between,
                         datetime_string, date_of, weekday])
```

Rewrite the format/parse Test clauses to the folded predicate:

```
Test("format date") <- (
    date(2026, 3, 16, D),
    datetime_string(D, S, "%Y-%m-%d"),
    S == "2026-03-16"
)  # nv

Test("parse date") <- (
    datetime_string(DT, "2026-03-16", "%Y-%m-%d"),
    nonvar(DT)
)  # vn
```

And the "parse iso to date diff no escapes" Test clause:

```
Test("parse iso to date diff no escapes") <- (
    datetime_string(DT_A, "2026-03-23", "%Y-%m-%d"),
    datetime_string(DT_B, "2026-03-16", "%Y-%m-%d"),
    date_of(DT_A, A),
    date_of(DT_B, B),
    days_between(A, B, N),
    N == 7
)  # vn
```

The `DayOfWeek(D, DOW)` Test becomes `weekday(D, DOW)`. Apply the rename map to all other clauses (`Date`→`date`, `DateTime`→`datetime`, `TimeDelta`→`timedelta`, `DateAdd`→`date_add`, `DateSub`→`date_sub`, `DateDiff`→`date_diff`, `DaysBetween`→`days_between`, `DateOf`→`date_of`).

- [ ] **Step 6: Update the display snippet file.**

In `tests/fixtures/docs/date_time_sigs.txt`: apply the rename map inside every snippet. Replace the `format_date` and `parse_date` sections with a single `datetime_string` section (keep both section markers referenced by the docs — see Step 7 — OR consolidate; if consolidating, update the `--8<--` refs accordingly). Recommended consolidation:

```
--8<-- [start:datetime_string]
datetime_string(DT, S, "%Y-%m-%d")    # format: S = "2026-03-16"
datetime_string(DT, "2026-03-16", "%Y-%m-%d")    # parse: DT = midnight datetime
--8<-- [end:datetime_string]
```

Rename the `day_of_week` section body to `weekday(D, DOW)    # DOW = 0 (Monday) through 6 (Sunday)` (keep the section marker name `day_of_week` OR rename to `weekday` and update the doc ref in Step 7 to match).

- [ ] **Step 7: Update `docs/date_time.md`.**

Apply the rename map to the three ```clausal blocks (the `-import_from` lists at lines ~12, ~41, ~153 and their bodies), the prose predicate references, and the `--8<--` snippet refs so they match the section names chosen in Step 6 (e.g. replace the `:format_date` and `:parse_date` refs with a single `:datetime_string` ref; `:day_of_week` → `:weekday` if renamed). Update the "Test coverage" info block bullets (`FormatDate/ParseDate` → `datetime_string`, `DayOfWeek` → `weekday`).

- [ ] **Step 8: Update the transitive-import test.**

In `tests/test_transitive_py_module_import.py`: in the two inline `.clausal` snippets, rename `-import_from(date_time, [Date, DateDiff])` → `[date, date_diff]` and the call sites `Date(...)`→`date(...)`, `DateDiff(...)`→`date_diff(...)`. Leave the *user-defined* `days_between/6` predicate name in that fixture as-is (it is the test's own rule head, not the module predicate).

- [ ] **Step 9: Update the remaining reference docs.**

- `docs/python_integration.md:~166`: `-import_from(date_time, [Date])` → `[date]` and the block body `Date(...)`→`date(...)`.
- `docs/compiler.md:~579`: rename the module predicate summary list to `now/1, now_utc/1, today/1, date/4, time/4, datetime/7, timedelta/3, date_add/3, date_sub/3, date_diff/3, datetime_string/3, weekday/2, date_between/3`.
- `docs/builtins.md`: apply the rename map to the summary line (~2519), the index table row (~95), the per-predicate `### ` headings (~2533–2666: `### FormatDate/3` + `### ParseDate/3` → one `### datetime_string/3`; `### DayOfWeek/2` → `### weekday/2`; etc.), and the test-file mapping row (~2740). Grep the date section for any ```clausal blocks and apply the rename map. (Tasks 2–3 add the `timestamp`/`iso` entries.)

- [ ] **Step 10: Run the full suite; confirm no new failures.**

Run: `cd /workspace/clausal-bug-fix && PYTHONPATH=/workspace/clausal-bug-fix /home/node/.pyenv/versions/3.13.3/bin/python -m pytest tests/ docs/ -q -p no:cacheprovider`
Expected: 0 failures (matches baseline; the datetime `.clausal` and doc-block items pass under new names). If any `[compile error]` doc item appears, it names the file+line — fix that block per the rename map.

- [ ] **Step 11: Commit.**

```bash
cd /workspace/clausal-bug-fix
git add clausal/modules/py/datetime.py tests/test_date_time.py \
  tests/fixtures/docs/date_time_sig_tests.clausal tests/fixtures/docs/date_time_sigs.txt \
  tests/test_transitive_py_module_import.py \
  docs/date_time.md docs/builtins.md docs/compiler.md docs/python_integration.md
git commit -m "refactor(datetime): snake_case rename + fold format/parse into datetime_string/3

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Add `timestamp/2` (bidirectional datetime ↔ POSIX epoch)

**Files:**
- Modify: `clausal/modules/py/datetime.py` (add `_timestamp_2` + `timestamp` export)
- Modify: `tests/test_date_time.py` (import `timestamp`, `_timestamp_2`; add `TestTimestamp`; add adapter test)
- Modify: `tests/fixtures/docs/date_time_sig_tests.clausal` (Test clause), `tests/fixtures/docs/date_time_sigs.txt` (snippet), `docs/date_time.md` (section + snippet ref), `docs/builtins.md`/`docs/compiler.md` (reference entry)

**Interfaces:**
- Consumes: `datetime/7` (to build a datetime in tests), `_dt.datetime`.
- Produces: `timestamp/2` (`ModulePredicate`, `module="datetime"`); dispatch `_timestamp_2(dt_obj, stamp, trail, k)`.

- [ ] **Step 1: Write the failing tests.**

Add to `tests/test_date_time.py`:

```python
class TestTimestamp:
    def test_forward_datetime_to_float(self):
        # nv
        v = Var()
        d = dt.datetime(2026, 3, 16, 12, 0, 0)
        results, _ = simple_solutions(_timestamp_2, d, v)
        assert len(results) == 1
        assert deref(v) == d.timestamp()

    def test_inverse_float_to_datetime(self):
        # vn
        d = dt.datetime(2026, 3, 16, 12, 0, 0)
        v = Var()
        results, _ = simple_solutions(_timestamp_2, v, d.timestamp())
        assert len(results) == 1
        assert deref(v) == d

    def test_inverse_int_stamp(self):
        # vn
        v = Var()
        results, _ = simple_solutions(_timestamp_2, v, 0)
        assert len(results) == 1
        assert isinstance(deref(v), dt.datetime)

    def test_check_mode_matches(self):
        # nn
        d = dt.datetime(2026, 3, 16, 12, 0, 0)
        results, _ = simple_solutions(_timestamp_2, d, d.timestamp())
        assert len(results) == 1

    def test_date_has_no_timestamp_fails(self):
        # a plain date is not a datetime → forward fails
        results, _ = simple_solutions(_timestamp_2, dt.date(2026, 3, 16), Var())
        assert len(results) == 0

    def test_both_unbound_fails(self):
        # vv
        results, _ = simple_solutions(_timestamp_2, Var(), Var())
        assert len(results) == 0
```

Add `timestamp, _timestamp_2` to the module import block, and add to `TestAdapters`:

```python
    def test_timestamp_has_dispatch(self):
        # nv
        assert callable(timestamp._get_dispatch())
```

- [ ] **Step 2: Run to confirm failure.**

Run: `... -m pytest tests/test_date_time.py::TestTimestamp -q -p no:cacheprovider`
Expected: FAIL — `cannot import name 'timestamp'`.

- [ ] **Step 3: Implement.**

Add to `clausal/modules/py/datetime.py` (before the export block):

```python
# ── timestamp/2 — bidirectional datetime ↔ POSIX epoch ───────────────────


def _timestamp_2(dt_obj, stamp, trail, k):
    """timestamp/2: bidirectional — timestamp(DateTime, Stamp).

    Forward (DateTime is a ``datetime``): Stamp = DateTime.timestamp() (float
    epoch seconds); with Stamp bound this is a check.
    Inverse (DateTime unbound, Stamp a number): DateTime =
    datetime.fromtimestamp(Stamp).  A plain ``date`` has no ``timestamp()``, so
    the forward direction requires a ``datetime``.
    """
    dt_obj, stamp = deref(dt_obj), deref(stamp)
    if isinstance(dt_obj, _dt.datetime):
        try:
            out = dt_obj.timestamp()
        except (OverflowError, OSError, ValueError):
            return
        if unify(stamp, out, trail):
            yield None
    elif is_var(dt_obj) and isinstance(stamp, (int, float)) and not isinstance(stamp, bool):
        try:
            out = _dt.datetime.fromtimestamp(stamp)
        except (OverflowError, OSError, ValueError, TypeError):
            return
        if unify(dt_obj, out, trail):
            yield None
```

Add to the export block:

```python
timestamp = ModulePredicate("timestamp", module="datetime")
timestamp._register(2, simple_to_trampoline(_timestamp_2))
```

- [ ] **Step 4: Run to confirm pass.**

Run: `... -m pytest tests/test_date_time.py::TestTimestamp tests/test_date_time.py::TestAdapters -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 5: Add doc coverage.**

- `tests/fixtures/docs/date_time_sigs.txt`: add a `timestamp` snippet section:
  ```
  --8<-- [start:timestamp]
  timestamp(DT, TS)    # forward: TS = DT.timestamp() (float epoch)
  timestamp(DT, 0)     # inverse: DT = datetime.fromtimestamp(0)
  --8<-- [end:timestamp]
  ```
- `tests/fixtures/docs/date_time_sig_tests.clausal`: add `timestamp` to the import list and a Test:
  ```
  Test("timestamp roundtrip") <- (
      datetime(2026, 3, 16, 12, 0, 0, DT),
      timestamp(DT, TS),
      timestamp(DT2, TS),
      DT == DT2
  )  # nv
  ```
- `docs/date_time.md`: add a `timestamp/2` subsection with an `--8<-- "tests/fixtures/docs/date_time_sigs.txt:timestamp"` reference and prose.
- `docs/builtins.md` + `docs/compiler.md`: add `timestamp/2` to the reference list/table.

- [ ] **Step 6: Run docs + datetime tests, then commit.**

Run: `... -m pytest tests/test_date_time.py "tests/fixtures/docs/date_time_sig_tests.clausal" docs/date_time.md -q -p no:cacheprovider`
Expected: PASS.

```bash
git add clausal/modules/py/datetime.py tests/test_date_time.py \
  tests/fixtures/docs/date_time_sig_tests.clausal tests/fixtures/docs/date_time_sigs.txt \
  docs/date_time.md docs/builtins.md docs/compiler.md
git commit -m "feat(datetime): add bidirectional timestamp/2

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Add `datetime_string_iso/2` and `date_string_iso/2`

**Files:**
- Modify: `clausal/modules/py/datetime.py` (two dispatch fns + two exports)
- Modify: `tests/test_date_time.py` (imports; `TestDatetimeStringIso`, `TestDateStringIso`; adapter tests)
- Modify: `tests/fixtures/docs/date_time_sig_tests.clausal`, `tests/fixtures/docs/date_time_sigs.txt`, `docs/date_time.md`, `docs/builtins.md`, `docs/compiler.md`

**Interfaces:**
- Consumes: `_dt.datetime`, `_dt.date`.
- Produces: `datetime_string_iso/2` (`_datetime_string_iso_2`), `date_string_iso/2` (`_date_string_iso_2`).

- [ ] **Step 1: Write the failing tests.**

Add to `tests/test_date_time.py`:

```python
class TestDatetimeStringIso:
    def test_forward(self):
        # nv
        s = Var()
        d = dt.datetime(2026, 3, 16, 14, 30, 0)
        results, _ = simple_solutions(_datetime_string_iso_2, d, s)
        assert len(results) == 1
        assert deref(s) == "2026-03-16T14:30:00"

    def test_inverse(self):
        # vn
        v = Var()
        results, _ = simple_solutions(
            _datetime_string_iso_2, v, "2026-03-16T14:30:00"
        )
        assert len(results) == 1
        assert deref(v) == dt.datetime(2026, 3, 16, 14, 30, 0)

    def test_inverse_invalid_fails(self):
        # vn
        v = Var()
        results, _ = simple_solutions(_datetime_string_iso_2, v, "nope")
        assert len(results) == 0

    def test_both_unbound_fails(self):
        # vv
        results, _ = simple_solutions(_datetime_string_iso_2, Var(), Var())
        assert len(results) == 0


class TestDateStringIso:
    def test_forward(self):
        # nv
        s = Var()
        results, _ = simple_solutions(_date_string_iso_2, dt.date(2026, 3, 16), s)
        assert len(results) == 1
        assert deref(s) == "2026-03-16"

    def test_inverse(self):
        # vn
        v = Var()
        results, _ = simple_solutions(_date_string_iso_2, v, "2026-03-16")
        assert len(results) == 1
        out = deref(v)
        assert out == dt.date(2026, 3, 16)
        assert isinstance(out, dt.date) and not isinstance(out, dt.datetime)

    def test_forward_rejects_datetime(self):
        """A datetime is not a plain date → forward fails (guarded like date/4)."""
        # nv
        results, _ = simple_solutions(
            _date_string_iso_2, dt.datetime(2026, 3, 16, 1, 2, 3), Var()
        )
        assert len(results) == 0

    def test_inverse_invalid_fails(self):
        # vn
        v = Var()
        results, _ = simple_solutions(_date_string_iso_2, v, "2026-03-16T00:00:00")
        assert len(results) == 0
```

Add `datetime_string_iso, date_string_iso, _datetime_string_iso_2, _date_string_iso_2` to the import block, and two adapter tests asserting `callable(datetime_string_iso._get_dispatch())` and `callable(date_string_iso._get_dispatch())`.

- [ ] **Step 2: Run to confirm failure.**

Run: `... -m pytest tests/test_date_time.py::TestDatetimeStringIso tests/test_date_time.py::TestDateStringIso -q -p no:cacheprovider`
Expected: FAIL — `cannot import name 'datetime_string_iso'`.

- [ ] **Step 3: Implement.**

Add to `clausal/modules/py/datetime.py` (before the export block):

```python
# ── ISO-8601 helpers — bidirectional, via isoformat/fromisoformat ────────


def _datetime_string_iso_2(dt_obj, s, trail, k):
    """datetime_string_iso/2: bidirectional ISO-8601 datetime.

    Forward (DateTime is a ``datetime``): String = DateTime.isoformat().
    Inverse (DateTime unbound, String a string): DateTime =
    datetime.fromisoformat(String).
    """
    dt_obj, s = deref(dt_obj), deref(s)
    if isinstance(dt_obj, _dt.datetime):
        if unify(s, dt_obj.isoformat(), trail):
            yield None
    elif is_var(dt_obj) and isinstance(s, str):
        try:
            out = _dt.datetime.fromisoformat(s)
        except (TypeError, ValueError):
            return
        if unify(dt_obj, out, trail):
            yield None


def _date_string_iso_2(d_obj, s, trail, k):
    """date_string_iso/2: bidirectional ISO-8601 date (YYYY-MM-DD).

    Forward (Date is a ``date`` and not a ``datetime``): String = Date.isoformat().
    Inverse (Date unbound, String a string): Date = date.fromisoformat(String).
    """
    d_obj, s = deref(d_obj), deref(s)
    if isinstance(d_obj, _dt.date) and not isinstance(d_obj, _dt.datetime):
        if unify(s, d_obj.isoformat(), trail):
            yield None
    elif is_var(d_obj) and isinstance(s, str):
        try:
            out = _dt.date.fromisoformat(s)
        except (TypeError, ValueError):
            return
        if unify(d_obj, out, trail):
            yield None
```

Add to the export block:

```python
datetime_string_iso = ModulePredicate("datetime_string_iso", module="datetime")
datetime_string_iso._register(2, simple_to_trampoline(_datetime_string_iso_2))

date_string_iso = ModulePredicate("date_string_iso", module="datetime")
date_string_iso._register(2, simple_to_trampoline(_date_string_iso_2))
```

- [ ] **Step 4: Run to confirm pass.**

Run: `... -m pytest tests/test_date_time.py::TestDatetimeStringIso tests/test_date_time.py::TestDateStringIso tests/test_date_time.py::TestAdapters -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 5: Add doc coverage.**

- `tests/fixtures/docs/date_time_sigs.txt`: add
  ```
  --8<-- [start:iso]
  datetime_string_iso(DT, S)    # S = "2026-03-16T14:30:00" / inverse parses it
  date_string_iso(D, S)         # S = "2026-03-16" / inverse parses it
  --8<-- [end:iso]
  ```
- `tests/fixtures/docs/date_time_sig_tests.clausal`: add both to the import list and Tests:
  ```
  Test("datetime iso roundtrip") <- (
      datetime(2026, 3, 16, 14, 30, 0, DT),
      datetime_string_iso(DT, S),
      datetime_string_iso(DT2, S),
      DT == DT2
  )  # nv

  Test("date iso roundtrip") <- (
      date(2026, 3, 16, D),
      date_string_iso(D, S),
      date_string_iso(D2, S),
      D == D2
  )  # nv
  ```
- `docs/date_time.md`: add an ISO helpers subsection referencing `--8<-- "tests/fixtures/docs/date_time_sigs.txt:iso"`.
- `docs/builtins.md` + `docs/compiler.md`: add `datetime_string_iso/2` and `date_string_iso/2` to the reference list/table.

- [ ] **Step 6: Run the FULL suite; confirm baseline; commit.**

Run: `cd /workspace/clausal-bug-fix && PYTHONPATH=/workspace/clausal-bug-fix /home/node/.pyenv/versions/3.13.3/bin/python -m pytest tests/ docs/ -q -p no:cacheprovider`
Expected: 0 failures (baseline ≈ 8253 passed + the new tests).

```bash
git add clausal/modules/py/datetime.py tests/test_date_time.py \
  tests/fixtures/docs/date_time_sig_tests.clausal tests/fixtures/docs/date_time_sigs.txt \
  docs/date_time.md docs/builtins.md docs/compiler.md
git commit -m "feat(datetime): add ISO-8601 helpers datetime_string_iso/2, date_string_iso/2

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Retire the TODO

**Files:**
- Modify/Move: `todo/date-api-snake-case-rename.md`

- [ ] **Step 1: Mark the TODO done.**

Move `todo/date-api-snake-case-rename.md` to `todo/done/date-api-snake-case-rename.md` and append a closing note recording the deltas from the original proposal: flag-day (no aliases), `datetime`/`timedelta` spelled as single words, `weekday` (0-based) instead of `day_of_week`, `FormatDate`+`ParseDate` folded into bidirectional `datetime_string/3`, plus new `timestamp/2` and `datetime_string_iso/2`/`date_string_iso/2`. Note the external `clausify-domains`/`kit` sweep remains outstanding in that repo.

- [ ] **Step 2: Commit.**

```bash
git mv todo/date-api-snake-case-rename.md todo/done/date-api-snake-case-rename.md
# edit to append the closing note, then:
git add todo/done/date-api-snake-case-rename.md
git commit -m "todo: close date-api-snake-case-rename (implemented)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- Flag-day rename, no aliases → Task 1 (Global Constraints + rename map). ✓
- `datetime`/`timedelta` one word, `weekday` 0-based → Task 1 export block + `_weekday_2`. ✓
- `datetime_string/3` bidirectional, FORMAT last, replaces Format+Parse → Task 1 Step 3(b). ✓
- `timestamp/2` → Task 2. ✓
- `datetime_string_iso/2`, `date_string_iso/2` via isoformat/fromisoformat → Task 3. ✓
- Consumer sweep (test_date_time.py, transitive test, both fixtures, date_time.md + incidental docs) → Task 1 Steps 1,5–9. ✓
- Docstring update → Task 1 Step 3(d). ✓
- Out-of-scope (formalize_lib, date-max-min-ordinal, external domains) → not touched; recorded in Task 4 note. ✓

**Placeholder scan:** All code steps show complete code; all commands are exact with expected output. No TBD/"add error handling". ✓

**Type consistency:** `datetime_string(DATETIME, STRING, FORMAT)` order is consistent across module fn `_datetime_string_3(dt_obj, s, fmt, …)`, the unit tests, and the `.clausal` Tests. Dispatch fn names (`_weekday_2`, `_datetime_string_3`, `_timestamp_2`, `_datetime_string_iso_2`, `_date_string_iso_2`) match between implementation, exports, and test imports. ✓
