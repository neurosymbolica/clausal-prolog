"""solve() accepts a Decimal, a Fraction or a Quantity as a goal argument.

These are numbers (rdiv/decimal ruling 2026-09-17; a quantity is a number
with units), but the query compiler had no literal lowering for them:
``solve(("p", Decimal("7.5"), X), m)`` raised ``NotImplementedError:
term_to_ast_expr: unsupported term type Decimal`` -- top-level, nested in a
list or a cell alike.  They now cross by reference, as an opaque object
does.  A Python date is still refused (it must be written as the term
``('date', Y, M, D)``).
"""
import datetime
from decimal import Decimal
from fractions import Fraction

import pytest

from clausal.logic.solve import _deref_walk, solve
from clausal.logic.variables import Var
from clausal.modules.units import metre

_SRC = "idn(X, X),\ndbl(X, Y) <- eval_(X * 2, Y)\n"


@pytest.fixture(scope="module")
def mod(tmp_path_factory):
    from clausal.import_hook import _load_module
    d = tmp_path_factory.mktemp("sena")
    p = d / "sena.clausal"
    p.write_text(_SRC)
    return _load_module("sena_mod", str(p))


def _one(mod, pred, arg):
    q = Var()
    return [_deref_walk(q) for _ in solve((pred, arg, q), mod)]


@pytest.mark.parametrize("value", [Decimal("7.5"), Fraction(1, 3), metre(3)],
                         ids=["Decimal", "Fraction", "Quantity"])
def test_identity(mod, value):
    assert _one(mod, "idn", value) == [value]


@pytest.mark.parametrize("value,want", [
    (Decimal("7.5"), Decimal("15.0")),
    (Fraction(1, 3), Fraction(2, 3)),
    (metre(3), metre(6)),
], ids=["Decimal", "Fraction", "Quantity"])
def test_arithmetic_on_the_argument(mod, value, want):
    assert _one(mod, "dbl", value) == [want]


def test_nested_in_a_list_and_a_cell(mod):
    assert _one(mod, "idn", [Decimal("1.5")]) == [[Decimal("1.5")]]
    assert _one(mod, "idn", ("f", Fraction(1, 2))) == [("f", Fraction(1, 2))]


def test_unifies_by_value(mod):
    assert len(list(solve(("idn", Decimal("7.5"), Decimal("7.50")), mod))) == 1
    assert len(list(solve(("idn", Decimal("7.5"), Decimal("7.6")), mod))) == 0


def test_a_python_date_is_still_refused(mod):
    with pytest.raises(NotImplementedError, match="not a term"):
        _one(mod, "idn", datetime.date(2020, 1, 1))
