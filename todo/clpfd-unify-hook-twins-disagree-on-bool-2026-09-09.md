# CLP(FD) unify hook: the Python and C twins disagree about `True`

Found while tracing integral-Fraction bindings (fix/normalise-integral-rationals-2026-09-09).

`clausal/logic/clpfd.py::_fd_hook` ("Accept int or integer-valued Fraction"):

    if isinstance(bound_to, int) and not isinstance(bound_to, bool):
        int_val = bound_to
    elif isinstance(bound_to, Fraction) and bound_to.denominator == 1:
        int_val = int(bound_to)

`bool` is excluded from the first branch and is not a `Fraction`, so binding an
FD-constrained variable to `True` falls through to the later branches and is NOT
treated as the integer 1.

`clausal/logic/_clpfd_propagate.c` (the C twin, "Case 1: bound to integer (or
integer-valued Fraction from CLP(Q))") excludes `PyBool` from `PyLong_Check` the same
way, but then reads `bt.denominator` through `PyObject_GetAttrString` — and `True`
HAS a `denominator` attribute (it is 1, inherited from int) — so it converts `True`
with `PyNumber_Long` and accepts it as the integer 1 for the domain check.

So the same binding `X in 0..1, X = True` is rejected or accepted depending on which
twin is active. Decide which behaviour is meant (the Python spelling is the explicit
one: bools are deliberately not FD numbers — see the `bool` guard in `_eval_ground`),
then make the C side test `PyBool_Check` before the denominator probe, and add a
parity test that runs the binding through both twins.
