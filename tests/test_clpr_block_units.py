"""CLP(R) with a physical quantity, through the seam's ``clpr.real(...)``
block: the units side channel posts a united variable's interval on its
SHADOW, so every CLP(R) entry point that READS an interval must look there.

Before: ``inf/2`` of a united variable answered ``0 metre`` (it fell through
to CLP(Q), which knew nothing of it), ``sup/2`` failed, and ``label_real/1``
skipped the variable (no interval on the user's variable itself).  Each
united case is checked against its unit-free twin: the same numbers, now
carrying the dimension.

Money stays refused in CLP(R) (``units_unsupported``: no floats on a money
path) and a dimension clash is ``system_error(units_mismatch)``.
"""
from __future__ import annotations

import itertools
import warnings

import pytest

from clausal.import_hook import _load_module
from clausal.logic.exceptions import LogicException
from clausal.logic.solve import call
from clausal.logic.variables import Var, walk
from clausal.terms import Quantity, term_str

_N = itertools.count()

UNITS = ("-import_from(european_union, [euro])\n"
         "-import_from(py.units, [metre])\n"
         "-constant_number_units(one_euro, 1, euro)\n"
         "-constant_number_units(one_metre, 1, metre)\n")

ROWS = {
    # a point interval, read back through inf/sup
    "pt_u": "clpr.real((X == 3 * constant(one_metre))), inf(X, L), sup(X, H), Q is [L, H]",
    "pt_p": "clpr.real((X == 3 * 1)), inf(X, L), sup(X, H), Q is [L, H]",
    # bounds
    "rng_u": ("clpr.real((X >= constant(one_metre), X <= 2 * constant(one_metre))), "
              "inf(X, L), sup(X, H), Q is [L, H]"),
    "rng_p": "clpr.real((X >= 1, X <= 2 * 1)), inf(X, L), sup(X, H), Q is [L, H]",
    # an expression over a united variable keeps its dimension
    "sum_u": ("clpr.real((X >= constant(one_metre), X <= 2 * constant(one_metre))), "
              "sup(X + X, Q)"),
    "sum_p": "clpr.real((X >= 1, X <= 2 * 1)), sup(X + X, Q)",
    # label_real narrows the shadow
    "lab_u": ("clpr.real((X == 3 * constant(one_metre))), label_real([X]), "
              "inf(X, L), sup(X, H), Q is [L, H]"),
    "lab_p": "clpr.real((X == 3 * 1)), label_real([X]), inf(X, L), sup(X, H), Q is [L, H]",
    # a scalar binds, as the bare comparator does
    "bind": "clpr.real((Q == constant(one_metre)))",
    "later": ("clpr.real((Q >= constant(one_metre), Q <= 2 * constant(one_metre))), "
              "Q == 1.5 * constant(one_metre)"),
    "later_out": ("clpr.real((Q >= constant(one_metre), Q <= 2 * constant(one_metre))), "
                  "Q == 5 * constant(one_metre)"),
    "money": "clpr.real((Q == 3 * constant(one_euro)))",
    "mismatch": "clpr.real((Q == 3 * constant(one_metre))), Q == 5",
}


@pytest.fixture(scope="module")
def mod(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("clpr_units")
    name = f"_clpr_units_{next(_N)}"
    body = "".join(f"{k}(Q) <- ({v})\n" for k, v in ROWS.items())
    src = (f"-module({name}, [{', '.join(k + '/1' for k in ROWS)}])\n"
           f"-allow_singletons\n{UNITS}{body}")
    p = tmp / f"{name}.clausal"
    p.write_text(src)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return _load_module(name, str(p)).__dict__["$module"]


def _answers(mod, pred):
    q = Var()
    return [walk(q) for _ in call(pred, q, module=mod)]


def _m(x):
    return Quantity(x, {"metre": 1})


def _as_metres(value):
    if isinstance(value, list):
        return [_as_metres(v) for v in value]
    return _m(value)


@pytest.mark.parametrize("stem", ["pt", "rng", "sum", "lab"])
def test_united_answers_are_the_unit_free_answers_in_metres(mod, stem):
    plain = _answers(mod, f"{stem}_p")
    assert plain, stem                                   # the control answers
    assert _answers(mod, f"{stem}_u") == [_as_metres(a) for a in plain]


def test_the_point_interval_is_three_metres(mod):
    [[lo, hi]] = _answers(mod, "pt_u")
    assert lo.dims == hi.dims == {"metre": 1}
    assert lo.value <= 3.0 <= hi.value and hi.value - lo.value < 1e-9


def test_a_scalar_binds_a_quantity(mod):
    assert _answers(mod, "bind") == [_m(1.0)]


def test_a_later_binding_is_checked_against_the_interval(mod):
    assert _answers(mod, "later") == [_m(1.5)]
    assert _answers(mod, "later_out") == []


def _raises(mod, pred, formal):
    with pytest.raises(LogicException) as ei:
        _answers(mod, pred)
    assert f"system_error({formal})" in term_str(ei.value.term)


def test_money_is_refused(mod):
    _raises(mod, "money", "units_unsupported")


def test_a_dimensionless_binding_is_a_mismatch(mod):
    _raises(mod, "mismatch", "units_mismatch")
