# date_time: clean APIs so users never need `++` Python escapes for dates

**Why:** `++(expr)` drops into arbitrary Python and is reserved for last-resort interop, throwaway,
and debugging — not for everyday declarative code. Today the date examples everyone copies are *all*
`++` escapes (`++DT.date()`, `++TD.days`, `++DT.isoformat()`). This both reads badly and caused a real
formalization bug: a model wrote `deadline(...) <- (ParseDate(REF,…,REF_D), REF is ++REF_D.date(), …)`
and then mishandled the string↔date boundary, failing its own tests. The fix is to make the clean,
declarative API cover every common date operation so the `++` escapes are never needed.

**Module:** `site/date_time` · **Docs:** `docs/date_time.md` · **Tests:** `tests/test_date_time.py`

## Current API (already declarative — no change needed, just USE it)
- `FormatDate/3` — date/datetime → string. **Already covers `++DT.isoformat()`** (`FormatDate(D, "%Y-%m-%d", S)`).
- `TimeDelta/3` is **bidirectional** — reverse mode extracts the parts. **Already covers `++TD.days`**
  (`TimeDelta(DAYS, _, TD)` decomposes a delta). So `DateDiff(A,B,TD), TimeDelta(N,_,TD)` gives the day count
  with no escape.
- `ParseDate/3`, `DateAdd/3`, `DateSub/3`, `DateDiff/3`, `Date/4`, `DateTime/7`, `DayOfWeek/2`, `DateBetween/3`.

## The one genuine gap → add it
`++DT.date()` (datetime → date) has **no clean equivalent**. `ParseDate` returns a `datetime.datetime`,
so every "parse an ISO date then work in dates" pattern reaches into Python. Pick one (maintainer's call):

- [x] **`DateOf/2`** — `DateOf(DateTime, Date)`, bidirectional where sensible: extract the `datetime.date`
      from a `datetime.datetime` (and the inverse: midnight datetime from a date). Most surgical. **CHOSEN.**
- [ ] *or* a **date-returning parse** — e.g. `ParseDate` yields a `datetime.date` when the format has no
      time fields, or a sibling `ParseDateOnly/3`. (Bigger behavioural change; weigh against existing users.)
      *Not chosen — DateOf is more surgical and leaves existing ParseDate users untouched.*

## Convenience worth adding (optional, removes the DateDiff+decompose dance)
- [x] **`DaysBetween/3`** — `DaysBetween(DateA, DateB, N)` → integer day count directly, so the common
      "days between two dates" need is a single declarative goal (no `DateDiff`+`TimeDelta` two-step).

## Tasks
- [x] Implement the chosen predicate(s) in `site/date_time`.
- [x] Tests in `tests/test_date_time.py` — round-trip + the schengen-style "parse ISO → date → diff" path,
      asserting **no `++` needed**.
- [x] Update `docs/date_time.md`: document the new predicate(s); add a "prefer these over `++X.date()` /
      `++TD.days` / `++X.isoformat()`" note.

**Downstream:** once this lands, the clausify cheat-sheet + primers get swept to use the clean APIs —
see `/workspace/clausify/todo/cheatsheet-remove-python-escapes.md` (that todo is **gated on this one**).

**Adjacent (separate todo, NOT this one):** schengen's current blocker is an engine limit
`terms_to_goalop: goal shape not yet supported (AttVar)` — a `==`/CLP attributed-variable goal shape.
Unrelated to dates; log separately if not already tracked. *(Resolved — see
`todo/done/attvar-in-goal-position.md`: a bare variable in goal position is now a clean, located
compile-time error.)*

## Resolution — RESOLVED 2026-06-29

Implemented (maintainer's choices: **DateOf/2** for the date-extraction gap, and **DaysBetween/3** as the
convenience):

- **`clausal/modules/py/datetime.py`**
  - `DateOf/2` — `DateOf(DateTime, Date)`, bidirectional. Forward: `datetime.datetime` → `datetime.date`
    (replaces `++DT.date()`); with `Date` bound it acts as a check. Inverse (`DateTime` unbound,
    `Date` a `datetime.date`): midnight datetime of that date. Fails on both-unbound or a non-datetime
    first arg.
  - `DaysBetween/3` — `DaysBetween(A, B, N)`, `N = (A - B).days` (whole days, consistent with
    `DateDiff` + `TimeDelta` decomposition); with `N` bound it acts as a check.
  - Both registered + exported; module docstring import list and "prefer declarative over `++`" note added.
- **Tests** — `tests/test_date_time.py`: `TestDateOf` (6) + `TestDaysBetween` (7) covering both modes,
  check modes, and failure modes; adapter-dispatch assertions. `tests/fixtures/docs/date_time_sig_tests.clausal`:
  DateOf forward/inverse, DaysBetween, and the schengen-style **parse ISO → DateOf → DaysBetween with no
  `++` escapes** path. 79 Python + 19 clausal tests pass.
- **Docs** — `docs/date_time.md`: new `DateOf/2` and `DaysBetween/3` sections, import list, and a
  "Prefer the declarative predicates over `++` escapes" table (isoformat→FormatDate, TD.days→TimeDelta,
  DT.date()→DateOf, DateDiff+decompose→DaysBetween). Snippet sources in
  `tests/fixtures/docs/date_time_sigs.txt` (`days_between`, `date_of`).

The existing API already covered the other two escapes (`++TD.days` via `TimeDelta(N,_,TD)`,
`++DT.isoformat()` via `FormatDate`) — no code change needed there, just the docs note steering users to them.

**Downstream now unblocked:** `/workspace/clausify/todo/cheatsheet-remove-python-escapes.md` (was gated on
this) can sweep the clausify cheat-sheet + primers to the clean APIs.
