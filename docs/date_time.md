# Date & Time Module

The `date_time` standard library module provides relational predicates for constructing, decomposing, and manipulating dates and times. All predicates work with **real Python datetime objects** — not custom term types.

The implementation lives in `clausal/modules/py/datetime.py`.

---

## Import

```clausal
-import_from(date_time, [now, today, date, time, datetime,
                         timedelta, date_add, date_sub, date_diff,
                         days_between, datetime_string,
                         date_of, weekday, date_between, timestamp,
                         datetime_string_iso, date_string_iso])
```

Or via [module import](import.md):

```clausal
-import_module(date_time)
# then use date_time.now(...), date_time.date(...), etc.
```

---

## Python Interop

All predicates produce and consume standard Python objects:

| Predicate | Python type |
|---|---|
| `date/4` | `datetime.date` |
| `time/4` | `datetime.time` |
| `datetime/7` | `datetime.datetime` |
| `timedelta/3` | `datetime.timedelta` |

Unification uses Python's native `==`. Any datetime method can be called via [`++()`](python_integration.md) interop:

```clausal
-import_from(date_time, [date, datetime_string])

IsoDate(Y, M, D, S) <- (
    date(Y, M, D, DT),
    S is ++DT.isoformat()
)
```

!!! tip "Prefer the declarative predicates over `++` escapes"

    `++()` drops into arbitrary Python and is reserved for last-resort interop. The common date operations all have clean, relational equivalents — reach for these first:

    | Instead of `++` … | Use |
    |---|---|
    | `S is ++DT.isoformat()` | `datetime_string(DT, S, "%Y-%m-%d")` |
    | `N is ++TD.days` | `timedelta(N, _, TD)` |
    | `D is ++DT.date()` | `date_of(DT, D)` |
    | `date_diff(A, B, TD), N is ++TD.days` | `days_between(A, B, N)` |

---

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

## Predicates

### now/1, now_utc/1, today/1

```clausal
--8<-- "tests/fixtures/docs/date_time_sigs.txt:now_today"
```

### date/4 — Bidirectional

`date(Year, Month, Day, DateObj)` — construct or decompose:

```clausal
--8<-- "tests/fixtures/docs/date_time_sigs.txt:date_examples"
```

### time/4 — Bidirectional

`time(Hour, Minute, Second, TimeObj)`:

```clausal
--8<-- "tests/fixtures/docs/date_time_sigs.txt:time_examples"
```

### datetime/7 — Bidirectional

`datetime(Year, Month, Day, Hour, Minute, Second, DtObj)`:

```clausal
--8<-- "tests/fixtures/docs/date_time_sigs.txt:datetime_example"
```

### timedelta/3 — Bidirectional

`timedelta(Days, Seconds, TdObj)`:

```clausal
--8<-- "tests/fixtures/docs/date_time_sigs.txt:timedelta_examples"
```

### date_add/3, date_sub/3

```clausal
--8<-- "tests/fixtures/docs/date_time_sigs.txt:date_add_sub"
```

### date_diff/3

```clausal
--8<-- "tests/fixtures/docs/date_time_sigs.txt:date_diff"
```

### days_between/3

`days_between(DateA, DateB, N)` — the whole-day count of `DateA - DateB` as a plain integer, so the common "days between two dates" need is a single goal instead of `date_diff(A, B, TD), timedelta(N, _, TD)`:

```clausal
--8<-- "tests/fixtures/docs/date_time_sigs.txt:days_between"
```

### datetime_string/3

```clausal
--8<-- "tests/fixtures/docs/date_time_sigs.txt:datetime_string"
```

### date_of/2 — Bidirectional

`date_of(DateTime, Date)` — the declarative form of `++DT.date()`. Forward, it extracts the calendar `datetime.date` from a `datetime.datetime`; in reverse (with `DateTime` unbound) it builds the midnight datetime of a `datetime.date`:

```clausal
--8<-- "tests/fixtures/docs/date_time_sigs.txt:date_of"
```

### weekday/2

```clausal
--8<-- "tests/fixtures/docs/date_time_sigs.txt:weekday"
```

### timestamp/2 — Bidirectional

`timestamp(DateTime, Stamp)` — convert between a `datetime.datetime` and a POSIX epoch float:

```clausal
--8<-- "tests/fixtures/docs/date_time_sigs.txt:timestamp"
```

Forward (DateTime bound to a `datetime`): Stamp = `DateTime.timestamp()` (float seconds since epoch). With Stamp already bound this acts as a check. Inverse (DateTime unbound, Stamp a number): DateTime = `datetime.fromtimestamp(Stamp)`. A plain `date` has no `timestamp()`, so the forward direction requires a `datetime` — pass a `datetime` object or use `datetime/7` to construct one first.

### datetime_string_iso/2, date_string_iso/2 — Bidirectional ISO-8601

Bidirectional ISO-8601 string conversion without a format argument:

```clausal
--8<-- "tests/fixtures/docs/date_time_sigs.txt:iso"
```

`datetime_string_iso/2` forward requires a `datetime.datetime` and produces the full ISO-8601 string via `isoformat()`; inverse (datetime unbound, string bound) parses via `fromisoformat`. `date_string_iso/2` forward requires a plain `datetime.date` (a `datetime` is rejected — use `date_of/2` first if needed) and produces `YYYY-MM-DD`; inverse parses via `date.fromisoformat`. Both predicates catch `(TypeError, ValueError)` and fail cleanly; both-unbound fails.

### date_between/3 — Nondeterministic

`date_between(Start, End, D)` — generates each date in the range [Start, End]:

```clausal
-import_from(date_time, [date, date_between])

WeekDates(START, END, D) <- date_between(START, END, D)
```

This is nondeterministic — it succeeds once for each date in the range via [backtracking](control.md).

---

??? info "Test coverage"

    Tests are in `tests/test_date_time.py`.

    - **now/now_utc/today**: current timestamps
    - **date/4**: construct, decompose, invalid values
    - **time/4**: construct, decompose
    - **datetime/7**: construct, decompose
    - **timedelta/3**: construct, decompose
    - **date_add/date_sub/date_diff**: arithmetic
    - **days_between**: direct integer day count
    - **datetime_string**: bidirectional strftime/strptime
    - **date_of**: datetime ↔ date (both modes)
    - **weekday**: weekday computation
    - **date_between**: date range enumeration
    - **timestamp**: bidirectional datetime ↔ POSIX epoch
    - **datetime_string_iso/date_string_iso**: bidirectional ISO-8601 helpers

---

*See also: [I/O](io.md) — writing and formatting output · [Python Interop](python_integration.md) — `++()` escape for additional datetime operations.*
