"""ISO arithmetic cells convert as the seam's operator nodes do.

A ``.clausal`` (or ``.pl``) term ``X**2 - 4`` reaches the wrapper as the
cells ``('-', ('**', X, 2), 4)``, not as the seam's ``Sub``/``Pow`` nodes;
they used to become SymPy UNDEFINED functions named ``-`` and ``**``, and
solve/3 raised NotImplementedError.  The units walk reads them the same
way, so a quantity inside one is dimension-checked.
"""
from __future__ import annotations

import pytest
import sympy as sp

from clausal.logic.variables import Var
from clausal.modules import units
from clausal.modules.py.sympy import _to_sympy, simplify, solve, solve_all

from test_sympy_module import _collect_solutions, _first_solution

x = sp.Symbol("x")


@pytest.mark.parametrize("cell,expected", [
    (("+", Var(), 1), x + 1),
    (("-", Var(), 1), x - 1),
    (("-", Var()), -x),
    (("+", Var()), x),
    (("*", 2, Var()), 2 * x),
    (("/", Var(), 2), x / 2),
    (("**", Var(), 3), x ** 3),
    (("^", Var(), 3), x ** 3),
])
def test_an_iso_cell_is_its_operator(cell, expected):
    assert _to_sympy(cell) == expected


def test_solve_over_iso_cells_returns_every_root():
    X, R = Var(), Var()
    roots = [s[2] for s in _collect_solutions(
        solve, ("-", ("**", X, 2), 4), X, R)]
    assert sorted(roots) == [-2, 2]


def test_solve_all_over_nested_iso_cells():
    X, R = Var(), Var()
    eq = ("*", ("*", ("-", X, 10), ("-", X, 3)), ("+", X, 7))
    assert sorted(_first_solution(solve_all, eq, X, R)[2]) == [-7, 3, 10]


def test_a_quantity_inside_iso_cells_keeps_its_dimension():
    X, R = Var(), Var()
    # X - 10 kelvin = 0, as cells
    roots = [s[2] for s in _collect_solutions(
        solve, ("-", X, units.kelvin(10)), X, R)]
    assert roots == [units.kelvin(10)]
    with pytest.raises(Exception, match="units_mismatch|kelvin"):
        _first_solution(simplify, ("+", units.kelvin(1), units.pascal(1)),
                        Var())
