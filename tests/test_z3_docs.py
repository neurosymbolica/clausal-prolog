"""Infrastructure tests for Z3 theories not expressible in .clausal syntax.

Arrays, sets, strings, and uninterpreted functions require Z3 sort objects
as arguments, which can't be expressed in pure .clausal syntax.
Problem-solving tests for other theories are in tests/fixtures/z3_*.clausal.
"""

from __future__ import annotations
import pytest

z3 = pytest.importorskip("z3")

from clausal.logic.variables import Var, Trail, deref, is_var
from clausal.logic.clpz3 import (
    z3_constraint_block, label_z3_polymorphic,
    get_z3_state, z3_check, entailed_z3,
    z3_array, z3_select, z3_store,
    z3_set, z3_set_add, z3_set_member,
    z3_string, z3_str_length, z3_str_contains,
    z3_function, z3_app,
)
from clausal.pythonic_ast.nodes import ArithEq, GtE


class TestArrays:
    def test_store_select(self):
        # nv
        trail = Trail()
        a, b = Var(), Var()
        z3_array(a, z3.IntSort(), z3.IntSort(), trail)
        z3_store(a, 0, 42, b, trail)
        v = Var()
        z3_select(b, 0, v, trail)
        sols = []
        for _ in label_z3_polymorphic([v], trail):
            sols.append(deref(v))
        assert sols == [42]


class TestSets:
    def test_set_member_after_add(self):
        # nv
        trail = Trail()
        s1, s2 = Var(), Var()
        z3_set(s1, z3.IntSort(), trail)
        z3_set_add(s1, 42, s2, trail)
        z3_set_member(42, s2, trail)
        assert z3_check(trail)


class TestStrings:
    def test_string_length_entailed(self):
        # nv
        trail = Trail()
        s = Var()
        z3_string(s, trail)
        n = Var()
        z3_str_length(s, n, trail)
        z3_str_contains(s, "hello", trail)
        assert entailed_z3(GtE(left=n, right=5), trail)


class TestUF:
    def test_functional_consistency(self):
        # nv
        trail = Trail()
        f = Var()
        z3_function(f, [z3.IntSort()], z3.IntSort(), trail)
        x = Var()
        r1, r2 = Var(), Var()
        z3_constraint_block((ArithEq(left=x, right=5),), z3.IntSort(), trail)
        z3_app(f, [x], r1, trail)
        z3_app(f, [5], r2, trail)
        assert entailed_z3(ArithEq(left=r1, right=r2), trail)
