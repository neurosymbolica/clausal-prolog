# clausal-sympy: a zero produced after the units check loses its dimension

**Status: OPEN (Low).** Found in code review of the clausal-sympy units support, 2026-11-04.

Dimensions are judged on the Clausal input term before SymPy folds anything, so the input is
checked. But a zero that SymPy produces later comes back as a plain `0`:

- `subs(M*Cp*DT, [(M, 0(kilogram)/1(second))], Q)` gives `Q = 0`, not `0 watt`. So does
  `subs(..., [(M, 0)], Q)`. `subs/3` and `limit/4` pass no expected dimension;
- `limit(X*1(kelvin) - 2(kelvin), X, 2, R)` gives `R = 0`;
- `solve(M*C*DT - 0(watt), M, R)`, with `C` unbound, gives `R = 0`;
- a zero coefficient (`coeffs`) is a plain `0`.

These fail loudly downstream, not silently: `0 + 5(watt)` and `0 > 1(watt)` raise
`system_error(units_mismatch)`. `subs(X + 3(kelvin), [(X, 0)])` gives `3 kelvin`, a value the
engine's own `0 + 3 kelvin` would refuse; the value is still right.

Fix: carry the expected dimension into `subs/3`, `limit/4` and multi-unknown `solve`, and attach
it to a zero result.
