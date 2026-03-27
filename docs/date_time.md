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
# skip
Now(DT)        # DT = datetime.datetime.now()
NowUTC(DT)     # DT = datetime.datetime.now(UTC)
Today(D)       # D = datetime.date.today()
```

### Date/4 — Bidirectional

`Date(Year, Month, Day, DateObj)` — construct or decompose:

```clausal
# skip
# Construct
Date(2026, 3, 16, D)    # D = datetime.date(2026, 3, 16)

# Decompose
Date(Y, M, D, SomeDateObj)    # Y, M, D bound to components
```

### Time/4 — Bidirectional

`Time(Hour, Minute, Second, TimeObj)`:

```clausal
# skip
Time(14, 30, 0, T)      # T = datetime.time(14, 30, 0)
Time(H, M, S, T)      # decompose T into components
```

### DateTime/7 — Bidirectional

`DateTime(Year, Month, Day, Hour, Minute, Second, DtObj)`:

```clausal
# skip
DateTime(2026, 3, 16, 14, 30, 0, DT)
# DT = datetime.datetime(2026, 3, 16, 14, 30, 0)
```

### TimeDelta/3 — Bidirectional

`TimeDelta(Days, Seconds, TdObj)`:

```clausal
# skip
TimeDelta(7, 0, TD)     # TD = datetime.timedelta(days=7)
TimeDelta(D, S, TD)    # decompose TD into days and seconds
```

### DateAdd/3, DateSub/3

```clausal
# skip
DateAdd(DATE, DELTA, RESULT)    # RESULT = DATE + DELTA
DateSub(DATE, DELTA, RESULT)    # RESULT = DATE - DELTA
```

### DateDiff/3

```clausal
# skip
DateDiff(D1, D2, TD)    # TD = D1 - D2 (timedelta)
```

### FormatDate/3

```clausal
# skip
FormatDate(DT, "%Y-%m-%d", S)    # S = "2026-03-16"
```

### ParseDate/3

```clausal
# skip
ParseDate("2026-03-16", "%Y-%m-%d", DT)    # DT = datetime.datetime(...)
```

### DayOfWeek/2

```clausal
# skip
DayOfWeek(D, DOW)    # DOW = 0 (Monday) through 6 (Sunday)
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
