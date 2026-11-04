# clausal-sympy: an irrational result with units comes back as a float, not an exact term

**Status: OPEN, deferred (operator ruling 2026-11-04: "ok floats for now and a todo for when we
feel we haven't suffered enough").**

When a sympy predicate's answer involves quantities and is irrational, it is returned as a float
quantity: `solve(X**2 - 2(metre)*1(metre), X, R)` gives `R = 1.4142135623730951 m`, and squaring it
back gives `2.0000000000000004 m^2`. Rational results stay exact (`Fraction`).

SymPy keeps such values exact as expressions (`sqrt(2)`), and the engine could carry the same
thing as a pow-form term, `2**(1/2) * 1(metre)`. That form was tried on the units branch, behind
the switch `_sympy_units.EXACT_IRRATIONAL_RESULTS`, and the engine does not accept it where
callers use it:

- `R > 1(metre)` raises `type_error(integer, 1/2)`, and `L > 18(kelvin)` raises
  `domain_error(clpz_expression, 1 (kelvin))`;
- `has_units(R, metre)` fails, and `strip_units(R, M)` raises `type_error(quantity, _)`;
- everything works only after an explicit `eval_(R, V)`.

To keep results exact: make comparison, `has_units/2` and `strip_units/2` evaluate a ground
pow-form or arithmetic term to a number on demand. Then flip the switch. These are engine paths
every program uses, so the change needs the full gate under both CLP(Q) solvers. A result built
from a function the engine cannot evaluate (LambertW, sinh, gamma, ...) still has to come back as
a float.
