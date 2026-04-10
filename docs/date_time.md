# Date & Time Module

The `date_time` standard library module provides relational predicates for constructing, decomposing, and manipulating dates and times. All predicates work with **real Python datetime objects** — not custom term types.

The implementation lives in `clausal/modules/date_time.py`.

---

## Import

```clausal
-import_from(date_time, [Now, Today, Date, Time, DateTime,
                         TimeDelta, DateAdd, DateSub, DateDiff,
                         FormatDate, ParseDate, DayOfWeek,
                         DateBetween])
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

### FormatDate/3

```clausal
--8<-- "tests/fixtures/docs/date_time_sigs.txt:format_date"
```

### ParseDate/3

```clausal
--8<-- "tests/fixtures/docs/date_time_sigs.txt:parse_date"
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
    - **FormatDate/ParseDate**: strftime/strptime
    - **DayOfWeek**: weekday computation
    - **DateBetween**: date range enumeration

---

*See also: [I/O](io.md) — writing and formatting output · [Python Interop](python_integration.md) — `++()` escape for additional datetime operations.*
