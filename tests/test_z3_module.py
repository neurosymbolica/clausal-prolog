"""Tests for the z3.* module API — constraint blocks with {}.

Tests the module-based API where constraints are posted via
z3.integer({...}), z3.real({...}), z3.bitvector(N, {...}), etc.
These call into clpz3.py's z3_constraint_block + clausal_to_z3.
"""

from __future__ import annotations
import pytest

z3 = pytest.importorskip("z3")

from clausal.logic.variables import Var, Trail, deref, is_var, unify
from clausal.logic.clpz3 import (
    z3_constraint_block, label_z3_polymorphic,
    get_z3_state, z3_check, z3_push,
    clausal_to_z3,
)
from clausal.pythonic_ast.nodes import (
    ArithEq, ArithNeq, Lt, LtE, Gt, GtE,
    Add, Sub, Mult,
    CompareChain,
    BitAnd, BitOr, BitXor,
)
from clausal.terms import SetTerm


# ══════════════════════════════════════════════════════════════════════════════
# CompareChain in clausal_to_z3
# ══════════════════════════════════════════════════════════════════════════════

class TestCompareChain:
    def test_simple_chain(self):
        """1 <= X <= 10 → And(1 <= x, x <= 10)."""
        trail = Trail()
        x = Var()
        chain = CompareChain(comparisons=[
            LtE(left=1, right=x),
            LtE(left=x, right=10),
        ])
        z3_expr = clausal_to_z3(chain, trail, default_sort=z3.IntSort())
        state = get_z3_state(trail)
        z3_push(trail)
        state.solver.add(z3_expr)
        assert z3_check(trail)

    def test_chain_constrains_domain(self):
        """1 <= X <= 3 limits X to {1, 2, 3}."""
        trail = Trail()
        x = Var()
        chain = CompareChain(comparisons=[
            LtE(left=1, right=x),
            LtE(left=x, right=3),
        ])
        z3_constraint_block(SetTerm([chain]), z3.IntSort(), trail)
        sols = []
        for _ in label_z3_polymorphic([x], trail):
            sols.append(deref(x))
        assert sorted(sols) == [1, 2, 3]

    def test_single_comparison_chain(self):
        """Chain with one comparison still works."""
        trail = Trail()
        x = Var()
        chain = CompareChain(comparisons=[LtE(left=x, right=5)])
        z3_expr = clausal_to_z3(chain, trail, default_sort=z3.IntSort())
        assert z3_expr is not None


# ══════════════════════════════════════════════════════════════════════════════
# z3.integer({...})
# ══════════════════════════════════════════════════════════════════════════════

class TestIntegerBlock:
    def test_simple_constraints(self):
        trail = Trail()
        x, y = Var(), Var()
        constraints = SetTerm([
            CompareChain(comparisons=[LtE(left=1, right=x), LtE(left=x, right=5)]),
            CompareChain(comparisons=[LtE(left=1, right=y), LtE(left=y, right=5)]),
            ArithEq(left=Add(left=x, right=y), right=6),
        ])
        z3_constraint_block(constraints, z3.IntSort(), trail)
        sols = []
        for _ in label_z3_polymorphic([x, y], trail):
            sols.append((deref(x), deref(y)))
        assert sorted(sols) == [(1, 5), (2, 4), (3, 3), (4, 2), (5, 1)]

    def test_auto_registers_vars(self):
        """Vars in constraint block are auto-registered with IntSort."""
        trail = Trail()
        x = Var()
        constraints = SetTerm([LtE(left=x, right=10), GtE(left=x, right=5)])
        z3_constraint_block(constraints, z3.IntSort(), trail)
        state = get_z3_state(trail)
        assert id(x) in state.var_map
        assert state.var_map[id(x)].sort() == z3.IntSort()

    def test_inequality(self):
        trail = Trail()
        x = Var()
        constraints = SetTerm([
            CompareChain(comparisons=[LtE(left=0, right=x), LtE(left=x, right=3)]),
            ArithNeq(left=x, right=1),
        ])
        z3_constraint_block(constraints, z3.IntSort(), trail)
        sols = []
        for _ in label_z3_polymorphic([x], trail):
            sols.append(deref(x))
        assert sorted(sols) == [0, 2, 3]

    def test_arithmetic_expression(self):
        trail = Trail()
        x = Var()
        constraints = SetTerm([
            CompareChain(comparisons=[LtE(left=0, right=x), LtE(left=x, right=10)]),
            ArithEq(left=Mult(left=x, right=2), right=8),
        ])
        z3_constraint_block(constraints, z3.IntSort(), trail)
        sols = []
        for _ in label_z3_polymorphic([x], trail):
            sols.append(deref(x))
        assert sols == [4]


# ══════════════════════════════════════════════════════════════════════════════
# z3.real({...})
# ══════════════════════════════════════════════════════════════════════════════

class TestRealBlock:
    def test_real_constraints(self):
        trail = Trail()
        x = Var()
        constraints = SetTerm([
            GtE(left=x, right=0),
            LtE(left=x, right=10),
        ])
        z3_constraint_block(constraints, z3.RealSort(), trail)
        state = get_z3_state(trail)
        assert state.var_map[id(x)].sort() == z3.RealSort()
        assert z3_check(trail)

    def test_real_label_yields_one(self):
        """Real labeling yields at most one solution (continuous domain)."""
        trail = Trail()
        x = Var()
        constraints = SetTerm([
            GtE(left=x, right=0),
            LtE(left=x, right=10),
        ])
        z3_constraint_block(constraints, z3.RealSort(), trail)
        count = 0
        for _ in label_z3_polymorphic([x], trail):
            count += 1
        assert count == 1


# ══════════════════════════════════════════════════════════════════════════════
# z3.bitvector(Width, {...})
# ══════════════════════════════════════════════════════════════════════════════

class TestBitvectorBlock:
    def test_bv_constraints(self):
        """BV(4) with x < 3 gives {0, 1, 2}."""
        trail = Trail()
        x = Var()
        constraints = SetTerm([Lt(left=x, right=3)])
        z3_constraint_block(constraints, z3.BitVecSort(4), trail)
        state = get_z3_state(trail)
        assert state.var_map[id(x)].sort() == z3.BitVecSort(4)
        sols = []
        for _ in label_z3_polymorphic([x], trail):
            sols.append(deref(x))
        assert sorted(sols) == [0, 1, 2]

    def test_bv_bitwise(self):
        """Bitwise AND in constraint block."""
        trail = Trail()
        x, r = Var(), Var()
        constraints = SetTerm([
            ArithEq(left=x, right=0b1010),
            ArithEq(left=BitAnd(left=x, right=0b1100), right=r),
        ])
        z3_constraint_block(constraints, z3.BitVecSort(8), trail)
        sols = []
        for _ in label_z3_polymorphic([r], trail):
            sols.append(deref(r))
        assert sols == [0b1000]

    def test_bv_arithmetic(self):
        """Addition wraps around in BV(8)."""
        trail = Trail()
        x, y, r = Var(), Var(), Var()
        constraints = SetTerm([
            ArithEq(left=x, right=200),
            ArithEq(left=y, right=100),
            ArithEq(left=Add(left=x, right=y), right=r),
        ])
        z3_constraint_block(constraints, z3.BitVecSort(8), trail)
        sols = []
        for _ in label_z3_polymorphic([r], trail):
            sols.append(deref(r))
        assert sols == [44]  # (200 + 100) mod 256 = 44


# ══════════════════════════════════════════════════════════════════════════════
# z3.boolean({...})
# ══════════════════════════════════════════════════════════════════════════════

class TestBooleanBlock:
    def test_boolean_constraints(self):
        trail = Trail()
        x, y = Var(), Var()
        constraints = SetTerm([
            BitOr(left=x, right=y),  # x | y must be true
        ])
        z3_constraint_block(constraints, z3.BoolSort(), trail)
        sols = []
        for _ in label_z3_polymorphic([x, y], trail):
            sols.append((deref(x), deref(y)))
        # {(0,1), (1,0), (1,1)} — three solutions where x|y is true
        assert len(sols) == 3
        assert (0, 0) not in sols


# ══════════════════════════════════════════════════════════════════════════════
# Sort-polymorphic label
# ══════════════════════════════════════════════════════════════════════════════

class TestPolymorphicLabel:
    def test_label_integer(self):
        trail = Trail()
        x = Var()
        z3_constraint_block(
            SetTerm([CompareChain(comparisons=[LtE(left=0, right=x), LtE(left=x, right=2)])]),
            z3.IntSort(), trail
        )
        sols = []
        for _ in label_z3_polymorphic([x], trail):
            sols.append(deref(x))
        assert sorted(sols) == [0, 1, 2]

    def test_label_bv(self):
        trail = Trail()
        x = Var()
        z3_constraint_block(
            SetTerm([Lt(left=x, right=4)]),
            z3.BitVecSort(4), trail
        )
        sols = []
        for _ in label_z3_polymorphic([x], trail):
            sols.append(deref(x))
        assert sorted(sols) == [0, 1, 2, 3]

    def test_label_bool(self):
        trail = Trail()
        x = Var()
        z3_constraint_block(SetTerm([ArithEq(left=x, right=x)]), z3.BoolSort(), trail)
        sols = []
        for _ in label_z3_polymorphic([x], trail):
            sols.append(deref(x))
        assert sorted(sols) == [0, 1]

    def test_label_real_one_solution(self):
        trail = Trail()
        x = Var()
        z3_constraint_block(
            SetTerm([GtE(left=x, right=0), LtE(left=x, right=10)]),
            z3.RealSort(), trail
        )
        count = sum(1 for _ in label_z3_polymorphic([x], trail))
        assert count == 1

    def test_label_ground_vars_ignored(self):
        """Ground values in the label list are skipped."""
        trail = Trail()
        x = Var()
        z3_constraint_block(
            SetTerm([ArithEq(left=x, right=5)]),
            z3.IntSort(), trail
        )
        sols = []
        for _ in label_z3_polymorphic([x, 42], trail):
            sols.append(deref(x))
        assert sols == [5]

    def test_label_unregistered_raises(self):
        trail = Trail()
        x = Var()
        with pytest.raises(ValueError, match="not registered"):
            list(label_z3_polymorphic([x], trail))

    def test_bindings_undone_after_label(self):
        trail = Trail()
        x = Var()
        z3_constraint_block(
            SetTerm([CompareChain(comparisons=[LtE(left=0, right=x), LtE(left=x, right=2)])]),
            z3.IntSort(), trail
        )
        for _ in label_z3_polymorphic([x], trail):
            pass
        assert is_var(deref(x))


# ══════════════════════════════════════════════════════════════════════════════
# Mixed theory (separate blocks on same trail)
# ══════════════════════════════════════════════════════════════════════════════

class TestMixedTheory:
    def test_integer_and_real_on_same_trail(self):
        """Integer and real constraints coexist on the same solver."""
        trail = Trail()
        x = Var()
        y = Var()
        z3_constraint_block(
            SetTerm([CompareChain(comparisons=[LtE(left=0, right=x), LtE(left=x, right=5)])]),
            z3.IntSort(), trail
        )
        z3_constraint_block(
            SetTerm([GtE(left=y, right=0.0), LtE(left=y, right=1.0)]),
            z3.RealSort(), trail
        )
        assert z3_check(trail)

    def test_constraint_block_backtrack(self):
        """Constraint block constraints are retracted on trail undo."""
        trail = Trail()
        x = Var()
        z3_constraint_block(
            SetTerm([CompareChain(comparisons=[LtE(left=0, right=x), LtE(left=x, right=10)])]),
            z3.IntSort(), trail
        )
        mark = trail.mark()
        z3_constraint_block(SetTerm([ArithEq(left=x, right=5)]), z3.IntSort(), trail)
        # Only x=5 reachable
        sols = []
        for _ in label_z3_polymorphic([x], trail):
            sols.append(deref(x))
        assert sols == [5]

        trail.undo(mark)
        # All 0..10 reachable again
        count = sum(1 for _ in label_z3_polymorphic([x], trail))
        assert count == 11
