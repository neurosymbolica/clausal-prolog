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

## DONE — closed 2026-09-01

Fixed by `7fd537b3 compiler: lower datetime values as constructor calls in term_to_ast_expr`,
which is exactly the whitelist omission this file named: `term_to_ast_expr` had no case for a
`datetime.date` appearing as a VALUE in a term being lowered into a compiled query, so it fell
through to `NotImplementedError: unsupported term type date`.

Resolved via the second of the two options proposed above — a constructor CALL against a name
injected into compiled globals (`$date(2021, 6, 30)`), not an `ast.Constant`, because
`ast.Constant` accepts only None/bool/int/float/complex/str/bytes/Ellipsis and `compile()` rejects
anything else. `datetime`, `time` and `timedelta` got the same treatment, as this file suggested
they optionally should.

This file's own three acceptance checks, re-run against `/workspace/clausal` on 2026-09-01 with a
module whose only clause is `same_day(D, D)`:

    same_day(date(2024,1,1), X)              -> X = datetime.date(2024, 1, 1)   binds
    same_day(date(2024,1,1), date(2024,1,1)) -> 1 solution                      unifies
    same_day(date(2024,1,1), date(2024,1,2)) -> 0 solutions                     fails

The **Scope note** above still stands and is not closed by this: `[Y,M,D]` remains at
SERIALIZATION boundaries, because a `datetime.date` is not JSON-serializable. Migrating a
rulebase's public interface to `date` args is still a per-domain, opt-in change.

Ordering was never part of this defect. A real `datetime.date` has always compared correctly; a
domain-local compound merely SPELLED `date(Y, M, D)` is a different term and was mis-ordered for
an unrelated reason — see `todo/done/msort-orders-compound-integer-args-as-strings.md`.
