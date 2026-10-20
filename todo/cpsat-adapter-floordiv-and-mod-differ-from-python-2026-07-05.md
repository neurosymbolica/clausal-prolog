# The CP-SAT adapter's `//` truncates and its `%` with a negative numerator is infeasible (A08-F015, A08-D001)

**Status: open, gated on design decision A08-D001 (unruled).** Triaged
2026-10-20, moved from the 2026-07-05 audit folder (was
`fix-A08-ortools-floordiv-mod-translation.md`). The pinning tests could not
be re-run here (ortools not installed; they skip), but the code is
unchanged: `clausal/logic/clportools.py:454-475` still uses
`AddDivisionEquality`/`AddModuloEquality` with the `rem` helper's domain
`[0, 10**9]`. Twin:
todo/z3-adapter-translates-floordiv-and-mod-with-smt-semantics-2026-07-05.md.

The original audit text follows.

> **DEFERRED (2026-07-07):** intentionally not implemented — direction-sensitive
> and gated on the parked design decision A08-D001 (`//`/`%` semantics across
> backends), still open in DESIGN-DECISIONS.md. Same gate as the Z3 twin
> (todo/z3-adapter-translates-floordiv-and-mod-with-smt-semantics-2026-07-05.md). Flip once D001 lands.

**Finding:** A08-F015 (correctness, medium); design question A08-D001 (parked)
**Tests:** `tests/audit_2026_07_05/test_08_clpqr_z3.py::TestCpsatTranslationFidelity::test_floordiv_negative_numerator`, `::test_mod_negative_numerator`

## Bug
`clausal_to_cpsat` (`clportools.py:459-475`):
- `AddDivisionEquality` truncates toward zero: `-7 // 2` -> -3 (Python: -4).
- `AddModuloEquality` follows the numerator sign AND the helper `rem` var is
  created with domain `[0, 10**9]`, so `X == -7 % 3` is INFEASIBLE (no
  solutions at all; Python: 2).

## Fix sketch (pending A08-D001; recommended = Python semantics)
Encode floor semantics with auxiliary vars:
`a == q*b + r`, `0 <= r < |b|` when `b > 0` (Python's sign-of-divisor rule),
using `AddMultiplicationEquality` + linear constraints instead of the native
Add{Division,Modulo}Equality; or post-adjust:
`q_f = q_t - ((r_t != 0) and (sign(a) != sign(b)))`. Also widen/parametrize
the hard-coded `[-10**9, 10**9]` helper domains (silent infeasibility for
larger values — note in docs).

## Acceptance
Both xfail tests flip; `tests/test_clportools.py` stays green.
