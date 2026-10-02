# Date & Time Module

The `date_time` standard library module provides relational predicates for constructing, decomposing, and manipulating dates and times. A date, time, datetime or duration is an ordinary **term** — a cell such as `date(2026, 3, 16)`, which Python sees as the tuple `('date', 2026, 3, 16)`. The predicates compute with Python's `datetime` module internally, but they take and give back terms, never `datetime` objects.

The implementation lives in `clausal/modules/py/datetime.py`.

---

## Import

```seam
-import_from(date_time, [now, today, date, time, datetime,
                         timedelta, date_add, date_sub, date_diff,
                         days_between, datetime_string,
                         date_of, weekday, date_between, timestamp,
                         datetime_string_iso, date_string_iso,
                         date_max, date_min, ordinal])
```

Or via [module import](import.md):

```seam
-import_module(date_time)
# then use date_time.now(...), date_time.date_add(...), etc.
```

---

## The terms

| Term | Python value it stands for |
|---|---|
| `date(Year, Month, Day)` | `datetime.date` |
| `time(Hour, Minute, Second, Microsecond)` | `datetime.time` |
| `datetime(Year, Month, Day, Hour, Minute, Second, Microsecond)` | naive `datetime.datetime` (a tz-aware one carries a ninth argument, the UTC offset in seconds) |
| `timedelta(Days, Seconds, Microseconds)` | `datetime.timedelta` |

`date(Y, M, D)` is a term, not a goal: write `D is date(2026, 3, 16)` to build
one and `date(Y, M, DAY) is D` to take one apart — both are plain
unification. Importing `date` makes the ground form validated: an impossible
date raises `domain_error(date, …)` instead of building a bogus term:

```
D is date(2025, 2, 29)
% error(domain_error(date,date(2025,2,29)),date/3)
```

Wrap it in `catch/3` if a caller wants failure instead.

To call a Python `datetime` method, convert explicitly with
[`to_python`](python_integration.md), which turns a date term into the
`datetime` object:

```seam
-import_from(date_time, [date])
-import_from(clausal, [to_python])

iso_date(Y, M, D, S) <- (
    DT is date(Y, M, D),
    S is ++to_python(DT).isoformat()
)
```

`S` is the Python `str` `'2026-03-16'` — an atom. From Python,
`clausal.to_python(('date', 2026, 3, 16))` is `datetime.date(2026, 3, 16)`,
and `clausal.to_clausal` goes the other way.

!!! tip "Prefer the declarative predicates over `++` escapes"

    `++()` drops into arbitrary Python and is reserved for last-resort interop. The common date operations all have clean, relational equivalents — reach for these first:

    | Instead of `++` … | Use |
    |---|---|
    | `S is ++to_python(DT).isoformat()` | `datetime_string(DT, S, "%Y-%m-%d")` |
    | `N is ++to_python(TD).days` | `timedelta(N, _, TD)` |
    | `D is ++to_python(DT).date()` | `date_of(DT, D)` |
    | `date_diff(A, B, TD), timedelta(N, _, TD)` | `days_between(A, B, N)` |
    | `M is ++max(…)` / `++min(…)` | `date_max(D1, D2, M)` / `date_min(D1, D2, M)` |
    | `N is ++to_python(D).toordinal()` | `ordinal(D, N)` |

Text results (`datetime_string/3`, `datetime_string_iso/2`,
`date_string_iso/2`) are **strings**, and a format or ISO text argument is
written as a string: `datetime_string(date(2026, 3, 16), S, "%Y-%m-%d")`
gives `S = "2026-03-16"`.

---

## Ordering & comparison

`date`, `time`, and `datetime` terms are ordered chronologically by the
comparison operators — `<`, `>`, `<=`, `>=`:

```seam
-import_from(date_time, [date])

earlier(A, B) <- (A is date(2020, 1, 1), B is date(2021, 1, 1), A < B)  # succeeds
```

The same terms sort chronologically through `sort/2`, `msort/2`,
`min_list/2`, and `max_list/2`.

Only terms of the same kind should be compared. Comparing a date with a
number throws `error(type_error(orderable, 5), (<)/2)`, and `min_list/2` /
`max_list/2` raise `type_error(orderable, List)` for such a mix. `catch/3`
intercepts it and binds the error term:

```seam
-import_from(date_time, [date])

compare_safe(D, X) <- catch(
    (D < X),
    _Error,
    writeln(_Error)
)
```

Comparing a `date` with a `datetime` does **not** raise today and does not
compare chronologically (`date(2030, 1, 1) < DT` holds for a `datetime` in
2020): convert with `date_of/2` first.

---

## Predicates

### now/1, now_utc/1, today/1

```seam
--8<-- "tests/fixtures/docs/date_time_sigs.txt:now_today"
```

### date/3 — the date term

`date(Year, Month, Day)` is the date itself; unification constructs and decomposes it:

```seam
--8<-- "tests/fixtures/docs/date_time_sigs.txt:date_examples"
```

### time/4 — Bidirectional

`time(Hour, Minute, Second, TimeObj)`:

```seam
--8<-- "tests/fixtures/docs/date_time_sigs.txt:time_examples"
```

### datetime/7 — Bidirectional

`datetime(Year, Month, Day, Hour, Minute, Second, DtObj)`:

```seam
--8<-- "tests/fixtures/docs/date_time_sigs.txt:datetime_example"
```

### timedelta/3 — Bidirectional

`timedelta(Days, Seconds, TdObj)`:

```seam
--8<-- "tests/fixtures/docs/date_time_sigs.txt:timedelta_examples"
```

### date_add/3, date_sub/3

```seam
--8<-- "tests/fixtures/docs/date_time_sigs.txt:date_add_sub"
```

### date_diff/3

```seam
--8<-- "tests/fixtures/docs/date_time_sigs.txt:date_diff"
```

### days_between/3

`days_between(DateA, DateB, N)` — the whole-day count of `DateA - DateB` as a plain integer, so the common "days between two dates" need is a single goal instead of `date_diff(A, B, TD), timedelta(N, _, TD)`:

```seam
--8<-- "tests/fixtures/docs/date_time_sigs.txt:days_between"
```

### datetime_string/3

```seam
--8<-- "tests/fixtures/docs/date_time_sigs.txt:datetime_string"
```

### date_of/2 — Bidirectional

`date_of(DateTime, Date)` — the declarative form of `++to_python(DT).date()`. Forward, it extracts the calendar `date` from a `datetime`; in reverse (with `DateTime` unbound) it builds the midnight `datetime` of a `date`:

```seam
--8<-- "tests/fixtures/docs/date_time_sigs.txt:date_of"
```

### date_max/3, date_min/3

`date_max(D1, D2, M)` / `date_min(D1, D2, M)` — `M` is the later (resp. earlier) of two dates or datetimes, with no `++` escape. A date/datetime mix is not comparable and fails the goal:

```seam
--8<-- "tests/fixtures/docs/date_time_sigs.txt:date_max_min"
```

### ordinal/2 — Bidirectional

`ordinal(Date, N)` — the proleptic-Gregorian day number (Python's `toordinal()`). Forward binds `N` (a datetime contributes its calendar day's ordinal); in reverse (`Date` unbound) it builds the `date` term for day `N`, so enumerating every calendar day in `[CS, CE]` is `ordinal(CS, A), ordinal(CE, B), numlist(A, B, Ns)` mapped back through the inverse mode:

```seam
--8<-- "tests/fixtures/docs/date_time_sigs.txt:ordinal"
```

### weekday/2

```seam
--8<-- "tests/fixtures/docs/date_time_sigs.txt:weekday"
```

### timestamp/2 — Bidirectional

`timestamp(DateTime, Stamp)` — convert between a `datetime` term and a POSIX epoch float:

```seam
--8<-- "tests/fixtures/docs/date_time_sigs.txt:timestamp"
```

Forward (DateTime bound to a `datetime` term): Stamp = the float seconds since the epoch. With Stamp already bound this acts as a check. Inverse (DateTime unbound, Stamp a number): DateTime is the local-time `datetime` for that stamp. A plain `date` has no timestamp, so the forward direction requires a `datetime` — use `datetime/7` to construct one first.

### datetime_string_iso/2, date_string_iso/2 — Bidirectional ISO-8601

Bidirectional ISO-8601 string conversion without a format argument:

```seam
--8<-- "tests/fixtures/docs/date_time_sigs.txt:iso"
```

`datetime_string_iso/2` forward requires a `datetime` term and produces the full ISO-8601 string; inverse (datetime unbound, string bound) parses it. `date_string_iso/2` forward requires a `date` term (a `datetime` is rejected — use `date_of/2` first if needed) and produces `YYYY-MM-DD`; inverse parses it. Unparsable text fails the goal; a wrong kind of term raises `type_error` (`date_string_iso(DT, S)` with a `datetime` is `type_error(date, datetime(...))`), and both arguments unbound raises `instantiation_error` (see [Wrong-type arguments raise](python_integration.md#what-the-py-wrappers-accept-and-answer)).

### date_between/3 — Nondeterministic

`date_between(Start, End, D)` — generates each date in the range [Start, End]:

```seam
-import_from(date_time, [date, date_between])

week_dates(START, END, D) <- date_between(START, END, D)

march_16_to_18(D) <- date_between(date(2026, 3, 16), date(2026, 3, 18), D)
# D = date(2026, 3, 16); date(2026, 3, 17); date(2026, 3, 18)
```

This is nondeterministic — it succeeds once for each date in the range via [backtracking](control.md).

---

??? info "Test coverage"

    Tests are in `tests/test_date_time.py`.

    - **now/now_utc/today**: current timestamps
    - **date/3**: construct, decompose, invalid values
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
