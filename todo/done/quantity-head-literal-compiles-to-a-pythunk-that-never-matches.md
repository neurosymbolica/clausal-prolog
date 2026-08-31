# A `value(unit)` amount in a clause HEAD compiles to a PyThunk and never matches

**RESOLVED 2026-08-31** on `fix/quantity-head-literal-pythunk` — direction 2
(hoist to a body `Unify`), not direction 1: `_is_structural_head_value`
(`clausal/logic/database.py`) now treats a `PyThunk` head arg as structural, so
`_normalize_structural_head_args` hoists it to Var + prepended
`Unify(var, thunk)` and the existing body compilation evaluates the thunk at
runtime — per call, preserving `++()` escape semantics, and working for
var-bearing thunks (f-strings) too, which assert-time forcing could not.
Second half found during the fix: `_lift_clause_at_pos`
(`clausal/logic/compiler/list_dispatch.py`) would lift that Unify back into the
head in argument-index buckets (the quantity clause keys `_INDEX_VAR` and is
merged into every bucket), and the lifted thunk's `$headlit` global is never
collected for bucket functions — so it now skips `PyThunk` like str/bytes and
`LoadName`. Both halves mutation-verified; units and currency spellings
covered by `tests/test_quantity_head_literal.py`.

**Filed:** 2026-07-30, found while fixing
`todo/done/headlit-global-not-injected-symbolic-diff-example.md` (adjacent
defect, deliberately not folded into that fix — different subsystem, different
seam).

A units/currency amount written in a clause **head** argument silently matches
nothing.  The same value in a **body** goal works, so the clause looks right and
just never fires.

## Repro (one clause, no indexing involved)

```clausal
-module(min9, [Len(AMOUNT, NAME), Chk(N)])
-import_from(py.units, [m])
-private([short_])

Len(5(m), short_) <- (number(1))

Chk(N) <- Len(5(m), N)
```

```
Chk(N)   ->  no solutions        # WRONG, expected N = short_
```

Control — move the amount out of the head and the same comparison succeeds:

```clausal
Len(A, short_) <- (A == 5(m))
Chk(N) <- Len(5(m), N)           # ->  N = short_
```

Reproduces identically for currency (`Price(7.89(euro), one_)` with
`-import_from(european_union, [euro])`) and at any clause count, so it is
independent of argument indexing.

## Mechanism

The head argument `5(m)` is compiled to a **`PyThunk`** (a deferred
`lambda`), not to the `Quantity` it denotes.  `PyThunk` is missing from the
exclusion list in `clausal/logic/compiler/terms_to_ast.py::_is_opaque_head_literal`
— it is not a `Var`, not a primitive, not one of the structural term types
enumerated there — so it is classified as a **ground opaque head literal** and
`head_match.py` emits the A02-F003 capture + `$headlit_<id>` unify guard against
the *thunk object itself*.  No runtime value ever equals or unifies with a
`PyThunk`, so the clause is dead.

Probe used:

```python
import clausal.logic.compiler.head_match as HM
_orig = HM.headlit_global_key
HM.headlit_global_key = lambda t: (print(type(t), repr(t)), _orig(t))[1]
# -> <class 'clausal.terms.PyThunk'> PyThunk(<function <lambda> ...>, ())
```

Note this is a **change of failure mode**, not a new one: before A02-F003
(`ca49b125`) the same head arg fell through to the accept-all wildcard, i.e. it
matched *every* caller instead of none.  Either way a `value(unit)` head arg has
never worked.

## Fix directions (not yet chosen)

1. Force/evaluate the thunk at assert time so the head carries the real
   `Quantity` — then the existing opaque-literal guard is correct and exact
   (`Quantity` compares by value).  Check what else relies on the head thunk
   staying deferred (`clausal/logic/database.py` normalisation, reification).
2. Or treat a `PyThunk` head arg like the other unresolved references
   `_lift_clause_at_pos` already refuses (`LoadName` / `Call(LoadName)`): hoist
   it to a body `Unify` so the runtime evaluates and unifies it.
3. Add `PyThunk` to `_is_opaque_head_literal`'s exclusion list regardless — a
   deferred computation is not a ground literal, and returning True there can
   only ever produce a dead clause.

A regression test belongs on the two-line units fixture above, not on a currency
example — the currency spelling is only the most likely way a user meets it.
