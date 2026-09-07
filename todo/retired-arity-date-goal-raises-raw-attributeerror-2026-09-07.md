# A `date/4` goal raises a raw AttributeError, not `existence_error(procedure, date/4)`

Found 2026-09-07 while diagnosing a downstream report of "'ModulePredicate' object is
not callable".
Reproduces on canonical `/workspace/clausal` (fdabe59f) and on the clone after
the date/3 commits were cherry-picked — it is pre-existing, not introduced here.

```
-import_from(date_time, [date])
Test("d4 goal") <- date(2024, 1, 1, E)
```

```
goal 1 of 1 raised:
  AttributeError: 'function' object has no attribute '_get_dispatch'
    clausal/logic/predicate.py:1468   return obj._get_dispatch()
```

`date/4` was retired on 2026-09-01 (canonical dc56b31c). Since then `date` is
the `_DatePattern` term class, and a 4-argument GOAL on it resolves to some
plain function (the positional constructor, presumably) that the goal
resolver then asks for `_get_dispatch`. The comment block right above
predicate.py:1468 says the resolver must produce "a clean, positioned one,
never a raw AttributeError" for an unknown arity — this path violates it.

Expected: `existence_error(procedure, date/4)` (ISO 7.4.2 / 8.7.1), so a
corpus module still written against `date(Y, M, D, OBJ)` gets a diagnostic
that names the arity instead of a Python attribute error. Two clone-only
tests (`tests/test_date_query_args.py`, `tests/test_tagged_terms.py`) hit
exactly this on 2026-09-07 and were migrated by hand.

Related: `docs/date_time.md` and `docs/python_integration.md` still document
`date(Year, Month, Day, DateObj)` on BOTH trees; canonical's 9eec2dcf
(2026-09-02) touched python_integration.md without removing it. Rewriting
those two docs for date/3 is its own item.
