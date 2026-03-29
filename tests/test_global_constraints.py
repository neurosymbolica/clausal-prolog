"""Tests for CLP(Z) global constraints: cumulative, global_cardinality, chain,
tuples_in, zcompare.
"""

from __future__ import annotations

import pytest

from clausal.logic.variables import Var, Trail, deref, unify, is_var, get_attr
from clausal.logic.clpfd import (
    FD_KEY,
    domain_min, domain_max, domain_contains, domain_size,
    in_domain, label, fd_eq, all_different,
    cumulative, global_cardinality, chain, tuples_in, zcompare,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def fresh_trail() -> Trail:
    return Trail()


# ══════════════════════════════════════════════════════════════════════════════
# TestCumulative
# ══════════════════════════════════════════════════════════════════════════════


class TestCumulative:
    def test_no_overlap_two_tasks(self):
        """Two tasks needing full capacity cannot overlap."""
        trail = fresh_trail()
        s1, s2 = Var(), Var()
        assert in_domain([s1, s2], 0, 10, trail)
        assert cumulative(
            [(s1, 3, 1), (s2, 2, 1)],
            1,  # capacity
            trail,
        )
        assert fd_eq(s1, 0, trail)
        # s2 must start at 3 or later
        state = get_attr(s2, FD_KEY)
        assert state is not None
        assert domain_min(state.domain) >= 3

    def test_overlapping_tasks_within_capacity(self):
        """Two tasks with combined resource <= capacity CAN overlap."""
        trail = fresh_trail()
        s1, s2 = Var(), Var()
        assert in_domain([s1, s2], 0, 10, trail)
        assert cumulative(
            [(s1, 3, 1), (s2, 2, 1)],
            2,  # capacity 2
            trail,
        )
        # Both can start at 0
        assert fd_eq(s1, 0, trail)
        assert fd_eq(s2, 0, trail)

    def test_three_tasks_propagation(self):
        """Three unit-duration tasks, capacity 1 -> all different start times."""
        trail = fresh_trail()
        s1, s2, s3 = Var(), Var(), Var()
        assert in_domain([s1, s2, s3], 1, 3, trail)
        assert cumulative(
            [(s1, 1, 1), (s2, 1, 1), (s3, 1, 1)],
            1,
            trail,
        )
        results = []
        for _ in label([s1, s2, s3], trail):
            results.append(sorted([deref(s1), deref(s2), deref(s3)]))
        # All solutions should be permutations of [1, 2, 3]
        assert all(r == [1, 2, 3] for r in results)

    def test_infeasible(self):
        """Three tasks of duration 2, capacity 1, horizon 4 -> too tight."""
        trail = fresh_trail()
        s1, s2, s3 = Var(), Var(), Var()
        assert in_domain([s1, s2, s3], 0, 2, trail)
        # 3 tasks x duration 2 = 6 time units needed, but horizon only 5
        # with capacity 1
        result = cumulative(
            [(s1, 2, 1), (s2, 2, 1), (s3, 2, 1)],
            1,
            trail,
        )
        if result:
            # If posting succeeds, labeling should find no solutions
            solutions = list(label([s1, s2, s3], trail))
            assert len(solutions) == 0

    def test_empty_task_list(self):
        """Empty task list is trivially true."""
        trail = fresh_trail()
        assert cumulative([], 1, trail)

    def test_single_task(self):
        """Single task with capacity is trivially satisfiable."""
        trail = fresh_trail()
        s = Var()
        assert in_domain(s, 0, 10, trail)
        assert cumulative([(s, 5, 1)], 1, trail)

    def test_zero_duration_task(self):
        """Zero-duration task is a no-op."""
        trail = fresh_trail()
        s1, s2 = Var(), Var()
        assert in_domain([s1, s2], 0, 5, trail)
        assert cumulative([(s1, 0, 1), (s2, 3, 1)], 1, trail)


# ══════════════════════════════════════════════════════════════════════════════
# TestGlobalCardinality
# ══════════════════════════════════════════════════════════════════════════════


class TestGlobalCardinality:
    def test_basic_cardinality(self):
        """[X, Y, Z] with value 1 appearing exactly twice."""
        trail = fresh_trail()
        x, y, z = Var(), Var(), Var()
        assert in_domain([x, y, z], 1, 3, trail)
        # Value 1 appears 2 times, value 2 appears 1 time
        assert global_cardinality(
            [x, y, z],
            [(1, 2), (2, 1)],
            trail,
        )
        results = []
        for _ in label([x, y, z], trail):
            results.append((deref(x), deref(y), deref(z)))
        # All solutions should have exactly two 1s and one 2
        for r in results:
            assert r.count(1) == 2
            assert r.count(2) == 1

    def test_cardinality_zero_count(self):
        """Value 3 appears 0 times -> excluded from all vars."""
        trail = fresh_trail()
        x, y = Var(), Var()
        assert in_domain([x, y], 1, 3, trail)
        assert global_cardinality([x, y], [(3, 0)], trail)
        # 3 should be removed from both domains
        sx = get_attr(x, FD_KEY)
        assert not domain_contains(sx.domain, 3)
        sy = get_attr(y, FD_KEY)
        assert not domain_contains(sy.domain, 3)

    def test_cardinality_forced(self):
        """If only N vars can take a value and count == N, they must all be that value."""
        trail = fresh_trail()
        x, y = Var(), Var()
        assert in_domain([x, y], 1, 2, trail)
        # Value 1 must appear exactly twice -> both must be 1
        assert global_cardinality([x, y], [(1, 2)], trail)
        assert deref(x) == 1
        assert deref(y) == 1

    def test_cardinality_infeasible(self):
        """Infeasible: value 1 must appear 3 times in 2 vars."""
        trail = fresh_trail()
        x, y = Var(), Var()
        assert in_domain([x, y], 1, 3, trail)
        result = global_cardinality([x, y], [(1, 3)], trail)
        assert not result


# ══════════════════════════════════════════════════════════════════════════════
# TestChain
# ══════════════════════════════════════════════════════════════════════════════


class TestChain:
    def test_increasing_chain(self):
        """chain([X, Y, Z], "lt") -> X < Y < Z."""
        trail = fresh_trail()
        x, y, z = Var(), Var(), Var()
        assert in_domain([x, y, z], 1, 5, trail)
        assert chain([x, y, z], "lt", trail)
        # Should propagate bounds
        sx = get_attr(x, FD_KEY)
        sy = get_attr(y, FD_KEY)
        sz = get_attr(z, FD_KEY)
        if sx is not None:
            assert domain_max(sx.domain) <= 3
        if sz is not None:
            assert domain_min(sz.domain) >= 3

    def test_increasing_chain_tight(self):
        """chain([X, Y, Z], "lt") with domain 1..3 forces X=1, Y=2, Z=3."""
        trail = fresh_trail()
        x, y, z = Var(), Var(), Var()
        assert in_domain([x, y, z], 1, 3, trail)
        assert chain([x, y, z], "lt", trail)
        assert deref(x) == 1
        assert deref(y) == 2
        assert deref(z) == 3

    def test_decreasing_chain(self):
        """chain([X, Y, Z], "gt") -> X > Y > Z."""
        trail = fresh_trail()
        x, y, z = Var(), Var(), Var()
        assert in_domain([x, y, z], 1, 3, trail)
        assert chain([x, y, z], "gt", trail)
        assert deref(x) == 3
        assert deref(y) == 2
        assert deref(z) == 1

    def test_chain_single_element(self):
        """Chain of length 1 is trivially true."""
        trail = fresh_trail()
        x = Var()
        assert in_domain(x, 1, 5, trail)
        assert chain([x], "lt", trail)

    def test_chain_le(self):
        """chain([X, Y, Z], "le") with domain 1..2."""
        trail = fresh_trail()
        x, y, z = Var(), Var(), Var()
        assert in_domain([x, y, z], 1, 2, trail)
        assert chain([x, y, z], "le", trail)
        results = []
        for _ in label([x, y, z], trail):
            results.append((deref(x), deref(y), deref(z)))
        # All solutions should satisfy x <= y <= z
        for a, b, c in results:
            assert a <= b <= c


# ══════════════════════════════════════════════════════════════════════════════
# TestTuplesIn
# ══════════════════════════════════════════════════════════════════════════════


class TestTuplesIn:
    def test_basic_table(self):
        """[X, Y] must be one of [(1,2), (3,4)]."""
        trail = fresh_trail()
        x, y = Var(), Var()
        assert in_domain([x, y], 1, 5, trail)
        assert tuples_in([[x, y]], [(1, 2), (3, 4)], trail)
        results = []
        for _ in label([x, y], trail):
            results.append((deref(x), deref(y)))
        assert set(results) == {(1, 2), (3, 4)}

    def test_table_propagation(self):
        """If X=1, then Y must be 2 (only matching tuple)."""
        trail = fresh_trail()
        x, y = Var(), Var()
        assert in_domain([x, y], 1, 5, trail)
        assert tuples_in([[x, y]], [(1, 2), (3, 4)], trail)
        assert fd_eq(x, 1, trail)
        assert deref(y) == 2

    def test_table_no_match_fails(self):
        """If X=2, no tuple matches -> fail."""
        trail = fresh_trail()
        x, y = Var(), Var()
        assert in_domain([x, y], 1, 5, trail)
        assert tuples_in([[x, y]], [(1, 2), (3, 4)], trail)
        assert not fd_eq(x, 2, trail)

    def test_empty_relation_fails(self):
        """Empty relation -> fails immediately."""
        trail = fresh_trail()
        x, y = Var(), Var()
        assert in_domain([x, y], 1, 5, trail)
        assert not tuples_in([[x, y]], [], trail)

    def test_domain_filtering(self):
        """Posting tuples_in should remove impossible values from domains."""
        trail = fresh_trail()
        x, y = Var(), Var()
        assert in_domain([x, y], 1, 5, trail)
        assert tuples_in([[x, y]], [(1, 2), (3, 4)], trail)
        # X's domain should only contain {1, 3}
        sx = get_attr(x, FD_KEY)
        if sx is not None:
            assert domain_contains(sx.domain, 1)
            assert domain_contains(sx.domain, 3)
            assert not domain_contains(sx.domain, 2)
            assert not domain_contains(sx.domain, 4)
            assert not domain_contains(sx.domain, 5)


# ══════════════════════════════════════════════════════════════════════════════
# TestZcompare
# ══════════════════════════════════════════════════════════════════════════════


class TestZcompare:
    def test_ground_less(self):
        """zcompare(Order, 1, 5) -> Order = '<'."""
        trail = fresh_trail()
        order = Var()
        assert zcompare(order, 1, 5, trail)
        assert deref(order) == '<'

    def test_ground_greater(self):
        """zcompare(Order, 5, 1) -> Order = '>'."""
        trail = fresh_trail()
        order = Var()
        assert zcompare(order, 5, 1, trail)
        assert deref(order) == '>'

    def test_ground_equal(self):
        """zcompare(Order, 3, 3) -> Order = '='."""
        trail = fresh_trail()
        order = Var()
        assert zcompare(order, 3, 3, trail)
        assert deref(order) == '='

    def test_var_determined_by_domains(self):
        """When domains don't overlap, order is determined."""
        trail = fresh_trail()
        x, y, order = Var(), Var(), Var()
        assert in_domain(x, 1, 3, trail)
        assert in_domain(y, 5, 8, trail)
        assert zcompare(order, x, y, trail)
        assert deref(order) == '<'

    def test_order_ground_constrains_vars(self):
        """zcompare('<', X, Y) constrains X < Y."""
        trail = fresh_trail()
        x, y = Var(), Var()
        assert in_domain([x, y], 1, 5, trail)
        assert zcompare('<', x, y, trail)
        sx = get_attr(x, FD_KEY)
        sy = get_attr(y, FD_KEY)
        if sx is not None:
            assert domain_max(sx.domain) <= 4
        if sy is not None:
            assert domain_min(sy.domain) >= 2

    def test_undetermined(self):
        """When domains overlap, order stays unbound."""
        trail = fresh_trail()
        x, y, order = Var(), Var(), Var()
        assert in_domain([x, y], 1, 5, trail)
        assert zcompare(order, x, y, trail)
        assert is_var(deref(order))


# ══════════════════════════════════════════════════════════════════════════════
# TestBacktracking — trail safety for global constraints
# ══════════════════════════════════════════════════════════════════════════════


class TestBacktracking:
    def test_cumulative_undo(self):
        """Cumulative constraint is undone cleanly by trail.undo()."""
        trail = fresh_trail()
        s1, s2 = Var(), Var()
        assert in_domain([s1, s2], 0, 10, trail)
        mark = trail.mark()
        assert cumulative([(s1, 3, 1), (s2, 2, 1)], 1, trail)
        assert fd_eq(s1, 0, trail)
        trail.undo(mark)
        # After undo, s1 should be unbound again
        assert is_var(deref(s1))

    def test_global_cardinality_undo(self):
        """Global cardinality constraint is undone cleanly."""
        trail = fresh_trail()
        x, y = Var(), Var()
        assert in_domain([x, y], 1, 3, trail)
        mark = trail.mark()
        assert global_cardinality([x, y], [(1, 2)], trail)
        assert deref(x) == 1
        trail.undo(mark)
        assert is_var(deref(x))

    def test_tuples_in_undo(self):
        """TuplesIn constraint is undone cleanly."""
        trail = fresh_trail()
        x, y = Var(), Var()
        assert in_domain([x, y], 1, 5, trail)
        mark = trail.mark()
        assert tuples_in([[x, y]], [(1, 2), (3, 4)], trail)
        sx = get_attr(x, FD_KEY)
        assert not domain_contains(sx.domain, 2)
        trail.undo(mark)
        sx_after = get_attr(x, FD_KEY)
        assert domain_contains(sx_after.domain, 2)

    def test_chain_undo(self):
        """Chain constraint is undone cleanly."""
        trail = fresh_trail()
        x, y, z = Var(), Var(), Var()
        assert in_domain([x, y, z], 1, 3, trail)
        mark = trail.mark()
        assert chain([x, y, z], "lt", trail)
        assert deref(x) == 1
        trail.undo(mark)
        assert is_var(deref(x))
