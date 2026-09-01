# Accept `datetime.date` (and friends) as a first-class query-arg term type

**Requested:** 2026-07-03, during the EU-corpus date-domain work. Passing a raw Python
`datetime.date` as a query argument fails:

```
term_to_ast_expr: unsupported term type date
```

so the corpus interface uses `[YEAR, MONTH, DAY]` integer triples + `Date/4` to reconstruct the
date inside the rulebase. That works, but the triple↔`Date/4` dance is pure ceremony for the
Python-interop path (oracles, tests, hand-written drivers). There is no fundamental barrier to
accepting a `date` term directly.

## Root cause — a whitelist omission in ONE compile-time function
The engine's **runtime already treats `datetime.date` as a first-class term**: `Date/4` produces a
real `datetime.date` bound to a variable, and `DaysBetween`/`DateBetween`/`DateAdd` consume them —
they unify and flow through the trail fine. The rejection is only in the *input-lowering* path:

`clausal/logic/compiler/terms_to_ast.py :: term_to_ast_expr(term, var_context, *, eval_arith)`
lowers a query-arg term VALUE into a Python AST expression that reconstructs it at runtime. It has
explicit cases for `Var`, `LoadName`/`LoadAttr`, `bool`/`None` (→ `ast.Constant`), ints/strings/
`Fraction`, lists, `Compound`, functor dataclasses — and **no case for `date`**, so it falls
through to the `unsupported term type` error.

## Fix (~a dozen lines)
Add a case in `term_to_ast_expr` for `datetime.date` (and optionally `datetime.datetime`, `time`,
`timedelta`) that emits an AST reconstructing the value at runtime, either:
- a `Call` node `datetime.date(Y, M, D)` (import `datetime` in the compiled module namespace), or
- stash the object in the compiled function's globals and reference it by name — the file already
  uses this pattern for some values (see `clausal/logic/solve.py:311` "so that term_to_ast_expr can
  reference them in the compiled code").

## Semantics to get right (all already satisfied by `date`)
- **Unify by VALUE, not identity** (unlike atoms). `date` is immutable, hashable, with correct
  `__eq__`/`__hash__`, so it slots into the unification store and tabling/WFS hashing exactly like an
  int. (A `date` term and a `[Y,M,D]` list must NOT unify — they're different terms.)
- **Keep it OUT of CLP(ℤ/ℚ) arithmetic** — a bare `date` is not a number; `==` on it stays
  unification/equality, not an arithmetic constraint. The `date_time` predicates already provide the
  arithmetic (`DaysBetween`, etc.).
- **Reflection / printing**: `date` has a clean `repr`; make sure term-inspection handles it.

## Test
```python
from datetime import date
# with a rulebase clause  same_day(D, D)  (D unbound, unifies two args)
solve(m.same_day(date(2024,1,1), X))            # X = date(2024,1,1)
solve(m.same_day(date(2024,1,1), date(2024,1,1)))  # succeeds
solve(m.same_day(date(2024,1,1), date(2024,1,2)))  # fails
# and a rulebase using date_time on a passed-in date:
#   window(REF_DATE, N) <- DaysBetween(REF_DATE, some_epoch, N)
solve(m.window(date(2024,6,1), N))              # N bound, no Date/4 reconstruction needed
```

## Scope note — `[Y,M,D]` does NOT fully go away
This helps the in-memory Python-interop path. It does NOT remove `[Y,M,D]` at **serialization**
boundaries: generated/JSON-persisted cases (e.g. the verifier's differential `case.inputs`, the
`interval_dedup` attack) aren't date-native — a `datetime.date` isn't JSON-serializable — so those
still encode `[Y,M,D]` (or ISO) and deserialize to `date` before the call. Migrating a rulebase's
public interface from `[Y,M,D]` to `date` args therefore means every caller (oracle, tests, engine
adapter) passes real dates, converting at the serialized boundary. Worth doing per-domain, opt-in,
not a blanket change.

## Related
- `todo/date-api-snake-case-rename.md` (date_time API → snake_case) — do the ergonomics together.
- Corpus convention today (the downstream corpus's authoring-conventions doc, "Corpus authoring"):
  `[Y,M,D]` triples + `Date/4`; update it if/when date-args land.

---

## CLOSED 2026-09-02 — shipped, both lowering paths

Implemented for `datetime.date`, naive `datetime`/`time`, and `timedelta`
(exact types only — a subclass may carry state the base constructor cannot
rebuild, so it keeps the honest fallthrough):

1. **Direct query args** (`clausal/logic/solve.py::_ground_value`): the four
   datetime types are parameterized like ints/strings — the OBJECT is bound
   at run time by reference. No reconstruction at all on this path, so
   tz-AWARE datetimes/times work here too, and 20 distinct dates reuse ONE
   compiled query (pinned).
2. **Nested occurrences** (`term_to_ast_expr`, which structural args still
   reach): a reconstruction branch emitting
   `__import__('datetime').date(Y, M, D)`-style calls — self-contained, no
   compiled-namespace dependency. tz-aware values fall through to the honest
   NotImplementedError on this nested path only.

Head-literal dates already worked (the A02-F003 `$headlit_<id>` opaque-literal
capture) — the gap really was only input lowering, as diagnosed above.

Semantics verified in `tests/test_date_query_args.py`: unify by value; a
`date` and a `[Y, M, D]` list do NOT unify; flows into
`days_between/3` (note: the API is snake_case now, and `date/4` is
`date(Y, M, D, DateObj)` — this todo predates the rename).

Not done here, per the scope note: serialization boundaries keep `[Y,M,D]`
(JSON), and per-domain corpus interface migration is downstream work.
