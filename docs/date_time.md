# Date & Time Module

The `date_time` standard library module provides relational predicates for constructing, decomposing, and manipulating dates and times. A date, time, datetime or duration is an ordinary **term** — a cell such as `date(2026, 3, 16)`, which Python sees as the tuple `('date', 2026, 3, 16)`. The predicates compute with Python's `datetime` module internally, but they take and give back terms, never `datetime` objects.

The implementation lives in `clausal/modules/py/datetime.py`. Clausal Prolog
imports it through its facade, `library(datetime)`.

Examples on this page are [Clausal Prolog](clausal_prolog.md) (`.clausal`):
ISO Prolog syntax, without cut. (The [seam](syntax.md), Clausal's
Python-syntax surface, imports the module as `date_time`; the page notes
where the seam behaves differently.)

---

## Import

```clausal
:- use_module(library(datetime), [now/1, now_utc/1, today/1, time/4,
                                  datetime/7, timedelta/3, date_add/3,
                                  date_sub/3, date_diff/3, days_between/3,
                                  datetime_string/3, date_of/2, weekday/2,
                                  date_between/3, timestamp/2,
                                  datetime_string_iso/2, date_string_iso/2,
                                  date_max/3, date_min/3, ordinal/2]).
```

Or import every predicate the module exports:

```clausal
:- use_module(library(datetime)).
```

There is no `date/3` to import: a date is a term (next section). (The seam
imports `-import_from(date_time, [now, today, date, ...])`, where `date` is a
validating constructor, or the whole module, `-import_module(date_time)`,
calling `date_time.now(...)`; see [module import](import.md).)

---

## The terms

| Term | Python value it stands for |
|---|---|
| `date(Year, Month, Day)` | `datetime.date` |
| `time(Hour, Minute, Second, Microsecond)` | `datetime.time` |
| `datetime(Year, Month, Day, Hour, Minute, Second, Microsecond)` | naive `datetime.datetime` (a tz-aware one carries a ninth argument, the UTC offset in seconds) |
| `timedelta(Days, Seconds, Microseconds)` | `datetime.timedelta` |

`date(Y, M, D)` is a term, not a goal: write `D = date(2026, 3, 16)` to build
one and `date(Y, M, DAY) = D` to take one apart — both are plain
unification. Building the term checks nothing; the first predicate that
reads an impossible date raises `domain_error(date, …)` instead of
computing with a bogus term:

```
D = date(2025, 2, 29), date_add(D, timedelta(1, 0, 0), R)
% error(domain_error(date,date(2025,2,29)),date_add/3)
```

Wrap it in `catch/3` if a caller wants failure instead. (In the seam,
importing `date` validates the ground form when it is built:
`D is date(2025, 2, 29)` raises `error(domain_error(date,date(2025,2,29)),date/3)`.)

To call a Python `datetime` method, convert explicitly with
[`to_python`](python_integration.md), which turns a date term into the
`datetime` object. That needs the seam's `++` escape into Python, which
Clausal Prolog does not have, so this example is seam:

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

    In the seam, `++()` drops into arbitrary Python and is reserved for last-resort interop; Clausal Prolog has no `++` at all. The common date operations all have clean, relational equivalents — reach for these first:

    | Instead of the seam's `++` … | Use |
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

`date`, `time`, and `datetime` terms of the same kind are ordered
chronologically by the standard order of terms — `@<`, `@>`, `@=<`, `@>=`
and `compare/3` — because their arguments run from the largest unit to the
smallest:

```clausal
earlier(A, B) :-
    A = date(2020, 12, 1),
    B = date(2021, 1, 1),
    A @< B.

test("earlier") :-
    earlier(_, _).
```

The same terms sort chronologically through `sort/2`, `msort/2`,
`min_list/2`, and `max_list/2`. The ISO arithmetic comparisons (`<`, `>`,
`=<`, `>=`) evaluate their arguments, so `date(2020, 1, 1) < date(2021, 1, 1)`
raises `error(type_error(evaluable, date/3), (is)/2)`. (The seam's `<`, `>`,
`<=`, `>=` compare date terms chronologically.)

Only terms of the same kind should be compared. `min_list/2` and
`max_list/2` raise `type_error(orderable, List)` for a list that mixes
dates and numbers; `catch/3` intercepts it and binds the error term:

```clausal
latest(DATES, LATEST) :-
    catch(max_list(DATES, LATEST), ERROR, (writeln(ERROR), fail)).

test("latest of dates") :-
    latest([date(2021, 1, 1), date(2020, 5, 1)], LATEST),
    LATEST == date(2021, 1, 1).

test("a date and a number do not mix") :-
    catch(max_list([date(2021, 1, 1), 5], _), E, true),
    E == error(type_error(orderable, [date(2021, 1, 1), 5]), max_list/2).
```

The standard order never raises, but across kinds it is not chronological:
it sorts a number before every compound term, and a `date` (arity 3) before
every `datetime` (arity 7), so `date(2030, 1, 1) @< DT` holds for a
`datetime` in 2020. Convert with `date_of/2` first.

---

## Predicates

### now/1, now_utc/1, today/1

```text
--8<-- "tests/fixtures/docs/date_time_sigs.txt:now_today"
```

### date/3 — the date term

`date(Year, Month, Day)` is the date itself; unification constructs and decomposes it:

```text
--8<-- "tests/fixtures/docs/date_time_sigs.txt:date_examples"
```

### time/4 — Bidirectional

`time(Hour, Minute, Second, TimeObj)`:

```text
--8<-- "tests/fixtures/docs/date_time_sigs.txt:time_examples"
```

### datetime/7 — Bidirectional

`datetime(Year, Month, Day, Hour, Minute, Second, DtObj)`:

```text
--8<-- "tests/fixtures/docs/date_time_sigs.txt:datetime_example"
```

A component of the right type but no such value raises a domain error carrying the term, as `date/3` does: `time(25, 0, 0, T)` is `domain_error(time, time(25, 0, 0))` and `datetime(2026, 13, 1, 0, 0, 0, DT)` is `domain_error(datetime, datetime(2026, 13, 1, 0, 0, 0))`.

### timedelta/3 — Bidirectional

`timedelta(Days, Seconds, TdObj)`:

```text
--8<-- "tests/fixtures/docs/date_time_sigs.txt:timedelta_examples"
```

### date_add/3, date_sub/3

```text
--8<-- "tests/fixtures/docs/date_time_sigs.txt:date_add_sub"
```

### date_diff/3

```text
--8<-- "tests/fixtures/docs/date_time_sigs.txt:date_diff"
```

### days_between/3

`days_between(DateA, DateB, N)` — the whole-day count of `DateA - DateB` as a plain integer, so the common "days between two dates" need is a single goal instead of `date_diff(A, B, TD), timedelta(N, _, TD)`:

```text
--8<-- "tests/fixtures/docs/date_time_sigs.txt:days_between"
```

### datetime_string/3

```text
--8<-- "tests/fixtures/docs/date_time_sigs.txt:datetime_string"
```

### date_of/2 — Bidirectional

`date_of(DateTime, Date)` — the declarative form of the seam's `++to_python(DT).date()`. Forward, it extracts the calendar `date` from a `datetime`; in reverse (with `DateTime` unbound) it builds the midnight `datetime` of a `date`:

```text
--8<-- "tests/fixtures/docs/date_time_sigs.txt:date_of"
```

### date_max/3, date_min/3

`date_max(D1, D2, M)` / `date_min(D1, D2, M)` — `M` is the later (resp. earlier) of two dates or datetimes. A date/datetime mix is not comparable and raises a `type_error` on the second argument (`date_max(date(2026,3,16), datetime(2026,3,16,9,0,0,0), M)` is `type_error(date, datetime(2026,3,16,9,0,0,0))`: the first argument fixes the type); a naive with an aware datetime raises `domain_error(naive_datetime, DT)` (or `aware_datetime`). `date_diff/3`, `days_between/3` and `date_between/3` raise the same:

```text
--8<-- "tests/fixtures/docs/date_time_sigs.txt:date_max_min"
```

### ordinal/2 — Bidirectional

`ordinal(Date, N)` — the proleptic-Gregorian day number (Python's `toordinal()`). Forward binds `N` (a datetime contributes its calendar day's ordinal); in reverse (`Date` unbound) it builds the `date` term for day `N` (an `N` outside 1..3652059 raises `domain_error(ordinal, N)`), so enumerating every calendar day in `[CS, CE]` is `ordinal(CS, A), ordinal(CE, B), numlist(A, B, Ns)` mapped back through the inverse mode:

```text
--8<-- "tests/fixtures/docs/date_time_sigs.txt:ordinal"
```

### weekday/2

```text
--8<-- "tests/fixtures/docs/date_time_sigs.txt:weekday"
```

### timestamp/2 — Bidirectional

`timestamp(DateTime, Stamp)` — convert between a `datetime` term and a POSIX epoch float:

```text
--8<-- "tests/fixtures/docs/date_time_sigs.txt:timestamp"
```

Forward (DateTime bound to a `datetime` term): Stamp = the float seconds since the epoch. With Stamp already bound this acts as a check. Inverse (DateTime unbound, Stamp a number): DateTime is the local-time `datetime` for that stamp. A plain `date` has no timestamp, so the forward direction requires a `datetime` — use `datetime/7` to construct one first.

### datetime_string_iso/2, date_string_iso/2 — Bidirectional ISO-8601

Bidirectional ISO-8601 string conversion without a format argument:

```text
--8<-- "tests/fixtures/docs/date_time_sigs.txt:iso"
```

`datetime_string_iso/2` forward requires a `datetime` term and produces the full ISO-8601 string; inverse (datetime unbound, string bound) parses it. `date_string_iso/2` forward requires a `date` term (a `datetime` is rejected — use `date_of/2` first if needed) and produces `YYYY-MM-DD`; inverse parses it. Text that does not parse raises `syntax_error(invalid_datetime)` / `syntax_error(invalid_date)` (ruled 2026-10-02); text that parses but names no date (`"2026-13-01"`) raises `domain_error(iso_datetime, S)` / `domain_error(iso_date, S)`; a wrong kind of term raises `type_error` (`date_string_iso(DT, S)` with a `datetime` is `type_error(date, datetime(...))`), and both arguments unbound raises `instantiation_error` (see [Wrong-type arguments raise](python_integration.md#what-the-py-wrappers-accept-and-answer)).

### date_between/3 — Nondeterministic

`date_between(Start, End, D)` — generates each date in the range [Start, End]:

```clausal
:- use_module(library(datetime), [date_between/3]).

week_dates(START, END, D) :-
    date_between(START, END, D).

% D = date(2026, 3, 16); date(2026, 3, 17); date(2026, 3, 18)
march_16_to_18(D) :-
    date_between(date(2026, 3, 16), date(2026, 3, 18), D).

test("three dates") :-
    findall(D, march_16_to_18(D), DS),
    DS == [date(2026, 3, 16), date(2026, 3, 17), date(2026, 3, 18)].
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

*See also: [I/O](io.md) — writing and formatting output · [Python Interop](python_integration.md) — the seam's `++()` escape for additional datetime operations.*
