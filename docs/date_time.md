# Date & Time Module

The `date_time` standard library module provides relational predicates for constructing, decomposing, and manipulating dates and times. All predicates work with **real Python datetime objects** — not custom term types.

The implementation lives in `clausal/modules/date_time.py`.

---

## Import

```
-import_from(date_time, [Now, Today, Date, Time, DateTime,
                         TimeDelta, DateAdd, DateSub, DateDiff,
                         FormatDate, ParseDate, DayOfWeek,
                         DateBetween])
```

Or via module import:

```
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

Unification uses Python's native `==`. Any datetime method can be called via `++()` interop:

```
-import_from(date_time, [Date, FormatDate])

IsoDate(Y_, M_, D_, S_) <- (
    Date(Y_, M_, D_, Dt_)
    and S_ is ++Dt_.isoformat()
)
```

---

## Predicates

### Now/1, NowUTC/1, Today/1

```
Now(Dt_)        # Dt_ = datetime.datetime.now()
NowUTC(Dt_)     # Dt_ = datetime.datetime.now(UTC)
Today(D_)       # D_ = datetime.date.today()
```

### Date/4 — Bidirectional

`Date(Year, Month, Day, DateObj)` — construct or decompose:

```
# Construct
Date(2026, 3, 16, D_)    # D_ = datetime.date(2026, 3, 16)

# Decompose
Date(Y_, M_, D_, SomeDateObj_)    # Y_, M_, D_ bound to components
```

### Time/4 — Bidirectional

`Time(Hour, Minute, Second, TimeObj)`:

```
Time(14, 30, 0, T_)      # T_ = datetime.time(14, 30, 0)
Time(H_, M_, S_, T_)      # decompose T_ into components
```

### DateTime/7 — Bidirectional

`DateTime(Year, Month, Day, Hour, Minute, Second, DtObj)`:

```
DateTime(2026, 3, 16, 14, 30, 0, Dt_)
# Dt_ = datetime.datetime(2026, 3, 16, 14, 30, 0)
```

### TimeDelta/3 — Bidirectional

`TimeDelta(Days, Seconds, TdObj)`:

```
TimeDelta(7, 0, Td_)     # Td_ = datetime.timedelta(days=7)
TimeDelta(D_, S_, Td_)    # decompose Td_ into days and seconds
```

### DateAdd/3, DateSub/3

```
DateAdd(Date_, Delta_, Result_)    # Result_ = Date_ + Delta_
DateSub(Date_, Delta_, Result_)    # Result_ = Date_ - Delta_
```

### DateDiff/3

```
DateDiff(D1_, D2_, Td_)    # Td_ = D1_ - D2_ (timedelta)
```

### FormatDate/3

```
FormatDate(Dt_, "%Y-%m-%d", S_)    # S_ = "2026-03-16"
```

### ParseDate/3

```
ParseDate("2026-03-16", "%Y-%m-%d", Dt_)    # Dt_ = datetime.datetime(...)
```

### DayOfWeek/2

```
DayOfWeek(D_, Dow_)    # Dow_ = 0 (Monday) through 6 (Sunday)
```

### DateBetween/3 — Nondeterministic

`DateBetween(Start, End, D)` — generates each date in the range [Start, End]:

```
-import_from(date_time, [Date, DateBetween])

WeekDates(Start_, End_, D_) <- DateBetween(Start_, End_, D_)
```

This is nondeterministic — it succeeds once for each date in the range.

---

## Test Coverage

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
