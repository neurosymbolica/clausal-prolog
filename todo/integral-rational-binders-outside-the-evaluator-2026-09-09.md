# Integral rationals: which binders present them as int, and what is still out of scope

Context: fix/normalise-integral-rationals-2026-09-09. `'is'(X, 4/2)` used to bind
`Fraction(2, 1)`, which `'=='`/`compare/3` place in a different kind from `2` while
`unify` conflates them. The invariant now is "no evaluated expression yields an
integral Fraction, and no binder hands one to a logic variable":

- `clpfd._eval_ground` normalises at its single return (and at Fraction leaves), so
  `is/2`, the six ISO comparisons, `between/3` and the constraint-side `_resolve`
  all inherit it.
- `clpq._present` is applied at EVERY `unify(...)` site in clpq.py: the two `q_eq`
  fast paths (which re-wrapped the value as `Fraction(r)` and were the real-world
  site for `Q == TOTAL / 4`), `_post_q_domain`'s pinched interval, the tableau's
  `check_implied_bindings`, `_bind_optimal`, `sup`/`inf`/`maximize`/`minimize` and
  `int_minimize`'s result. Tableau arithmetic itself stays Fraction.
- `clpz3.z3_to_python` returns int for a whole Real.

Out of scope, decide later:

1. **Bindings the census cannot see.** The unify census counts a SUCCESSFUL compare
   of two ground numbers of different types. A Fraction bound TO A VARIABLE never
   reaches that compare (the variable side binds; a Q/FD attribute hook resolves the
   rest inside `__unify__`), so "0 conflations" says nothing about whether an integral
   Fraction reached a variable. The instrument that found the `q_eq` re-wrap was a
   `fractions.Fraction.__new__` tap filtered by numerator (see the test module's
   docstring). If this class of defect recurs, the durable instrument is a debug
   assertion at `_present`'s callers or a tap on `unify`'s value argument, not the
   census.
2. **Python callers binding a Fraction directly.** `unify(x, Fraction(2, 1), trail)`
   from Python, or a `Fraction(2, 1)` literal inside a term that is never evaluated,
   is untouched: `'=='(Fraction(2, 1), 2)` stays false, which is the standard order
   speaking. Whether `_q_hook` / `_fd_hook` should present such a binding (they
   already ACCEPT it — `_fd_hook` converts an integral Fraction for the domain check)
   is a design question, not a bug.
3. **Tabling answer keys.** `_normalize_for_key_py` / `do_normalize` keep the
   A01-D001 residual (Fraction/Decimal untagged, so `Fraction(2, 1)` and `2` dedup
   together while `'=='` says they differ). Filed separately as
   todo/a01-d001-tabling-half-2026-09-09.md; with binders presenting ints the residual
   is reached only by case 2 above.
4. **Input direction.** `clpz3.py` builds `Fraction(val).limit_denominator(...)` to
   FEED Z3 (`python_to_z3`); that is not a binder and needs nothing.
