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

- [ ] **`DateOf/2`** — `DateOf(DateTime, Date)`, bidirectional where sensible: extract the `datetime.date`
      from a `datetime.datetime` (and the inverse: midnight datetime from a date). Most surgical.
- [ ] *or* a **date-returning parse** — e.g. `ParseDate` yields a `datetime.date` when the format has no
      time fields, or a sibling `ParseDateOnly/3`. (Bigger behavioural change; weigh against existing users.)

## Convenience worth adding (optional, removes the DateDiff+decompose dance)
- [ ] **`DaysBetween/3`** — `DaysBetween(DateA, DateB, N)` → integer day count directly, so the common
      "days between two dates" need is a single declarative goal (no `DateDiff`+`TimeDelta` two-step).

## Tasks
- [ ] Implement the chosen predicate(s) in `site/date_time`.
- [ ] Tests in `tests/test_date_time.py` — round-trip + the schengen-style "parse ISO → date → diff" path,
      asserting **no `++` needed**.
- [ ] Update `docs/date_time.md`: document the new predicate(s); add a "prefer these over `++X.date()` /
      `++TD.days` / `++X.isoformat()`" note.

**Downstream:** once this lands, the clausify cheat-sheet + primers get swept to use the clean APIs —
see `/workspace/clausify/todo/cheatsheet-remove-python-escapes.md` (that todo is **gated on this one**).

**Adjacent (separate todo, NOT this one):** schengen's current blocker is an engine limit
`terms_to_goalop: goal shape not yet supported (AttVar)` — a `==`/CLP attributed-variable goal shape.
Unrelated to dates; log separately if not already tracked.
