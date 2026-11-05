"""SymExpr equality and hash are SymPy's STRUCTURAL ones (operator ruling
2026-11-04, review of the sandbox admission).

They used to run ``sympy.simplify`` and up to 120 alpha-renamings from
``__eq__``: from ``=``, ``==`` and ``sort/2`` on two SymPy results, outside
any time budget (17 s under a 1 s sandbox budget), and with answers that
depended on how the engine reached it.  Semantic equality is
``sym_equal/2``'s job, which runs under the budget.
"""
from __future__ import annotations

import time

import sympy as sp

from clausal.logic.variables import Trail, Var, unify
from clausal.modules.py.sympy import SymExpr, sym_equal

from test_sympy_module import _first_solution

x, y = sp.symbols("x y")


def test_two_forms_of_one_polynomial_are_different_terms():
    a = SymExpr(sp.expand((x + 1) ** 2))
    b = SymExpr(sp.factor(x ** 2 + 2 * x + 1))
    assert a != b
    assert not (a == b)


def test_the_same_structure_is_equal_with_one_hash():
    a = SymExpr(sp.expand((x + 1) ** 2))
    b = SymExpr(x ** 2 + 2 * x + 1)
    assert a == b
    assert hash(a) == hash(b)
    assert a == x ** 2 + 2 * x + 1          # a SymPy value: structural too


def test_renamed_variables_are_different_terms():
    assert SymExpr(x + 1) != SymExpr(y + 1)


def test_a_clausal_term_is_no_symexpr():
    """No conversion (and so no auto-naming of variables) from __eq__."""
    assert SymExpr(x + 1) != ("+", Var(), 1)


def test_unifying_two_big_results_does_not_simplify():
    def big(k):
        a, b, c, d, f = sp.symbols("a b c d f")
        return sp.expand((a + 2 * b + 3 * c + 4 * d + 5 * f + k) ** 6
                         * sp.sin(a * b + c) ** 2 + sp.cos(d * f) ** 3)
    e1, e2 = SymExpr(big(1)), SymExpr(big(2))
    t0 = time.monotonic()
    trail = Trail()
    assert not unify(e1, e2, trail)
    assert time.monotonic() - t0 < 1.0


def test_semantic_equality_is_sym_equal():
    a = SymExpr(sp.expand((x + 1) ** 2))
    b = SymExpr(sp.factor(x ** 2 + 2 * x + 1))
    assert _first_solution(sym_equal, a, b) is not None
