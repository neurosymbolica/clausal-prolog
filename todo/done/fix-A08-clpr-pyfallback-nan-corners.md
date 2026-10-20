# fix(A08): CLP(R) Python fallback `_imul_py`/`_idiv_py` propagate NaN corners

**Finding:** A08-F012 (correctness, low — Python-fallback builds only)
**Test:** `tests/audit_2026_07_05/test_08_clpqr_z3.py::TestClprPythonCParity::test_imul_py_nan_corner_matches_c`

## Bug
`_imul_py(0.0, 1.0, -inf, 2.0)` computes corner `0*-inf = nan`; Python
`min()/max()` propagate NaN depending on argument order -> `(nan, nan)` ->
`_narrow_real` treats NaN as wipeout -> spurious failure. The C version's
`fmin/fmax` skip NaN (`_clpr_core.c:44-54`), so builds with the extension are
unaffected — but the fallback silently changes semantics.

## Fix sketch
Filter NaN corners in `_imul_py`/`_idiv_py` (e.g.
`corners = [c for c in corners if not math.isnan(c)] or [0.0]` following the
C convention that 0*inf contributes 0-ish bounds via the other corners), or
use `math.fmin`-style helpers. Keep C/py results bit-identical.

## Acceptance
xfail test flips to pass (asserts C/py parity on the NaN corner).
