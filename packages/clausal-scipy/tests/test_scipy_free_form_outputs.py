"""Free-form text scipy hands back is a STRING; constant NAMES stay ATOMS.

Ruled 2026-10-04 (adapters are their own entry point, strings spec 9.4):
an integrator's or optimizer's ``message`` and a CODATA unit are free-form
text, the string ``('$chars', s)``.  A CODATA constant NAME is the key
``lookup/4`` and the rest take, so ``find/2`` and ``all_names/1`` keep
answering atoms (plain ``str``).
"""

from __future__ import annotations

import math

import pytest

pytest.importorskip("scipy", reason="scipy not installed")
np = pytest.importorskip("numpy")

from clausal.logic.cells import chars, is_chars
from clausal.logic.trampoline import DONE
from clausal.logic.variables import Trail, Var, deref
from clausal.modules.py import scipy_constants as sc
from clausal.modules.py import scipy_integrate as si
from clausal.modules.py import scipy_optimize as so


def _drive(pred, *args, n_out=1):
    outs = [Var() for _ in range(n_out)]
    gen = pred._get_dispatch()(None, None, None, None, *args, *outs, Trail())
    for _parent, sentinel in gen:
        if sentinel is DONE:
            return None
        if sentinel is None:
            vals = [deref(o) for o in outs]
            return vals[0] if n_out == 1 else vals
    return None


def test_unit_is_a_string():
    assert _drive(sc.unit, "speed of light in vacuum") == chars("m s^-1")


def test_lookup_unit_is_a_string():
    _v, u, _unc = _drive(sc.lookup, "electron mass", n_out=3)
    assert u == chars("kg")


def test_dimensionless_unit_is_the_empty_string():
    assert _drive(sc.unit, "fine-structure constant") == chars("")


def test_constant_names_stay_atoms():
    names = _drive(sc.find, "electron mass")
    assert "electron mass" in names
    assert all(type(n) is str for n in names)
    every = _drive(sc.all_names)
    assert all(type(n) is str for n in every)


def test_quad_vec_message_is_a_string():
    r = _drive(si.quad_vec, lambda x: np.sin(x), 0.0, math.pi)
    assert is_chars(r["message"])
    assert is_chars(_drive(si.result_get, r, "message"))


def test_solve_ivp_message_is_a_string():
    r = _drive(si.solve_initial_value_problem,
               lambda t, y: -y, [0.0, 1.0], [1.0])
    assert is_chars(r["message"])


def test_optimizer_message_is_a_string():
    r = _drive(so.minimize_scalar, lambda x: (x - 2.0) ** 2)
    assert is_chars(_drive(so.result_get, r, "message"))
    # other fields are unchanged
    assert _drive(so.result_get, r, "x") == pytest.approx(2.0)


def test_root_scalar_flag_is_a_string():
    # ruled 2026-10-04: the flag is SciPy's free-form status message
    # ("converged"), a string like an optimizer's message
    r = _drive(so.root_scalar, lambda x: x * x - 4.0, "brentq", [0.0, 3.0])
    assert r["flag"] == chars("converged") and is_chars(r["flag"])
    assert _drive(so.result_get, r, "flag") == chars("converged")
    # the other fields are unchanged
    assert r["root"] == pytest.approx(2.0) and r["converged"] is True
