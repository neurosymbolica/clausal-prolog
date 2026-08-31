# date_time: clean predicates for max/min/ordinal (the last ++ date escapes)

**Why:** `date_max`/`date_min`/`day_ordinals` have no clean predicate, so callers still reach
for `++` escapes even after the rest of the date API was cleaned up elsewhere (`DateOf` /
`DaysBetween` / `FormatDate` already retired `++DT.date()` / `++TD.days` / `++DT.isoformat()`).
A representative caller, e.g. a rolling date-window rule:

```clausal
date_max(D1, D2, M) <- (M is ++max(D1, D2))     # earlier/later of two dates
date_min(D1, D2, M) <- (M is ++min(D1, D2))
day_ordinals(CS, CE, DAYS) <- (..., A is ++CS.toordinal(), B is ++CE.toordinal(), numlist(A,B,DAYS))
```

## Proposed predicates
- [ ] **`DateMax/3` / `DateMin/3`** — `DateMax(D1, D2, M)` binds `M` to the later (resp. earlier) of two
      dates. (Or a single `DateEarlier/2`/`DateLater/2` pair — maintainer's call.)
- [ ] **`Ordinal/2` — bidirectional** — `Ordinal(Date, N)`: forward, `N = Date.toordinal()`; reverse,
      builds the date from its proleptic-Gregorian ordinal. The reverse mode also cleans up the common
      "enumerate every calendar day in `[CS, CE]`" pattern (`Ordinal(CS,A), Ordinal(CE,B), numlist(A,B,Ns)`,
      then map back), which callers doing rolling date-window arithmetic need for exact
      day-of-presence de-duplication.

## Done when
- [ ] No caller needs a `++` escape for date max/min/ordinal conversion.
- [ ] A representative rolling date-window caller's `date_max`/`date_min`/`day_ordinals` use the
      new predicates instead of `++`; behaviour unchanged.

Context: the primary date todo `date-clean-apis.md` (already done) covered date/days/isoformat;
this is the remaining slice.

---

**CLOSED 2026-08-31 (engine side):** `date_max/3`, `date_min/3`, and
bidirectional `ordinal/2` shipped in `clausal/modules/py/datetime.py` with
tests + docs (date_time.md, builtins.md, sigs snippets). Chose the
`DateMax/DateMin` spelling from the two options offered. The remaining
"Done when" item — converting a representative rolling date-window caller's
`++` escapes — lives in the downstream corpus, not this repo; do it there
on next contact with those domains.
