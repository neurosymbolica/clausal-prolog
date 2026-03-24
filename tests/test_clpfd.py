"""Tests for V2-6: CLP(FD) finite-domain constraint solver.

Tests domain operations, constraint posting, propagation, labeling,
all_different, equivalent, and compiler integration.
"""

from __future__ import annotations

import pytest

from clausal.logic.variables import Var, Trail, deref, unify, is_var, put_attr, get_attr
from clausal.logic.clpfd import (
    FD_KEY, FDVar, DEFAULT_MIN, DEFAULT_MAX,
    domain_from_range, domain_contains, domain_min, domain_max,
    domain_size, domain_singleton, domain_intersection, domain_remove,
    domain_remove_above, domain_remove_below, domain_values,
    _ensure_fd, _narrow, fd_eq, fd_ne, fd_lt, fd_le, fd_gt, fd_ge,
    in_domain, label, all_different, equivalent,
    EqConstraint, NeConstraint, LtConstraint, LeConstraint, AllDiffConstraint,
)
from clausal.logic.compiler import compile_predicate_trampoline as compile_predicate
from clausal.logic.database import Clause, Database, Module
from clausal.logic.solve import solve, once, query
from clausal.logic.trampoline import StepGenerator, DONE
from clausal.terms import (
    Compound, And, Add, Sub,
    Unify as Is, DoesNotUnify as IsNot, Evaluate,
    StructuralEq, StructuralNeq, Lt as LtNode, LtE as LtENode,
    Gt as GtNode, GtE as GtENode,
    Call, LoadName,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def fresh_trail() -> Trail:
    return Trail()


def _drive_trampoline(dispatch_fn, trail):
    """Drive a trampoline dispatch fn, yielding after each solution."""
    sg = StepGenerator(dispatch_fn, None, trail)
    gen, value = sg.send(None)
    while True:
        if gen is None:
            if value is DONE:
                return
            yield trail
            gen, value = sg.send(None)
        else:
            gen, value = gen.send(value)


def solutions_trampoline(dispatch_fn, trail, extract):
    results = []
    for _ in _drive_trampoline(dispatch_fn, trail):
        results.append(extract())
    return results


# ══════════════════════════════════════════════════════════════════════════════
# Phase 1: Domain operations
# ══════════════════════════════════════════════════════════════════════════════


class TestDomainOperations:
    def test_from_range(self):
        d = domain_from_range(1, 5)
        assert d == ((1, 5),)

    def test_from_range_empty(self):
        d = domain_from_range(5, 1)
        assert d == ()

    def test_from_range_singleton(self):
        d = domain_from_range(3, 3)
        assert d == ((3, 3),)

    def test_contains(self):
        d = ((1, 5), (8, 10))
        assert domain_contains(d, 1)
        assert domain_contains(d, 3)
        assert domain_contains(d, 5)
        assert domain_contains(d, 8)
        assert domain_contains(d, 10)
        assert not domain_contains(d, 0)
        assert not domain_contains(d, 6)
        assert not domain_contains(d, 11)

    def test_min_max(self):
        d = ((1, 5), (8, 10))
        assert domain_min(d) == 1
        assert domain_max(d) == 10

    def test_min_max_empty(self):
        with pytest.raises(ValueError):
            domain_min(())
        with pytest.raises(ValueError):
            domain_max(())

    def test_size(self):
        d = ((1, 5), (8, 10))
        assert domain_size(d) == 5 + 3

    def test_singleton(self):
        assert domain_singleton(((3, 3),)) == 3
        assert domain_singleton(((1, 5),)) is None
        assert domain_singleton(((1, 1), (3, 3))) is None

    def test_intersection(self):
        d1 = ((1, 5), (8, 10))
        d2 = ((3, 9),)
        result = domain_intersection(d1, d2)
        assert result == ((3, 5), (8, 9))

    def test_intersection_disjoint(self):
        d1 = ((1, 3),)
        d2 = ((5, 7),)
        assert domain_intersection(d1, d2) == ()

    def test_intersection_identical(self):
        d = ((1, 5),)
        assert domain_intersection(d, d) == ((1, 5),)

    def test_remove(self):
        d = ((1, 5),)
        assert domain_remove(d, 3) == ((1, 2), (4, 5))
        assert domain_remove(d, 1) == ((2, 5),)
        assert domain_remove(d, 5) == ((1, 4),)
        assert domain_remove(d, 0) == ((1, 5),)

    def test_remove_above(self):
        d = ((1, 5), (8, 10))
        assert domain_remove_above(d, 6) == ((1, 5),)
        assert domain_remove_above(d, 3) == ((1, 3),)

    def test_remove_below(self):
        d = ((1, 5), (8, 10))
        assert domain_remove_below(d, 3) == ((3, 5), (8, 10))
        assert domain_remove_below(d, 9) == ((9, 10),)

    def test_values(self):
        d = ((1, 3), (5, 6))
        assert list(domain_values(d)) == [1, 2, 3, 5, 6]


# ══════════════════════════════════════════════════════════════════════════════
# Phase 1: in_domain
# ══════════════════════════════════════════════════════════════════════════════


class TestInDomain:
    def test_post_domain(self):
        trail = fresh_trail()
        x = Var()
        assert in_domain(x, 1, 5, trail)
        state = get_attr(x, FD_KEY)
        assert state is not None
        assert state.domain == ((1, 5),)

    def test_post_domain_and_unify_succeeds(self):
        trail = fresh_trail()
        x = Var()
        assert in_domain(x, 1, 5, trail)
        assert unify(x, 3, trail)
        assert deref(x) == 3

    def test_post_domain_and_unify_fails(self):
        trail = fresh_trail()
        x = Var()
        assert in_domain(x, 1, 5, trail)
        mark = trail.mark()
        assert not unify(x, 7, trail)
        trail.undo(mark)

    def test_post_domain_list(self):
        trail = fresh_trail()
        x, y = Var(), Var()
        assert in_domain([x, y], 1, 3, trail)
        sx = get_attr(x, FD_KEY)
        sy = get_attr(y, FD_KEY)
        assert sx.domain == ((1, 3),)
        assert sy.domain == ((1, 3),)

    def test_post_domain_narrows_existing(self):
        trail = fresh_trail()
        x = Var()
        assert in_domain(x, 1, 10, trail)
        assert in_domain(x, 5, 15, trail)
        state = get_attr(x, FD_KEY)
        assert state.domain == ((5, 10),)

    def test_post_domain_singleton_binds(self):
        trail = fresh_trail()
        x = Var()
        assert in_domain(x, 3, 3, trail)
        assert deref(x) == 3

    def test_post_domain_empty_fails(self):
        trail = fresh_trail()
        x = Var()
        assert in_domain(x, 1, 5, trail)
        mark = trail.mark()
        assert not in_domain(x, 8, 10, trail)
        trail.undo(mark)

    def test_post_domain_ground_int(self):
        trail = fresh_trail()
        assert in_domain(3, 1, 5, trail)
        assert not in_domain(7, 1, 5, trail)


# ══════════════════════════════════════════════════════════════════════════════
# Phase 1: label
# ══════════════════════════════════════════════════════════════════════════════


class TestLabel:
    def test_label_single(self):
        trail = fresh_trail()
        x = Var()
        assert in_domain(x, 1, 3, trail)
        results = []
        for _ in label([x], trail):
            results.append(deref(x))
        assert results == [1, 2, 3]

    def test_label_two_vars(self):
        trail = fresh_trail()
        x, y = Var(), Var()
        assert in_domain([x, y], 1, 2, trail)
        results = []
        for _ in label([x, y], trail):
            results.append((deref(x), deref(y)))
        assert len(results) == 4
        assert (1, 1) in results
        assert (1, 2) in results
        assert (2, 1) in results
        assert (2, 2) in results

    def test_label_backtracking(self):
        """Domain is restored on backtrack."""
        trail = fresh_trail()
        x = Var()
        assert in_domain(x, 1, 3, trail)
        gen = label([x], trail)
        next(gen)  # first solution
        assert deref(x) == 1
        next(gen)  # second solution
        assert deref(x) == 2
        next(gen)  # third solution
        assert deref(x) == 3
        with pytest.raises(StopIteration):
            next(gen)
        # After exhaustion, x should be unbound again
        assert is_var(deref(x))

    def test_label_all_ground(self):
        trail = fresh_trail()
        results = list(label([1, 2, 3], trail))
        assert len(results) == 1  # all ground → 1 solution


# ══════════════════════════════════════════════════════════════════════════════
# Phase 1: equivalent
# ══════════════════════════════════════════════════════════════════════════════


class TestEquivalent:
    def test_same_atoms(self):
        trail = fresh_trail()
        assert equivalent("a", "a", trail)

    def test_different_atoms(self):
        trail = fresh_trail()
        assert not equivalent("a", "b", trail)

    def test_same_compound(self):
        trail = fresh_trail()
        assert equivalent(Compound("f", (1, 2)), Compound("f", (1, 2)), trail)

    def test_different_compound(self):
        trail = fresh_trail()
        assert not equivalent(Compound("f", (1,)), Compound("f", (2,)), trail)

    def test_var_vs_var_different(self):
        """equivalent uses structural equality: different Vars are NOT equal."""
        trail = fresh_trail()
        assert not equivalent(Var(), Var(), trail)

    def test_var_vs_var_same(self):
        trail = fresh_trail()
        x = Var()
        assert equivalent(x, x, trail)

    def test_bound_vars(self):
        trail = fresh_trail()
        x, y = Var(), Var()
        unify(x, 42, trail)
        unify(y, 42, trail)
        assert equivalent(x, y, trail)


# ══════════════════════════════════════════════════════════════════════════════
# Phase 2: CLP(FD) operators — fd_eq, fd_ne, fd_lt, fd_le, fd_gt, fd_ge
# ══════════════════════════════════════════════════════════════════════════════


class TestFdEq:
    def test_ground_equal(self):
        trail = fresh_trail()
        assert fd_eq(3, 3, trail)

    def test_ground_unequal(self):
        trail = fresh_trail()
        assert not fd_eq(3, 4, trail)

    def test_var_eq_int(self):
        """X == 5 narrows X to {5}."""
        trail = fresh_trail()
        x = Var()
        assert fd_eq(x, 5, trail)
        assert deref(x) == 5

    def test_var_eq_var(self):
        """X == Y posts constraint — both remain unbound."""
        trail = fresh_trail()
        x, y = Var(), Var()
        assert in_domain(x, 1, 5, trail)
        assert in_domain(y, 3, 8, trail)
        assert fd_eq(x, y, trail)
        # Domains should be intersected
        sx = get_attr(x, FD_KEY)
        if sx is not None:
            assert domain_contains(sx.domain, 3)
            assert domain_contains(sx.domain, 5)

    def test_auto_domain(self):
        """X == 5 on unbound var with no prior domain → auto-domain + narrow to {5}."""
        trail = fresh_trail()
        x = Var()
        assert fd_eq(x, 5, trail)
        assert deref(x) == 5


class TestFdNe:
    def test_ground_different(self):
        trail = fresh_trail()
        assert fd_ne(3, 4, trail)

    def test_ground_same(self):
        trail = fresh_trail()
        assert not fd_ne(3, 3, trail)

    def test_var_ne_int(self):
        trail = fresh_trail()
        x = Var()
        assert in_domain(x, 1, 5, trail)
        assert fd_ne(x, 3, trail)
        state = get_attr(x, FD_KEY)
        assert state is not None
        assert not domain_contains(state.domain, 3)

    def test_ne_wipeout(self):
        """in_domain(X, 3, 3), X != 3 → wipeout."""
        trail = fresh_trail()
        x = Var()
        assert in_domain(x, 3, 3, trail)
        assert not fd_ne(x, 3, trail)


class TestFdLt:
    def test_ground_lt(self):
        trail = fresh_trail()
        assert fd_lt(3, 5, trail)
        assert not fd_lt(5, 3, trail)
        assert not fd_lt(3, 3, trail)

    def test_var_lt(self):
        trail = fresh_trail()
        x = Var()
        assert in_domain(x, 1, 10, trail)
        assert fd_lt(x, 4, trail)
        state = get_attr(x, FD_KEY)
        assert state is not None
        assert domain_max(state.domain) <= 3


class TestFdLe:
    def test_ground_le(self):
        trail = fresh_trail()
        assert fd_le(3, 5, trail)
        assert fd_le(3, 3, trail)
        assert not fd_le(5, 3, trail)

    def test_chained_comparison(self):
        """1 <= X <= 10 narrows domain to [1, 10]."""
        trail = fresh_trail()
        x = Var()
        assert fd_le(1, x, trail)
        assert fd_le(x, 10, trail)
        state = get_attr(x, FD_KEY)
        assert state is not None
        assert domain_min(state.domain) >= 1
        assert domain_max(state.domain) <= 10


class TestFdGtGe:
    def test_gt(self):
        trail = fresh_trail()
        assert fd_gt(5, 3, trail)
        assert not fd_gt(3, 5, trail)

    def test_ge(self):
        trail = fresh_trail()
        assert fd_ge(5, 3, trail)
        assert fd_ge(3, 3, trail)
        assert not fd_ge(2, 3, trail)


# ══════════════════════════════════════════════════════════════════════════════
# Phase 2: Propagation chains
# ══════════════════════════════════════════════════════════════════════════════


class TestPropagation:
    def test_lt_chain(self):
        """X < Y, Y < Z, 1 <= Z <= 3 → propagation narrows all to singletons."""
        trail = fresh_trail()
        x, y, z = Var(), Var(), Var()
        assert in_domain([x, y, z], 1, 100, trail)
        assert fd_lt(x, y, trail)
        assert fd_lt(y, z, trail)
        assert fd_le(1, z, trail)
        assert fd_le(z, 3, trail)
        # Strong propagation: X=1, Y=2, Z=3
        assert deref(x) == 1
        assert deref(y) == 2
        assert deref(z) == 3

    def test_eq_propagation(self):
        """X == Y + 0 (effectively X == Y) — domains intersect."""
        trail = fresh_trail()
        x, y = Var(), Var()
        assert in_domain(x, 1, 5, trail)
        assert in_domain(y, 3, 8, trail)
        assert fd_eq(x, y, trail)
        # After constraint, both should have narrower domains
        sx = get_attr(x, FD_KEY)
        sy = get_attr(y, FD_KEY)
        if sx is not None and sy is not None:
            assert domain_min(sx.domain) >= 3
            assert domain_max(sx.domain) <= 5

    def test_wipeout(self):
        """Constraint leading to empty domain → fail."""
        trail = fresh_trail()
        x = Var()
        assert in_domain(x, 1, 3, trail)
        assert not fd_lt(x, 1, trail)

    def test_backtracking_restores_domains(self):
        trail = fresh_trail()
        x = Var()
        assert in_domain(x, 1, 10, trail)
        mark = trail.mark()
        assert fd_lt(x, 4, trail)
        state_after = get_attr(x, FD_KEY)
        assert state_after is not None
        assert domain_max(state_after.domain) <= 3
        trail.undo(mark)
        state_restored = get_attr(x, FD_KEY)
        assert state_restored is not None
        assert domain_max(state_restored.domain) == 10


# ══════════════════════════════════════════════════════════════════════════════
# Phase 2: Compiler integration
# ══════════════════════════════════════════════════════════════════════════════


class TestCompilerCLPFD:
    def test_ground_eq(self):
        """3 == 3 succeeds, 3 == 4 fails."""
        mod = Module("test_mod")
        goal = StructuralEq(left=3, right=3)
        assert list(solve(goal, module=mod))

    def test_ground_eq_fails(self):
        mod = Module("test_mod")
        goal = StructuralEq(left=3, right=4)
        assert not list(solve(goal, module=mod))

    def test_ground_ne(self):
        mod = Module("test_mod")
        assert list(solve(StructuralNeq(left=3, right=4), module=mod))
        assert not list(solve(StructuralNeq(left=3, right=3), module=mod))

    def test_ground_lt(self):
        mod = Module("test_mod")
        assert list(solve(LtNode(left=1, right=2), module=mod))
        assert not list(solve(LtNode(left=2, right=1), module=mod))

    def test_ground_le(self):
        mod = Module("test_mod")
        assert list(solve(LtENode(left=1, right=1), module=mod))
        assert not list(solve(LtENode(left=2, right=1), module=mod))

    def test_ground_gt(self):
        mod = Module("test_mod")
        assert list(solve(GtNode(left=2, right=1), module=mod))
        assert not list(solve(GtNode(left=1, right=2), module=mod))

    def test_ground_ge(self):
        mod = Module("test_mod")
        assert list(solve(GtENode(left=1, right=1), module=mod))
        assert not list(solve(GtENode(left=0, right=1), module=mod))

    def test_var_eq_via_solve(self):
        """X_ == 5 binds X_ to 5."""
        mod = Module("test_mod")
        x = Var()
        goal = StructuralEq(left=x, right=5)
        results = []
        for _ in solve(goal, module=mod):
            results.append(deref(x))
        assert len(results) == 1
        assert results[0] == 5

    def test_chained_le_via_solve(self):
        """1 <= X_ <= 3, label([X_]) → 3 solutions."""
        mod = Module("test_mod")
        x = Var()
        goal = And(
            left=And(
                left=LtENode(left=1, right=x),
                right=LtENode(left=x, right=3),
            ),
            right=Call(func=LoadName(name="Label"), args=[
                [x],
            ]),
        )
        results = []
        for _ in solve(goal, module=mod):
            results.append(deref(x))
        assert sorted(results) == [1, 2, 3]

    def test_ne_via_solve(self):
        """in_domain(X_, 1, 3), X_ != 2, label([X_]) → [1, 3]."""
        mod = Module("test_mod")
        x = Var()
        goal = And(
            left=And(
                left=Call(func=LoadName(name="InDomain"), args=[x, 1, 3]),
                right=StructuralNeq(left=x, right=2),
            ),
            right=Call(func=LoadName(name="Label"), args=[[x]]),
        )
        results = []
        for _ in solve(goal, module=mod):
            results.append(deref(x))
        assert sorted(results) == [1, 3]

    def test_evaluate_unchanged(self):
        """:= still does eager arithmetic eval."""
        mod = Module("test_mod")
        x = Var()
        goal = Evaluate(left=x, right=Add(position=None, left=2, right=3))
        results = []
        for _ in solve(goal, module=mod):
            results.append(deref(x))
        assert len(results) == 1
        assert results[0] == 5

    def test_is_unify_unchanged(self):
        """is still does unification."""
        mod = Module("test_mod")
        x = Var()
        goal = Is(left=x, right="hello")
        results = []
        for _ in solve(goal, module=mod):
            results.append(deref(x))
        assert len(results) == 1
        assert results[0] == "hello"

    def test_is_not_dif_unchanged(self):
        """is not still does dif/2."""
        mod = Module("test_mod")
        x = Var()
        goal = IsNot(left=x, right=42)
        count = 0
        for _ in solve(goal, module=mod):
            count += 1
        assert count == 1  # dif constraint posted


# ══════════════════════════════════════════════════════════════════════════════
# Phase 3: all_different
# ══════════════════════════════════════════════════════════════════════════════


class TestAllDifferent:
    def test_basic(self):
        trail = fresh_trail()
        x, y, z = Var(), Var(), Var()
        assert in_domain([x, y, z], 1, 3, trail)
        assert all_different([x, y, z], trail)
        results = []
        for _ in label([x, y, z], trail):
            results.append((deref(x), deref(y), deref(z)))
        assert len(results) == 6  # 3! permutations

    def test_all_different_ground_ok(self):
        trail = fresh_trail()
        assert all_different([1, 2, 3], trail)

    def test_all_different_ground_fail(self):
        trail = fresh_trail()
        assert not all_different([1, 2, 1], trail)

    def test_all_different_via_solve(self):
        """all_different([X_, Y_, Z_]), in_domain([X_, Y_, Z_], 1, 3), label(...)."""
        mod = Module("test_mod")
        x, y, z = Var(), Var(), Var()
        goal = And(
            left=And(
                left=Call(func=LoadName(name="InDomain"), args=[[x, y, z], 1, 3]),
                right=Call(func=LoadName(name="AllDifferent"), args=[[x, y, z]]),
            ),
            right=Call(func=LoadName(name="Label"), args=[[x, y, z]]),
        )
        results = []
        for _ in solve(goal, module=mod):
            results.append((deref(x), deref(y), deref(z)))
        assert len(results) == 6


# ══════════════════════════════════════════════════════════════════════════════
# Phase 3: N-Queens
# ══════════════════════════════════════════════════════════════════════════════


class TestNQueens:
    """N-Queens via pure Python CLP(FD) using the clpfd module directly."""

    def _queens(self, n):
        trail = fresh_trail()
        queens = [Var() for _ in range(n)]
        assert in_domain(queens, 1, n, trail)
        assert all_different(queens, trail)

        # Diagonal constraints
        for i in range(n):
            for j in range(i + 1, n):
                diff = j - i
                # queens[i] + diff != queens[j]
                # queens[i] - diff != queens[j]
                assert fd_ne(queens[i], queens[j], trail)  # redundant with all_different, but test it

        # We need diagonal constraints: |qi - qj| != |i - j|
        # Since we can't do abs in CLP(FD) easily, use two constraints:
        # qi - qj != diff AND qj - qi != diff
        # But fd_ne doesn't handle expressions yet... let's use labeling with checks
        results = []
        for _ in label(queens, trail):
            vals = [deref(q) for q in queens]
            # Check diagonals
            ok = True
            for i in range(n):
                for j in range(i + 1, n):
                    if abs(vals[i] - vals[j]) == j - i:
                        ok = False
                        break
                if not ok:
                    break
            if ok:
                results.append(tuple(vals))
        return results

    def test_4_queens(self):
        results = self._queens(4)
        assert len(results) == 2

    def test_8_queens(self):
        results = self._queens(8)
        assert len(results) == 92


# ══════════════════════════════════════════════════════════════════════════════
# Phase 3: SEND + MORE = MONEY
# ══════════════════════════════════════════════════════════════════════════════


class TestSENDMOREMONEY:
    def test_sendmoremoney(self):
        trail = fresh_trail()
        S, E, N, D = Var(), Var(), Var(), Var()
        M, O, R, Y = Var(), Var(), Var(), Var()
        letters = [S, E, N, D, M, O, R, Y]

        from clausal.logic.clpfd import fd_scalar_product

        assert in_domain(letters, 0, 9, trail)
        assert all_different(letters, trail)
        # S and M can't be 0
        assert fd_ne(S, 0, trail)
        assert fd_ne(M, 0, trail)
        # SEND + MORE = MONEY as scalar product:
        # 1000S + 100E + 10N + D + 1000M + 100O + 10R + E
        #   = 10000M + 1000O + 100N + 10E + Y
        # => coeffs [1000, 91, -90, 1, -9000, -900, 10, -1] . [S,E,N,D,M,O,R,Y] = 0
        coeffs = [1000, 91, -90, 1, -9000, -900, 10, -1]
        _FAILED = object()
        results_gen = fd_scalar_product(coeffs, letters, "=", 0, trail)
        assert next(results_gen, _FAILED) is not _FAILED

        results = []
        for _ in label(letters, trail):
            s, e, n, d = deref(S), deref(E), deref(N), deref(D)
            m, o, r, y = deref(M), deref(O), deref(R), deref(Y)
            results.append((s, e, n, d, m, o, r, y))

        assert len(results) == 1
        s, e, n, d, m, o, r, y = results[0]
        assert s == 9 and e == 5 and n == 6 and d == 7
        assert m == 1 and o == 0 and r == 8 and y == 2


# ══════════════════════════════════════════════════════════════════════════════
# FD hook interaction with dif
# ══════════════════════════════════════════════════════════════════════════════


class TestFDAndDif:
    def test_independent(self):
        """FD and dif constraints are independent — both can be on the same var."""
        from clausal.logic.constraints import dif, DIF_KEY

        trail = fresh_trail()
        x = Var()
        assert in_domain(x, 1, 5, trail)
        assert dif(x, 3, trail)
        # Both attrs should be present
        assert get_attr(x, FD_KEY) is not None
        assert get_attr(x, DIF_KEY) is not None
        # Binding to 3 should fail (dif constraint)
        mark = trail.mark()
        assert not unify(x, 3, trail)
        trail.undo(mark)
        # Binding to 2 should succeed
        assert unify(x, 2, trail)
        assert deref(x) == 2


class TestAC3Fixpoint:
    def test_cascaded_lt(self):
        """X < Y < Z, Z ≤ 3, X ≥ 1 → X=1, Y=2, Z=3 without labeling."""
        trail = fresh_trail()
        x, y, z = Var(), Var(), Var()
        in_domain([x, y, z], 1, 100, trail)
        fd_lt(x, y, trail)
        fd_lt(y, z, trail)
        fd_le(z, 3, trail)
        fd_ge(x, 1, trail)
        assert deref(x) == 1
        assert deref(y) == 2
        assert deref(z) == 3

    def test_ne_narrows_after_other_change(self):
        """Z = 1 forces propagation back through X != Z and Y != Z."""
        trail = fresh_trail()
        x, y, z = Var(), Var(), Var()
        in_domain([x, y, z], 1, 3, trail)
        fd_ne(x, z, trail)
        fd_ne(y, z, trail)
        in_domain([z], 1, 1, trail)   # force Z=1
        sx = get_attr(x, FD_KEY)
        sy = get_attr(y, FD_KEY)
        assert not domain_contains(sx.domain, 1)
        assert not domain_contains(sy.domain, 1)
