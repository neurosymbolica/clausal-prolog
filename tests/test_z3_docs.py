"""Tests backing the examples in docs/z3.md.

Each test corresponds to a code example in the documentation, ensuring
that documentation stays accurate as the implementation evolves.
"""

from __future__ import annotations
import pytest

z3 = pytest.importorskip("z3")

from clausal.logic.variables import Var, Trail, deref, is_var
from clausal.logic.clpz3 import (
    z3_constraint_block, label_z3_polymorphic,
    get_z3_state, z3_check, z3_push,
    z3_eq, z3_named, z3_unsat_core,
    z3_soft, z3_max_sat,
    z3_optimize_label, maximize_z3, minimize_z3,
    all_different_z3, entailed_z3, z3_disentailed,
    z3_is_sat, z3_model,
    bv_extract, bv_concat,
    z3_array, z3_select, z3_store,
    z3_set, z3_set_add, z3_set_member,
    z3_string, z3_str_length, z3_str_contains,
    z3_function, z3_app,
)
from clausal.pythonic_ast.nodes import (
    ArithEq, ArithNeq, Lt, LtE, Gt, GtE,
    Add, Sub, Mult, CompareChain,
    BitAnd, BitOr,
)
from clausal.terms import SetTerm


# ══════════════════════════════════════════════════════════════════════════════
# Integer Constraints (docs: "Integer Constraints" section)
# ══════════════════════════════════════════════════════════════════════════════

class TestDocsInteger:
    def test_solve_x_plus_y(self):
        """docs: Solve(X, Y) with X+Y==4, domain [1,3]."""
        trail = Trail()
        x, y = Var(), Var()
        z3_constraint_block(SetTerm([
            CompareChain(comparisons=[LtE(left=1, right=x), LtE(left=x, right=3)]),
            CompareChain(comparisons=[LtE(left=1, right=y), LtE(left=y, right=3)]),
            ArithEq(left=Add(left=x, right=y), right=4),
        ]), z3.IntSort(), trail)
        sols = []
        for _ in label_z3_polymorphic([x, y], trail):
            sols.append((deref(x), deref(y)))
        assert sorted(sols) == [(1, 3), (2, 2), (3, 1)]

    def test_scheduling_minimize(self):
        """docs: Schedule(T1, T2, T3, Cost) — minimize makespan."""
        trail = Trail()
        t1, t2, t3 = Var(), Var(), Var()
        z3_constraint_block(SetTerm([
            CompareChain(comparisons=[LtE(left=0, right=t1), LtE(left=t1, right=100)]),
            CompareChain(comparisons=[LtE(left=0, right=t2), LtE(left=t2, right=100)]),
            CompareChain(comparisons=[LtE(left=0, right=t3), LtE(left=t3, right=100)]),
            LtE(left=Add(left=t1, right=5), right=t2),
            LtE(left=Add(left=t2, right=3), right=t3),
        ]), z3.IntSort(), trail)
        cost = Var()
        sols = []
        for _ in z3_optimize_label([t1, t2, t3], t3, cost, "minimize", trail):
            sols.append((deref(t1), deref(t2), deref(t3), deref(cost)))
        assert sols == [(0, 5, 8, 8)]

    def test_all_different(self):
        """docs: all_different constraint."""
        trail = Trail()
        x, y, z = Var(), Var(), Var()
        z3_constraint_block(SetTerm([
            CompareChain(comparisons=[LtE(left=1, right=x), LtE(left=x, right=3)]),
            CompareChain(comparisons=[LtE(left=1, right=y), LtE(left=y, right=3)]),
            CompareChain(comparisons=[LtE(left=1, right=z), LtE(left=z, right=3)]),
        ]), z3.IntSort(), trail)
        all_different_z3([x, y, z], trail)
        sols = []
        for _ in label_z3_polymorphic([x, y, z], trail):
            sols.append(tuple(sorted([deref(x), deref(y), deref(z)])))
        # 3! = 6 permutations of {1, 2, 3}
        assert len(sols) == 6
        assert all(s == (1, 2, 3) for s in sols)


# ══════════════════════════════════════════════════════════════════════════════
# Real Constraints (docs: "Real Constraints" section)
# ══════════════════════════════════════════════════════════════════════════════

class TestDocsReal:
    def test_real_label_one_solution(self):
        """docs: labeling real variables yields at most one solution."""
        trail = Trail()
        x = Var()
        z3_constraint_block(SetTerm([
            GtE(left=x, right=0),
            LtE(left=x, right=10),
        ]), z3.RealSort(), trail)
        count = sum(1 for _ in label_z3_polymorphic([x], trail))
        assert count == 1

    def test_real_minimize(self):
        """docs: Diet problem — minimize cost."""
        trail = Trail()
        bread, milk = Var(), Var()
        z3_constraint_block(SetTerm([
            CompareChain(comparisons=[LtE(left=0, right=bread), LtE(left=bread, right=100)]),
            CompareChain(comparisons=[LtE(left=0, right=milk), LtE(left=milk, right=100)]),
            GtE(left=Add(left=Mult(left=2, right=bread), right=Mult(left=4, right=milk)), right=6),
        ]), z3.RealSort(), trail)
        cost = Var()
        assert minimize_z3(
            Add(left=Mult(left=2, right=bread), right=Mult(left=4, right=milk)),
            cost, trail
        )
        assert deref(cost) == 6  # minimum when constraint is tight


# ══════════════════════════════════════════════════════════════════════════════
# Boolean Constraints (docs: "Boolean Constraints" section)
# ══════════════════════════════════════════════════════════════════════════════

class TestDocsBoolean:
    def test_or_constraint(self):
        """docs: Circuit(A, B, C) — A | B, not all three."""
        trail = Trail()
        a, b, c = Var(), Var(), Var()
        z3_constraint_block(SetTerm([
            BitOr(left=a, right=b),
        ]), z3.BoolSort(), trail)
        sols = []
        for _ in label_z3_polymorphic([a, b], trail):
            sols.append((deref(a), deref(b)))
        # (0,1), (1,0), (1,1)
        assert len(sols) == 3
        assert (0, 0) not in sols


# ══════════════════════════════════════════════════════════════════════════════
# Bitvector Constraints (docs: "Bitvector Constraints" section)
# ══════════════════════════════════════════════════════════════════════════════

class TestDocsBitvector:
    def test_mask(self):
        """docs: Mask(X, Result) — X & 0xF0."""
        trail = Trail()
        x, result = Var(), Var()
        z3_constraint_block(SetTerm([
            ArithEq(left=x, right=0xAB),
            ArithEq(left=BitAnd(left=x, right=0xF0), right=result),
        ]), z3.BitVecSort(8), trail)
        sols = []
        for _ in label_z3_polymorphic([result], trail):
            sols.append(deref(result))
        assert sols == [0xA0]

    def test_unsigned_comparison(self):
        """docs: Comparisons inside z3.bitvector are unsigned."""
        trail = Trail()
        x = Var()
        # BV(4): unsigned < 3 gives {0, 1, 2}
        z3_constraint_block(SetTerm([Lt(left=x, right=3)]), z3.BitVecSort(4), trail)
        sols = []
        for _ in label_z3_polymorphic([x], trail):
            sols.append(deref(x))
        assert sorted(sols) == [0, 1, 2]

    def test_extract(self):
        """docs: z3.extract(Hi, Lo, X, Result) — bit extraction."""
        trail = Trail()
        x, r = Var(), Var()
        z3_constraint_block(SetTerm([ArithEq(left=x, right=0xAB)]), z3.BitVecSort(8), trail)
        bv_extract(7, 4, x, r, trail)
        sols = []
        for _ in label_z3_polymorphic([r], trail):
            sols.append(deref(r))
        assert sols == [0xA]


# ══════════════════════════════════════════════════════════════════════════════
# Optimization (docs: "Optimization" section)
# ══════════════════════════════════════════════════════════════════════════════

class TestDocsOptimization:
    def test_maximize(self):
        """docs: Maximize X + Y subject to X + Y <= 10."""
        trail = Trail()
        x, y = Var(), Var()
        z3_constraint_block(SetTerm([
            CompareChain(comparisons=[LtE(left=0, right=x), LtE(left=x, right=10)]),
            CompareChain(comparisons=[LtE(left=0, right=y), LtE(left=y, right=10)]),
            LtE(left=Add(left=x, right=y), right=10),
        ]), z3.IntSort(), trail)
        cost = Var()
        assert maximize_z3(Add(left=x, right=y), cost, trail)
        assert deref(cost) == 10

    def test_soft_preferences(self):
        """docs: Soft constraints — higher weight wins."""
        trail = Trail()
        x = Var()
        z3_constraint_block(SetTerm([
            CompareChain(comparisons=[LtE(left=0, right=x), LtE(left=x, right=10)]),
        ]), z3.IntSort(), trail)
        z3_soft(LtE(left=x, right=3), 2, trail)
        z3_soft(GtE(left=x, right=7), 5, trail)
        sat = Var()
        assert z3_max_sat(sat, trail)
        assert deref(sat) == 5

    def test_optimize_label(self):
        """docs: z3.optimize_label — minimize makespan."""
        trail = Trail()
        t1, t2, t3 = Var(), Var(), Var()
        z3_constraint_block(SetTerm([
            CompareChain(comparisons=[LtE(left=0, right=t1), LtE(left=t1, right=100)]),
            CompareChain(comparisons=[LtE(left=0, right=t2), LtE(left=t2, right=100)]),
            CompareChain(comparisons=[LtE(left=0, right=t3), LtE(left=t3, right=100)]),
            LtE(left=Add(left=t1, right=5), right=t2),
            LtE(left=Add(left=t2, right=3), right=t3),
        ]), z3.IntSort(), trail)
        cost = Var()
        sols = []
        for _ in z3_optimize_label([t1, t2, t3], t3, cost, "minimize", trail):
            sols.append(deref(cost))
        assert sols == [8]


# ══════════════════════════════════════════════════════════════════════════════
# Diagnostics (docs: "Diagnostics" section)
# ══════════════════════════════════════════════════════════════════════════════

class TestDocsDiagnostics:
    def test_unsat_core(self):
        """docs: Debug(Core) — named constraints + unsat core."""
        trail = Trail()
        x = Var()
        z3_constraint_block(SetTerm([
            CompareChain(comparisons=[LtE(left=1, right=x), LtE(left=x, right=10)]),
        ]), z3.IntSort(), trail)
        z3_named(Gt(left=x, right=8), "x_high", trail)
        z3_named(Lt(left=x, right=3), "x_low", trail)
        core = Var()
        assert z3_unsat_core(core, trail)
        names = deref(core)
        assert "x_high" in names
        assert "x_low" in names

    def test_satisfiability(self):
        """docs: z3.satisfiability returns 'sat' or 'unsat'."""
        trail = Trail()
        x = Var()
        z3_constraint_block(SetTerm([
            CompareChain(comparisons=[LtE(left=1, right=x), LtE(left=x, right=10)]),
        ]), z3.IntSort(), trail)
        r = Var()
        assert z3_is_sat(r, trail)
        assert deref(r) == "sat"

    def test_entailed(self):
        """docs: z3.entailed succeeds when constraint is implied."""
        trail = Trail()
        x = Var()
        z3_constraint_block(SetTerm([
            CompareChain(comparisons=[LtE(left=5, right=x), LtE(left=x, right=10)]),
        ]), z3.IntSort(), trail)
        assert entailed_z3(GtE(left=x, right=5), trail)

    def test_disentailed(self):
        """docs: z3.disentailed succeeds when constraint is impossible."""
        trail = Trail()
        x = Var()
        z3_constraint_block(SetTerm([
            CompareChain(comparisons=[LtE(left=5, right=x), LtE(left=x, right=10)]),
        ]), z3.IntSort(), trail)
        assert z3_disentailed(Lt(left=x, right=5), trail)

    def test_model_without_binding(self):
        """docs: z3.model gets model without binding variables."""
        trail = Trail()
        x = Var()
        z3_constraint_block(SetTerm([ArithEq(left=x, right=7)]), z3.IntSort(), trail)
        vals = Var()
        assert z3_model([x], vals, trail)
        assert is_var(deref(x))  # x still unbound
        assert deref(vals)[0][1] == 7


# ══════════════════════════════════════════════════════════════════════════════
# Arrays, Sets, Strings (docs: respective sections)
# ══════════════════════════════════════════════════════════════════════════════

class TestDocsArrays:
    def test_store_select(self):
        """docs: array store then select."""
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


class TestDocsSets:
    def test_set_member_after_add(self):
        """docs: set_add then set_member."""
        trail = Trail()
        s1, s2 = Var(), Var()
        z3_set(s1, z3.IntSort(), trail)
        z3_set_add(s1, 42, s2, trail)
        z3_set_member(42, s2, trail)
        assert z3_check(trail)


class TestDocsStrings:
    def test_string_length(self):
        """docs: z3.string_length(S, N)."""
        trail = Trail()
        s = Var()
        z3_string(s, trail)
        n = Var()
        z3_str_length(s, n, trail)
        z3_str_contains(s, "hello", trail)
        # Length must be >= 5 since it contains "hello"
        assert entailed_z3(GtE(left=n, right=5), trail)


class TestDocsUF:
    def test_functional_consistency(self):
        """docs: f(x) == f(y) when x == y."""
        trail = Trail()
        f = Var()
        z3_function(f, [z3.IntSort()], z3.IntSort(), trail)
        x = Var()
        r1, r2 = Var(), Var()
        z3_constraint_block(SetTerm([ArithEq(left=x, right=5)]), z3.IntSort(), trail)
        z3_app(f, [x], r1, trail)
        z3_app(f, [5], r2, trail)
        # r1 == r2 because f(x) == f(5) when x == 5
        assert entailed_z3(ArithEq(left=r1, right=r2), trail)
