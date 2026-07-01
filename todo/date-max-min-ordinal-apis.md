# date_time: clean predicates for max/min/ordinal (the last ++ date escapes)

**Why:** migrating the clausify gold rulebases off `++` date escapes retired every `++DT.date()` /
`++TD.days` / `++DT.isoformat()` (now `DateOf` / `DaysBetween` / `FormatDate`). Three date `++` escapes
remain **only because no clean predicate exists** — all in `eu/schengen-90-180/schengen.clausal`:

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
      then map back) that schengen uses for exact day-of-presence de-duplication.

## Done when
- [ ] `grep -rnE '\+\+' /workspace/clausify-domains/*/*/*.clausal` (excluding comments/tests) is empty —
      no everyday date `++` escapes anywhere in the golds.
- [ ] `schengen.clausal` `date_max`/`date_min`/`day_ordinals` use the new predicates; conformance +
      the 26/26 oracle score unchanged.

Context: gold date-API migration (clausify `5cab886`); the primary date todo `date-clean-apis.md`
(already done) covered date/days/isoformat.
