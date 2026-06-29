# Date & Time Module

The `date_time` standard library module provides relational predicates for constructing, decomposing, and manipulating dates and times. All predicates work with **real Python datetime objects** — not custom term types.

The implementation lives in `clausal/modules/date_time.py`.

---

## Import

```clausal
-import_from(date_time, [Now, Today, Date, Time, DateTime,
                         TimeDelta, DateAdd, DateSub, DateDiff,
                         DaysBetween, FormatDate, ParseDate,
                         DateOf, DayOfWeek, DateBetween])
```

Or via [module import](import.md):

```clausal
-import_module(date_time)
# then use date_time.Now(...), date_time.Date(...), etc.
```

---

## Python Interop

All predicates produce and consume standard Python objects:

| Predicate | Python type |
|---|---|
| `Date/4` | `datetime.date` |
| `Time/4` | `datetime.time` |
| `DateTime/7` | `datetime.datetime` |
| `TimeDelta/3` | `datetime.timedelta` |

Unification uses Python's native `==`. Any datetime method can be called via [`++()`](python_integration.md) interop:

```clausal
-import_from(date_time, [Date, FormatDate])

IsoDate(Y, M, D, S) <- (
    Date(Y, M, D, DT),
    S is ++DT.isoformat()
)
```

!!! tip "Prefer the declarative predicates over `++` escapes"

    `++()` drops into arbitrary Python and is reserved for last-resort interop. The common date operations all have clean, relational equivalents — reach for these first:

    | Instead of `++` … | Use |
    |---|---|
    | `S is ++DT.isoformat()` | `FormatDate(DT, "%Y-%m-%d", S)` |
    | `N is ++TD.days` | `TimeDelta(N, _, TD)` |
    | `D is ++DT.date()` | `DateOf(DT, D)` |
    | `DateDiff(A, B, TD), N is ++TD.days` | `DaysBetween(A, B, N)` |

---

## Predicates

### Now/1, NowUTC/1, Today/1

```clausal
--8<-- "tests/fixtures/docs/date_time_sigs.txt:now_today"
```

### Date/4 — Bidirectional

`Date(Year, Month, Day, DateObj)` — construct or decompose:

```clausal
--8<-- "tests/fixtures/docs/date_time_sigs.txt:date_examples"
```

### Time/4 — Bidirectional

`Time(Hour, Minute, Second, TimeObj)`:

```clausal
--8<-- "tests/fixtures/docs/date_time_sigs.txt:time_examples"
```

### DateTime/7 — Bidirectional

`DateTime(Year, Month, Day, Hour, Minute, Second, DtObj)`:

```clausal
--8<-- "tests/fixtures/docs/date_time_sigs.txt:datetime_example"
```

### TimeDelta/3 — Bidirectional

`TimeDelta(Days, Seconds, TdObj)`:

```clausal
--8<-- "tests/fixtures/docs/date_time_sigs.txt:timedelta_examples"
```

### DateAdd/3, DateSub/3

```clausal
--8<-- "tests/fixtures/docs/date_time_sigs.txt:date_add_sub"
```

### DateDiff/3

```clausal
--8<-- "tests/fixtures/docs/date_time_sigs.txt:date_diff"
```

### DaysBetween/3

`DaysBetween(DateA, DateB, N)` — the whole-day count of `DateA - DateB` as a plain integer, so the common "days between two dates" need is a single goal instead of `DateDiff(A, B, TD), TimeDelta(N, _, TD)`:

```clausal
--8<-- "tests/fixtures/docs/date_time_sigs.txt:days_between"
```

### FormatDate/3

```clausal
--8<-- "tests/fixtures/docs/date_time_sigs.txt:format_date"
```

### ParseDate/3

```clausal
--8<-- "tests/fixtures/docs/date_time_sigs.txt:parse_date"
```

### DateOf/2 — Bidirectional

`DateOf(DateTime, Date)` — the declarative form of `++DT.date()`. Forward, it extracts the calendar `datetime.date` from a `datetime.datetime`; in reverse (with `DateTime` unbound) it builds the midnight datetime of a `datetime.date`:

```clausal
--8<-- "tests/fixtures/docs/date_time_sigs.txt:date_of"
```

### DayOfWeek/2

```clausal
--8<-- "tests/fixtures/docs/date_time_sigs.txt:day_of_week"
```

### DateBetween/3 — Nondeterministic

`DateBetween(Start, End, D)` — generates each date in the range [Start, End]:

```clausal
-import_from(date_time, [Date, DateBetween])

WeekDates(START, END, D) <- DateBetween(START, END, D)
```

This is nondeterministic — it succeeds once for each date in the range via [backtracking](control.md).

---

??? info "Test coverage"

    Tests are in `tests/test_date_time.py`.

    - **Now/NowUTC/Today**: current timestamps
    - **Date/4**: construct, decompose, invalid values
    - **Time/4**: construct, decompose
    - **DateTime/7**: construct, decompose
    - **TimeDelta/3**: construct, decompose
    - **DateAdd/DateSub/DateDiff**: arithmetic
    - **DaysBetween**: direct integer day count
    - **FormatDate/ParseDate**: strftime/strptime
    - **DateOf**: datetime ↔ date (both modes)
    - **DayOfWeek**: weekday computation
    - **DateBetween**: date range enumeration

---

*See also: [I/O](io.md) — writing and formatting output · [Python Interop](python_integration.md) — `++()` escape for additional datetime operations.*
