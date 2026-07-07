# fix(A08): Z3 adapter translates `//` and `%` with SMT semantics, not Python's

> **DEFERRED (2026-07-07):** intentionally not implemented — direction-sensitive
> and gated on the parked design decision A08-D001 (`//`/`%` semantics across
> backends: translate to Python floor-div/mod vs keep SMT/CP-SAT native
> semantics), still open in DESIGN-DECISIONS.md. Choosing Python semantics is
> the recommendation but is exactly the contested call. Flip once D001 lands.

**Finding:** A08-F014 (correctness, medium); design question A08-D001 (parked)
**Tests:** `tests/audit_2026_07_05/test_08_clpqr_z3.py::TestZ3TranslationFidelity` (3 xfails)

## Bug
`clausal_to_z3` (`clpz3.py:234-239`) maps `FloorDiv -> /` and `Mod -> %`:
- Int sort: SMT-LIB Euclidean div/mod. `7 // -2` -> -3 (Python: -4);
  `7 % -2` -> 1 (Python: -1).
- Real sort: `FloorDiv` becomes TRUE division: `7 // 2` -> 7/2.

## Fix sketch (pending A08-D001; recommended = Python semantics)
Int sort: emit floor semantics, e.g.
`mod_f = ((a % b) + b) % b` is Euclid-on-|b|... simplest correct encoding:
`q = If(b > 0, a / b  adjusted, ...)` — or use the identity
`floor_div(a,b) = (a - mod_f(a,b)) / b` with
`mod_f(a,b) = a - b*floor(a/b)`; in SMT terms:
`mod_f = If(mod_e == 0, 0, If(b > 0, mod_e, mod_e + b))` where
`mod_e = a % b` (Euclidean, always >= 0), and
`div_f = (a - mod_f) / b`.
Real sort: reject FloorDiv (TypeError) or emit `ToReal(ToInt(a/b))` (true
floor) — decide with A08-D001.

## Acceptance
The three xfail tests flip; `tests/test_clpz3*.py` stay green.
