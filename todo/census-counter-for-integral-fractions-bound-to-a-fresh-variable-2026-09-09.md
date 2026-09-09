# Unify census: add a second counter, "integral Fraction bound to a fresh variable"

Context: fix/normalise-integral-rationals-2026-09-09, review round 2. Not implemented
this round (no C change was made in that round; do it in its own change with a rebuild).

The existing census in `clausal/logic/variables/_variables.c` (`unify_census_start` /
`unify_census_stop` / `unify_census`) counts one thing: a SUCCESSFUL
`PyObject_RichCompareBool(t1, t2, Py_EQ)` between two dereferenced, non-variable,
non-container terms whose Python types differ and are both numbers. That is the
ground-vs-ground fallback path only. A value bound TO A VARIABLE never reaches it —
the variable branch binds and returns before the compare — so the census was blind to
every producer this branch fixed:

- `eval_(4/2, X)` (compiled `ArithEval` -> `$unify(X, Fraction(2, 1))`): `X` is fresh,
  the Fraction is bound, nothing is compared, census says 0.
- `q_eq`'s fast path (`unify(l, Fraction(r))` with `l` a fresh var): same.
- `z3_to_python` handing a whole Real to a fresh var: same.

The absence test in `tests/test_integral_rationals.py` therefore asserts the bound
value's TYPE directly and treats the census's 0 as a secondary check with a positive
control; it cannot rely on the census to catch a new producer.

Proposed instrument: on the var-binding path in `unify` (the branch that calls
`bind`/trails a fresh Var), when the census is on and the value's type is `Fraction`
with `denominator == 1`, increment a second counter, e.g. `integral_fraction_binds`,
and record the pair `"<var kind>/Fraction"` in `by_type_pair` (or a separate dict
`bound_integral_fractions`) so the two totals stay separable. Keep it on the census-ON
branch only: cost when disabled must stay one global load and a predictable branch,
as the existing counter's comment promises. `PyObject_GetAttrString(v, "denominator")`
is too slow for the bind path even when enabled; check `Py_TYPE(v) == FractionType`
(fetch the type once at `unify_census_start`) before touching attributes.

Positive control for the test: `unify(Var(), Fraction(2, 1), trail)` -> counter 1;
`unify(Var(), Fraction(3, 2), trail)` -> 0; `unify(Var(), 2, trail)` -> 0. Then rerun
the absence test with the new counter asserted 0 for every path.
