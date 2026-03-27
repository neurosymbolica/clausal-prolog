"""Tests for Phase 5 — gap-filling builtin extensions.

Covers: lcm, exp_mod, popcount, msb, lsb (arithmetic),
numlist, same_length, transpose (lists), group_pairs_by_key (pairs),
must_be, can_be (error checking), current_time, statistics (time),
sequence (DCG).
"""

from __future__ import annotations

import time

import pytest

from clausal.logic.database import Module
from clausal.logic.solve import solve
from clausal.logic.variables import Var, Trail, deref, is_var, unify
from clausal.terms import Call, LoadName, Quantity


# ── Helpers ──────────────────────────────────────────────────────────────


def fresh_module(name: str = "test") -> Module:
    return Module(name)


def solutions(goal, mod=None, *, limit=50):
    if mod is None:
        mod = fresh_module()
    t = Trail()
    return list(solve(goal, mod, t))


def sol_var(goal, var, *, mod=None):
    if mod is None:
        mod = fresh_module()
    t = Trail()
    return [deref(var) for _ in solve(goal, mod, t)]


def sol_vars(goal, *vars, mod=None):
    if mod is None:
        mod = fresh_module()
    t = Trail()
    return [tuple(deref(v) for v in vars) for _ in solve(goal, mod, t)]


# ── Arithmetic + Quantity support ────────────────────────────────────────


class TestLcm:
    def test_basic(self):
        l = Var()
        goal = Call(func=LoadName(name="lcm"), args=[4, 6, l], kwargs=[])
        assert sol_var(goal, l) == [12]

    def test_coprime(self):
        l = Var()
        goal = Call(func=LoadName(name="lcm"), args=[7, 13, l], kwargs=[])
        assert sol_var(goal, l) == [91]

    def test_with_zero(self):
        l = Var()
        goal = Call(func=LoadName(name="lcm"), args=[0, 5, l], kwargs=[])
        assert sol_var(goal, l) == [0]

    def test_negative(self):
        l = Var()
        goal = Call(func=LoadName(name="lcm"), args=[-4, 6, l], kwargs=[])
        assert sol_var(goal, l) == [12]

    def test_unbound_fails(self):
        goal = Call(func=LoadName(name="lcm"), args=[Var(), 6, Var()], kwargs=[])
        assert solutions(goal) == []


class TestExpMod:
    def test_basic(self):
        r = Var()
        goal = Call(func=LoadName(name="exp_mod"), args=[2, 10, 1000, r], kwargs=[])
        assert sol_var(goal, r) == [1024 % 1000]

    def test_zero_exp(self):
        r = Var()
        goal = Call(func=LoadName(name="exp_mod"), args=[3, 0, 7, r], kwargs=[])
        assert sol_var(goal, r) == [1]

    def test_mod_zero_fails(self):
        goal = Call(func=LoadName(name="exp_mod"), args=[2, 3, 0, Var()], kwargs=[])
        assert solutions(goal) == []

    def test_unbound_fails(self):
        goal = Call(func=LoadName(name="exp_mod"), args=[Var(), 3, 7, Var()], kwargs=[])
        assert solutions(goal) == []


class TestPopcount:
    def test_zero(self):
        c = Var()
        goal = Call(func=LoadName(name="popcount"), args=[0, c], kwargs=[])
        assert sol_var(goal, c) == [0]

    def test_255(self):
        c = Var()
        goal = Call(func=LoadName(name="popcount"), args=[255, c], kwargs=[])
        assert sol_var(goal, c) == [8]

    def test_power_of_two(self):
        c = Var()
        goal = Call(func=LoadName(name="popcount"), args=[16, c], kwargs=[])
        assert sol_var(goal, c) == [1]

    def test_negative_fails(self):
        goal = Call(func=LoadName(name="popcount"), args=[-1, Var()], kwargs=[])
        assert solutions(goal) == []


class TestMsb:
    def test_one(self):
        b = Var()
        goal = Call(func=LoadName(name="msb"), args=[1, b], kwargs=[])
        assert sol_var(goal, b) == [0]

    def test_eight(self):
        b = Var()
        goal = Call(func=LoadName(name="msb"), args=[8, b], kwargs=[])
        assert sol_var(goal, b) == [3]

    def test_255(self):
        b = Var()
        goal = Call(func=LoadName(name="msb"), args=[255, b], kwargs=[])
        assert sol_var(goal, b) == [7]

    def test_zero_fails(self):
        goal = Call(func=LoadName(name="msb"), args=[0, Var()], kwargs=[])
        assert solutions(goal) == []


class TestLsb:
    def test_one(self):
        b = Var()
        goal = Call(func=LoadName(name="lsb"), args=[1, b], kwargs=[])
        assert sol_var(goal, b) == [0]

    def test_twelve(self):
        b = Var()
        goal = Call(func=LoadName(name="lsb"), args=[12, b], kwargs=[])
        assert sol_var(goal, b) == [2]

    def test_eight(self):
        b = Var()
        goal = Call(func=LoadName(name="lsb"), args=[8, b], kwargs=[])
        assert sol_var(goal, b) == [3]

    def test_zero_fails(self):
        goal = Call(func=LoadName(name="lsb"), args=[0, Var()], kwargs=[])
        assert solutions(goal) == []


# ── Arithmetic with Quantity ─────────────────────────────────────────────


class TestArithmeticQuantity:
    """Verify arithmetic builtins work with Quantity values.

    Tests call the simple-mode builtin functions directly (Quantity literals
    can't be passed through the compile→solve pipeline).
    """

    def _q(self, value, **dims):
        """Shorthand for Quantity with named dims."""
        from clausal.modules.py.units import Metre, Second, Kilogram
        dim_map = {"m": Metre, "s": Second, "kg": Kilogram}
        return Quantity(value, {dim_map[k]: v for k, v in dims.items() if v != 0})

    def _simple(self, fn, *args):
        """Run simple-mode builtin, return (solutions, trail).

        Note: bindings may be undone after yield, so capture deref'd values
        inside the generator loop, not after.
        """
        trail = Trail()
        return list(fn(*args, trail, None)), trail

    def _simple_var(self, fn, var, *args):
        """Run simple-mode builtin and capture deref'd var values per solution."""
        trail = Trail()
        return [deref(var) for _ in fn(*args, trail, None)]

    # ── abs_ ──

    def test_abs_quantity(self):
        from clausal.logic.builtins.arithmetic import _abs__2
        q = self._q(-5, m=1)
        result_var = Var()
        results = self._simple_var(_abs__2, result_var, q, result_var)
        assert len(results) == 1
        assert isinstance(results[0], Quantity)
        assert results[0].value == 5

    # ── sign (always dimensionless) ──

    def test_sign_quantity_positive(self):
        from clausal.logic.builtins.arithmetic import _sign__2
        q = self._q(3.0, m=1)
        s = Var()
        results = self._simple_var(_sign__2, s, q, s)
        assert results == [1]

    def test_sign_quantity_negative(self):
        from clausal.logic.builtins.arithmetic import _sign__2
        q = self._q(-7.0, kg=1)
        s = Var()
        results = self._simple_var(_sign__2, s, q, s)
        assert results == [-1]

    # ── max_ / min_ (same dims required, raises on mismatch) ──

    def test_max_quantity(self):
        from clausal.logic.builtins.arithmetic import _max__3
        q1, q2 = self._q(3, m=1), self._q(7, m=1)
        z = Var()
        results = self._simple_var(_max__3, z, q1, q2, z)
        assert len(results) == 1
        assert results[0].value == 7

    def test_min_quantity(self):
        from clausal.logic.builtins.arithmetic import _min__3
        q1, q2 = self._q(3, m=1), self._q(7, m=1)
        z = Var()
        results = self._simple_var(_min__3, z, q1, q2, z)
        assert len(results) == 1
        assert results[0].value == 3

    def test_max_mismatched_dims_raises(self):
        """max_ with different dimensions raises UnitsMismatch."""
        from clausal.logic.builtins.arithmetic import _max__3
        from clausal.terms import UnitsMismatch
        q1, q2 = self._q(3, m=1), self._q(7, s=1)
        with pytest.raises(UnitsMismatch):
            self._simple(_max__3, q1, q2, Var())

    # ── plus (same dims required, raises on mismatch) ──

    def test_plus_quantity(self):
        from clausal.logic.builtins.arithmetic import _plus__3
        q1, q2 = self._q(3, m=1), self._q(4, m=1)
        z = Var()
        results = self._simple_var(_plus__3, z, q1, q2, z)
        assert len(results) == 1
        assert results[0].value == 7

    def test_plus_mismatched_dims_raises(self):
        from clausal.logic.builtins.arithmetic import _plus__3
        from clausal.terms import UnitsMismatch
        q1, q2 = self._q(3, m=1), self._q(4, s=1)
        with pytest.raises(UnitsMismatch):
            self._simple(_plus__3, q1, q2, Var())

    # ── gcd (same dims, result preserves dims) ──

    def test_gcd_quantity(self):
        from clausal.logic.builtins.arithmetic import _gcd__3
        q1, q2 = self._q(12, m=1), self._q(8, m=1)
        g = Var()
        results = self._simple_var(_gcd__3, g, q1, q2, g)
        assert len(results) == 1
        assert isinstance(results[0], Quantity)
        assert results[0].value == 4

    def test_gcd_mismatched_dims_raises(self):
        from clausal.logic.builtins.arithmetic import _gcd__3
        from clausal.terms import UnitsMismatch
        q1, q2 = self._q(12, m=1), self._q(8, s=1)
        with pytest.raises(UnitsMismatch):
            self._simple(_gcd__3, q1, q2, Var())

    # ── Mixed Quantity + plain raises ──

    def test_gcd_mixed_quantity_plain_raises(self):
        """gcd(plain_int, Quantity(dims)) raises UnitsMismatch."""
        from clausal.logic.builtins.arithmetic import _gcd__3
        from clausal.terms import UnitsMismatch
        q = self._q(6, m=1)
        with pytest.raises(UnitsMismatch):
            self._simple(_gcd__3, 4, q, Var())

    def test_lcm_mixed_quantity_plain_raises(self):
        from clausal.logic.builtins.arithmetic import _lcm__3
        from clausal.terms import UnitsMismatch
        q = self._q(6, m=1)
        with pytest.raises(UnitsMismatch):
            self._simple(_lcm__3, 4, q, Var())

    # ── lcm (same dims, result preserves dims) ──

    def test_lcm_quantity(self):
        from clausal.logic.builtins.arithmetic import _lcm__3
        q1, q2 = self._q(4, m=1), self._q(6, m=1)
        l = Var()
        results = self._simple_var(_lcm__3, l, q1, q2, l)
        assert len(results) == 1
        assert isinstance(results[0], Quantity)
        assert results[0].value == 12

    # ── divmod_ (same dims; quotient dimensionless, remainder keeps dims) ──

    def test_divmod_quantity(self):
        from clausal.logic.builtins.arithmetic import _divmod__4
        q1, q2 = self._q(17, m=1), self._q(5, m=1)
        q_var, r_var = Var(), Var()
        trail = Trail()
        results = [(deref(q_var), deref(r_var))
                   for _ in _divmod__4(q1, q2, q_var, r_var, trail, None)]
        assert len(results) == 1
        quotient, remainder = results[0]
        # Quotient is dimensionless
        assert quotient == 3
        assert not isinstance(quotient, Quantity)
        # Remainder preserves dimensions
        assert isinstance(remainder, Quantity)
        assert remainder.value == 2


# ── partition/4 ─────────────────────────────────────────────────────────


class TestPartition:
    def test_basic_partition(self):
        """partition(integer, [1, "a", 2, "b"], Yes, No)."""
        yes, no = Var(), Var()
        goal = Call(func=LoadName(name="partition"),
                    args=[LoadName(name="integer"), [1, "a", 2, "b"], yes, no], kwargs=[])
        mod = fresh_module()
        t = Trail()
        results = [(deref(yes), deref(no)) for _ in solve(goal, mod, t)]
        assert len(results) == 1
        assert results[0] == ([1, 2], ["a", "b"])

    def test_all_match(self):
        yes, no = Var(), Var()
        goal = Call(func=LoadName(name="partition"),
                    args=[LoadName(name="integer"), [1, 2, 3], yes, no], kwargs=[])
        mod = fresh_module()
        t = Trail()
        results = [(deref(yes), deref(no)) for _ in solve(goal, mod, t)]
        assert results == [([1, 2, 3], [])]

    def test_none_match(self):
        yes, no = Var(), Var()
        goal = Call(func=LoadName(name="partition"),
                    args=[LoadName(name="integer"), ["a", "b"], yes, no], kwargs=[])
        mod = fresh_module()
        t = Trail()
        results = [(deref(yes), deref(no)) for _ in solve(goal, mod, t)]
        assert results == [([], ["a", "b"])]

    def test_empty_list(self):
        yes, no = Var(), Var()
        goal = Call(func=LoadName(name="partition"),
                    args=[LoadName(name="integer"), [], yes, no], kwargs=[])
        mod = fresh_module()
        t = Trail()
        results = [(deref(yes), deref(no)) for _ in solve(goal, mod, t)]
        assert results == [([], [])]


# ── tfilter/3 and tpartition/4 (reified) ────────────────────────────────


class TestTFilter:
    """tfilter calls Goal(Elem, T) and keeps elements where T=True."""

    def _make_eq_1_dispatch(self):
        """Create a dispatch for goal(Elem, T) = eq(Elem, 1, T)."""
        from clausal.logic.reif import eq__3

        def goal_eq_1(elem, t, trail, k):
            yield from eq__3(elem, 1, t, trail, k)

        return goal_eq_1

    def _run_tfilter(self, lst):
        from clausal.logic.builtins.higher_order import _tfilter__3
        from clausal.logic.trampoline import DONE
        dispatch = self._make_eq_1_dispatch()
        trail = Trail()
        filtered = Var()
        gen = _tfilter__3(None, None, dispatch, lst, filtered, trail)
        results = []
        for parent, value in gen:
            if value is DONE:
                break
            results.append(deref(filtered))
        return results

    def test_with_reified_eq(self):
        results = self._run_tfilter([1, 2, 1, 3])
        assert len(results) == 1
        assert results[0] == [1, 1]

    def test_empty_list(self):
        results = self._run_tfilter([])
        assert len(results) == 1
        assert results[0] == []

    def test_none_match(self):
        results = self._run_tfilter([2, 3, 4])
        assert len(results) == 1
        assert results[0] == []

    def test_all_match(self):
        results = self._run_tfilter([1, 1, 1])
        assert len(results) == 1
        assert results[0] == [1, 1, 1]


class TestTPartition:
    """tpartition calls Goal(Elem, T) and splits by T=True/T=False."""

    def _make_eq_1_dispatch(self):
        from clausal.logic.reif import eq__3

        def goal_eq_1(elem, t, trail, k):
            yield from eq__3(elem, 1, t, trail, k)

        return goal_eq_1

    def _run_tpartition(self, lst):
        from clausal.logic.builtins.higher_order import _tpartition__4
        from clausal.logic.trampoline import DONE
        dispatch = self._make_eq_1_dispatch()
        trail = Trail()
        yes, no = Var(), Var()
        gen = _tpartition__4(None, None, dispatch, lst, yes, no, trail)
        results = []
        for parent, value in gen:
            if value is DONE:
                break
            results.append((deref(yes), deref(no)))
        return results

    def test_with_reified_eq(self):
        results = self._run_tpartition([1, 2, 1, 3])
        assert len(results) == 1
        assert results[0] == ([1, 1], [2, 3])

    def test_empty_list(self):
        results = self._run_tpartition([])
        assert len(results) == 1
        assert results[0] == ([], [])

    def test_all_true(self):
        results = self._run_tpartition([1, 1])
        assert len(results) == 1
        assert results[0] == ([1, 1], [])

    def test_all_false(self):
        results = self._run_tpartition([2, 3])
        assert len(results) == 1
        assert results[0] == ([], [2, 3])


# ── 5b: Lists ───────────────────────────────────────────────────────────


class TestNumlist:
    def test_range(self):
        l = Var()
        goal = Call(func=LoadName(name="numlist"), args=[1, 5, l], kwargs=[])
        assert sol_var(goal, l) == [[1, 2, 3, 4, 5]]

    def test_single(self):
        l = Var()
        goal = Call(func=LoadName(name="numlist"), args=[3, 3, l], kwargs=[])
        assert sol_var(goal, l) == [[3]]

    def test_empty_fails(self):
        goal = Call(func=LoadName(name="numlist"), args=[5, 3, Var()], kwargs=[])
        assert solutions(goal) == []

    def test_shorthand(self):
        l = Var()
        goal = Call(func=LoadName(name="numlist"), args=[5, l], kwargs=[])
        assert sol_var(goal, l) == [[1, 2, 3, 4, 5]]

    def test_shorthand_one(self):
        l = Var()
        goal = Call(func=LoadName(name="numlist"), args=[1, l], kwargs=[])
        assert sol_var(goal, l) == [[1]]

    def test_unbound_fails(self):
        goal = Call(func=LoadName(name="numlist"), args=[Var(), 5, Var()], kwargs=[])
        assert solutions(goal) == []


class TestSameLength:
    def test_both_ground_equal(self):
        goal = Call(func=LoadName(name="same_length"), args=[[1, 2, 3], ["a", "b", "c"]], kwargs=[])
        assert len(solutions(goal)) == 1

    def test_both_ground_unequal(self):
        goal = Call(func=LoadName(name="same_length"), args=[[1, 2], ["a", "b", "c"]], kwargs=[])
        assert solutions(goal) == []

    def test_generate_from_first(self):
        l2 = Var()
        goal = Call(func=LoadName(name="same_length"), args=[[1, 2, 3], l2], kwargs=[])
        mod = fresh_module()
        t = Trail()
        results = [deref(l2) for _ in solve(goal, mod, t)]
        assert len(results) == 1
        assert isinstance(results[0], list)
        assert len(results[0]) == 3

    def test_generate_from_second(self):
        l1 = Var()
        goal = Call(func=LoadName(name="same_length"), args=[l1, ["a", "b"]], kwargs=[])
        mod = fresh_module()
        t = Trail()
        results = [deref(l1) for _ in solve(goal, mod, t)]
        assert len(results) == 1
        assert isinstance(results[0], list)
        assert len(results[0]) == 2

    def test_empty_lists(self):
        goal = Call(func=LoadName(name="same_length"), args=[[], []], kwargs=[])
        assert len(solutions(goal)) == 1


class TestTranspose:
    def test_2x2(self):
        t = Var()
        goal = Call(func=LoadName(name="transpose"), args=[[[1, 2], [3, 4]], t], kwargs=[])
        assert sol_var(goal, t) == [[[1, 3], [2, 4]]]

    def test_2x3(self):
        t = Var()
        goal = Call(func=LoadName(name="transpose"), args=[[[1, 2, 3], [4, 5, 6]], t], kwargs=[])
        assert sol_var(goal, t) == [[[1, 4], [2, 5], [3, 6]]]

    def test_empty(self):
        t = Var()
        goal = Call(func=LoadName(name="transpose"), args=[[], t], kwargs=[])
        assert sol_var(goal, t) == [[]]

    def test_non_rectangular_fails(self):
        goal = Call(func=LoadName(name="transpose"), args=[[[1, 2], [3]], Var()], kwargs=[])
        assert solutions(goal) == []


# ── 5f: Pairs ───────────────────────────────────────────────────────────


class TestGroupPairsByKey:
    def test_basic(self):
        g = Var()
        goal = Call(func=LoadName(name="group_pairs_by_key"),
                    args=[[["a", 1], ["b", 2], ["a", 3]], g], kwargs=[])
        result = sol_var(goal, g)
        assert len(result) == 1
        groups = result[0]
        assert groups == [["a", [1, 3]], ["b", [2]]]

    def test_all_unique(self):
        g = Var()
        goal = Call(func=LoadName(name="group_pairs_by_key"),
                    args=[[["x", 1], ["y", 2], ["z", 3]], g], kwargs=[])
        result = sol_var(goal, g)
        assert result == [[["x", [1]], ["y", [2]], ["z", [3]]]]

    def test_empty(self):
        g = Var()
        goal = Call(func=LoadName(name="group_pairs_by_key"), args=[[], g], kwargs=[])
        assert sol_var(goal, g) == [[]]

    def test_single_pair(self):
        g = Var()
        goal = Call(func=LoadName(name="group_pairs_by_key"),
                    args=[[["a", 1]], g], kwargs=[])
        assert sol_var(goal, g) == [[["a", [1]]]]

    def test_order_preserved(self):
        g = Var()
        goal = Call(func=LoadName(name="group_pairs_by_key"),
                    args=[[["b", 1], ["a", 2], ["b", 3]], g], kwargs=[])
        result = sol_var(goal, g)
        assert result[0][0][0] == "b"  # b appears first
        assert result[0][1][0] == "a"


# ── 5g: Error ───────────────────────────────────────────────────────────


class TestMustBe:
    def test_integer_succeeds(self):
        goal = Call(func=LoadName(name="must_be"), args=["integer", 42], kwargs=[])
        assert len(solutions(goal)) == 1

    def test_integer_string_throws(self):
        from clausal.logic.exceptions import LogicException
        goal = Call(func=LoadName(name="must_be"), args=["integer", "hello"], kwargs=[])
        with pytest.raises(LogicException):
            solutions(goal)

    def test_unbound_throws_instantiation(self):
        from clausal.logic.exceptions import LogicException
        goal = Call(func=LoadName(name="must_be"), args=["integer", Var()], kwargs=[])
        with pytest.raises(LogicException):
            solutions(goal)

    def test_list_succeeds(self):
        goal = Call(func=LoadName(name="must_be"), args=["list", [1, 2]], kwargs=[])
        assert len(solutions(goal)) == 1

    def test_number_float_succeeds(self):
        goal = Call(func=LoadName(name="must_be"), args=["number", 3.14], kwargs=[])
        assert len(solutions(goal)) == 1

    def test_atom_int_throws(self):
        from clausal.logic.exceptions import LogicException
        goal = Call(func=LoadName(name="must_be"), args=["atom", 42], kwargs=[])
        with pytest.raises(LogicException):
            solutions(goal)


class TestCanBe:
    def test_integer_succeeds(self):
        goal = Call(func=LoadName(name="can_be"), args=["integer", 42], kwargs=[])
        assert len(solutions(goal)) == 1

    def test_unbound_succeeds(self):
        goal = Call(func=LoadName(name="can_be"), args=["integer", Var()], kwargs=[])
        assert len(solutions(goal)) == 1

    def test_wrong_type_throws(self):
        from clausal.logic.exceptions import LogicException
        goal = Call(func=LoadName(name="can_be"), args=["integer", "hello"], kwargs=[])
        with pytest.raises(LogicException):
            solutions(goal)

    def test_dict_succeeds(self):
        from clausal.terms import DictTerm
        goal = Call(func=LoadName(name="can_be"), args=["dict", DictTerm({"a": 1})], kwargs=[])
        assert len(solutions(goal)) == 1


# ── 5i: Time & statistics ───────────────────────────────────────────────


class TestCurrentTime:
    def test_returns_float(self):
        t = Var()
        goal = Call(func=LoadName(name="current_time"), args=[t], kwargs=[])
        result = sol_var(goal, t)
        assert len(result) == 1
        assert isinstance(result[0], float)
        assert result[0] > 0

    def test_monotonic(self):
        """Two calls return non-decreasing values."""
        t1 = Var()
        goal1 = Call(func=LoadName(name="current_time"), args=[t1], kwargs=[])
        v1 = sol_var(goal1, t1)[0]
        t2 = Var()
        goal2 = Call(func=LoadName(name="current_time"), args=[t2], kwargs=[])
        v2 = sol_var(goal2, t2)[0]
        assert v2 >= v1


class TestStatistics:
    def test_cpu_time(self):
        v = Var()
        goal = Call(func=LoadName(name="statistics"), args=["cpu_time", v], kwargs=[])
        result = sol_var(goal, v)
        assert len(result) == 1
        assert isinstance(result[0], float)
        assert result[0] >= 0

    def test_wall_time(self):
        v = Var()
        goal = Call(func=LoadName(name="statistics"), args=["wall_time", v], kwargs=[])
        result = sol_var(goal, v)
        assert len(result) == 1
        assert isinstance(result[0], float)
        assert result[0] >= 0

    def test_enumerate(self):
        """Unbound key enumerates all stats."""
        k, v = Var(), Var()
        goal = Call(func=LoadName(name="statistics"), args=[k, v], kwargs=[])
        mod = fresh_module()
        t = Trail()
        count = 0
        for _ in solve(goal, mod, t):
            count += 1
        assert count >= 2  # at least wall_time and cpu_time

    def test_unknown_key_fails(self):
        goal = Call(func=LoadName(name="statistics"), args=["nonexistent", Var()], kwargs=[])
        assert solutions(goal) == []


# ── 5c: CLP(FD) Global Constraints ──────────────────────────────────────


class TestSum:
    def test_ground_eq(self):
        """sum_([1, 2, 3], #=, 6) succeeds."""
        goal = Call(func=LoadName(name="sum_"), args=[[1, 2, 3], "#=", 6], kwargs=[])
        assert len(solutions(goal)) == 1

    def test_ground_eq_fails(self):
        """sum_([1, 2, 3], #=, 7) fails."""
        goal = Call(func=LoadName(name="sum_"), args=[[1, 2, 3], "#=", 7], kwargs=[])
        assert solutions(goal) == []

    def test_ground_lt(self):
        """sum_([1, 2, 3], #<, 10) succeeds."""
        goal = Call(func=LoadName(name="sum_"), args=[[1, 2, 3], "#<", 10], kwargs=[])
        assert len(solutions(goal)) == 1

    def test_ground_lt_fails(self):
        """sum_([1, 2, 3], #<, 5) fails."""
        goal = Call(func=LoadName(name="sum_"), args=[[1, 2, 3], "#<", 5], kwargs=[])
        assert solutions(goal) == []

    def test_empty_list(self):
        """sum_([], #=, 0) succeeds."""
        goal = Call(func=LoadName(name="sum_"), args=[[], "#=", 0], kwargs=[])
        assert len(solutions(goal)) == 1

    def test_unify_value(self):
        """sum_([1, 2, 3], #=, V) with V unbound → V = 6."""
        v = Var()
        goal = Call(func=LoadName(name="sum_"), args=[[1, 2, 3], "#=", v], kwargs=[])
        result = sol_var(goal, v)
        assert result == [6]


class TestScalarProduct:
    def test_ground(self):
        """scalar_product([2, 3], [4, 5], #=, 23) succeeds (2*4 + 3*5 = 23)."""
        goal = Call(func=LoadName(name="scalar_product"),
                    args=[[2, 3], [4, 5], "#=", 23], kwargs=[])
        assert len(solutions(goal)) == 1

    def test_ground_fails(self):
        goal = Call(func=LoadName(name="scalar_product"),
                    args=[[2, 3], [4, 5], "#=", 10], kwargs=[])
        assert solutions(goal) == []

    def test_mismatched_lengths_fails(self):
        goal = Call(func=LoadName(name="scalar_product"),
                    args=[[1, 2, 3], [4, 5], "#=", 0], kwargs=[])
        assert solutions(goal) == []


class TestElement:
    def test_ground_index(self):
        """element(2, [10, 20, 30], V) → V = 20."""
        v = Var()
        goal = Call(func=LoadName(name="element"), args=[2, [10, 20, 30], v], kwargs=[])
        result = sol_var(goal, v)
        assert result == [20]

    def test_ground_index_first(self):
        v = Var()
        goal = Call(func=LoadName(name="element"), args=[1, [10, 20, 30], v], kwargs=[])
        assert sol_var(goal, v) == [10]

    def test_index_out_of_range_fails(self):
        goal = Call(func=LoadName(name="element"), args=[4, [10, 20, 30], Var()], kwargs=[])
        assert solutions(goal) == []

    def test_index_zero_fails(self):
        goal = Call(func=LoadName(name="element"), args=[0, [10, 20, 30], Var()], kwargs=[])
        assert solutions(goal) == []


class TestCircuit:
    def test_valid_circuit(self):
        """circuit([2, 3, 1]) succeeds (1→2→3→1)."""
        goal = Call(func=LoadName(name="circuit"), args=[[2, 3, 1]], kwargs=[])
        assert len(solutions(goal)) == 1

    def test_self_loop_fails(self):
        """circuit([1, 2, 3]) fails (node 1 points to itself)."""
        goal = Call(func=LoadName(name="circuit"), args=[[1, 2, 3]], kwargs=[])
        assert solutions(goal) == []

    def test_sub_tour_fails(self):
        """circuit([2, 1, 4, 3]) fails (two sub-tours: 1→2→1 and 3→4→3)."""
        goal = Call(func=LoadName(name="circuit"), args=[[2, 1, 4, 3]], kwargs=[])
        assert solutions(goal) == []

    def test_valid_4_node(self):
        """circuit([2, 3, 4, 1]) succeeds (1→2→3→4→1)."""
        goal = Call(func=LoadName(name="circuit"), args=[[2, 3, 4, 1]], kwargs=[])
        assert len(solutions(goal)) == 1


# ── 5d: DCG sequence ────────────────────────────────────────────────────


class TestSequence:
    def test_match_exact(self):
        """phrase(sequence([a, b, c]), [a, b, c]) succeeds."""
        from clausal.logic.builtins.dcg import _sequence__3
        from clausal.logic.trampoline import DONE
        trail = Trail()
        gen = _sequence__3(None, None, ["a", "b", "c"], ["a", "b", "c"], [], trail)
        results = []
        for parent, value in gen:
            if value is DONE:
                break
            results.append(value)
        assert len(results) == 1

    def test_match_with_rest(self):
        """sequence([a, b], [a, b, c], Rest) → Rest = [c]."""
        from clausal.logic.builtins.dcg import _sequence__3
        from clausal.logic.trampoline import DONE
        trail = Trail()
        rest = Var()
        gen = _sequence__3(None, None, ["a", "b"], ["a", "b", "c"], rest, trail)
        results = []
        for parent, value in gen:
            if value is DONE:
                break
            results.append(deref(rest))
        assert len(results) == 1
        assert results[0] == ["c"]

    def test_no_match_fails(self):
        """sequence([a], [b]) fails."""
        from clausal.logic.builtins.dcg import _sequence__3
        from clausal.logic.trampoline import DONE
        trail = Trail()
        gen = _sequence__3(None, None, ["a"], ["b"], [], trail)
        results = []
        for parent, value in gen:
            if value is DONE:
                break
            results.append(value)
        assert len(results) == 0

    def test_empty_sequence(self):
        """sequence([], []) succeeds."""
        from clausal.logic.builtins.dcg import _sequence__3
        from clausal.logic.trampoline import DONE
        trail = Trail()
        gen = _sequence__3(None, None, [], [], [], trail)
        results = []
        for parent, value in gen:
            if value is DONE:
                break
            results.append(value)
        assert len(results) == 1

    def test_too_short_fails(self):
        """sequence([a, b, c], [a, b]) fails."""
        from clausal.logic.builtins.dcg import _sequence__3
        from clausal.logic.trampoline import DONE
        trail = Trail()
        gen = _sequence__3(None, None, ["a", "b", "c"], ["a", "b"], [], trail)
        results = []
        for parent, value in gen:
            if value is DONE:
                break
            results.append(value)
        assert len(results) == 0


# ── Propagation constraint tests ─────────────────────────────────────────────

from clausal.logic.clpfd import (
    FD_KEY, domain_min, domain_max, domain_contains, _post_constraint,
    in_domain, label, fd_sum, fd_scalar_product, fd_element, fd_circuit,
    SumConstraint, ScalarProductConstraint, ElementConstraint, CircuitConstraint,
)
from clausal.logic.variables import get_attr


def fresh_trail():
    return Trail()


class TestSumConstraint:
    def test_sum_narrows_total(self):
        """X in [1,5], Y in [1,5]: sum_([X,Y], #=, T) → T in [2,10]."""
        trail = fresh_trail()
        x, y, t = Var(), Var(), Var()
        in_domain(x, 1, 5, trail)
        in_domain(y, 1, 5, trail)
        assert list(fd_sum([x, y], "#=", t, trail))
        st = get_attr(t, FD_KEY)
        assert domain_min(st.domain) == 2
        assert domain_max(st.domain) == 10

    def test_sum_narrows_vars_from_total(self):
        """X in [1,5], Y in [1,5], T=10: sum_ propagates both to 5."""
        trail = fresh_trail()
        x, y = Var(), Var()
        in_domain(x, 1, 5, trail)
        in_domain(y, 1, 5, trail)
        assert list(fd_sum([x, y], "#=", 10, trail))
        # Propagation fully determines both variables to the unique solution
        assert deref(x) == 5
        assert deref(y) == 5

    def test_sum_wipeout(self):
        """X in [1,3], Y in [1,3], T=10: impossible → no solutions."""
        trail = fresh_trail()
        x, y = Var(), Var()
        in_domain(x, 1, 3, trail)
        in_domain(y, 1, 3, trail)
        assert not list(fd_sum([x, y], "#=", 10, trail))

    def test_sum_lt_narrows(self):
        """X in [1,5], Y in [1,5]: sum_([X,Y], #<, 5) → each max ≤ 3."""
        trail = fresh_trail()
        x, y = Var(), Var()
        in_domain(x, 1, 5, trail)
        in_domain(y, 1, 5, trail)
        assert list(fd_sum([x, y], "#<", 5, trail))
        sx = get_attr(x, FD_KEY)
        sy = get_attr(y, FD_KEY)
        assert domain_max(sx.domain) <= 3
        assert domain_max(sy.domain) <= 3

    def test_sum_propagates_on_label(self):
        """sum_([X,Y], #=, 7), label → only pairs summing to 7."""
        trail = fresh_trail()
        x, y = Var(), Var()
        in_domain(x, 1, 5, trail)
        in_domain(y, 1, 5, trail)
        assert list(fd_sum([x, y], "#=", 7, trail))
        results = []
        for _ in label([x, y], trail):
            results.append((deref(x), deref(y)))
        assert all(a + b == 7 for a, b in results)
        assert len(results) == 4   # (2,5),(3,4),(4,3),(5,2)

    def test_sum_ground_vars_unbound_value_eq(self):
        """sum_([1,2,3], #=, V) with unbound V → V = 6."""
        trail = fresh_trail()
        v = Var()
        assert list(fd_sum([1, 2, 3], "#=", v, trail))
        assert deref(v) == 6

    def test_sum_ground_vars_unbound_value_lt(self):
        """sum_([1,2,3], #<, V) with unbound V → V domain starts at 7."""
        trail = fresh_trail()
        v = Var()
        in_domain(v, 1, 20, trail)
        assert list(fd_sum([1, 2, 3], "#<", v, trail))
        sv = get_attr(v, FD_KEY)
        assert domain_min(sv.domain) == 7


class TestScalarProductConstraint:
    def test_sp_narrows_total(self):
        """2*X + 3*Y, X in [1,5], Y in [1,5] → total in [5,25]."""
        trail = fresh_trail()
        x, y, t = Var(), Var(), Var()
        in_domain(x, 1, 5, trail)
        in_domain(y, 1, 5, trail)
        assert list(fd_scalar_product([2, 3], [x, y], "#=", t, trail))
        st = get_attr(t, FD_KEY)
        assert domain_min(st.domain) == 5
        assert domain_max(st.domain) == 25

    def test_sp_backward_narrows_vars(self):
        """2*X + 3*Y = 12, X in [1,5], Y in [1,5] → Y ≤ 3 (propagation finds unique solution X=3,Y=2)."""
        trail = fresh_trail()
        x, y = Var(), Var()
        in_domain(x, 1, 5, trail)
        in_domain(y, 1, 5, trail)
        assert list(fd_scalar_product([2, 3], [x, y], "#=", 12, trail))
        # Propagation fully determines the unique integer solution in [1,5]
        xv, yv = deref(x), deref(y)
        assert 2 * xv + 3 * yv == 12
        assert yv <= 3

    def test_sp_negative_coeff(self):
        """2*X - Y = 5, X in [1,5], Y in [1,5] → X ≥ 3."""
        trail = fresh_trail()
        x, y = Var(), Var()
        in_domain(x, 1, 5, trail)
        in_domain(y, 1, 5, trail)
        assert list(fd_scalar_product([2, -1], [x, y], "#=", 5, trail))
        sx = get_attr(x, FD_KEY)
        assert domain_min(sx.domain) >= 3

    def test_sp_wipeout(self):
        """[1,1] coeffs (like sum_): [1,3] + [1,3] = 10 impossible."""
        trail = fresh_trail()
        x, y = Var(), Var()
        in_domain(x, 1, 3, trail)
        in_domain(y, 1, 3, trail)
        assert not list(fd_scalar_product([1, 1], [x, y], "#=", 10, trail))


class TestElementConstraint:
    def test_element_narrows_value_from_index_domain(self):
        """Index in [1,2], List=[10,20,30] → Value in {10,20}."""
        trail = fresh_trail()
        idx, val = Var(), Var()
        in_domain(idx, 1, 2, trail)
        assert list(fd_element(idx, [10, 20, 30], val, trail))
        sv = get_attr(val, FD_KEY)
        assert domain_contains(sv.domain, 10)
        assert domain_contains(sv.domain, 20)
        assert not domain_contains(sv.domain, 30)

    def test_element_narrows_index_from_value(self):
        """Value = 20, List=[10,20,30] → Index must be 2."""
        trail = fresh_trail()
        idx = Var()
        in_domain(idx, 1, 3, trail)
        results = list(fd_element(idx, [10, 20, 30], 20, trail))
        assert results
        assert deref(idx) == 2

    def test_element_wipeout(self):
        """Value = 99 not in list → fail."""
        trail = fresh_trail()
        idx = Var()
        in_domain(idx, 1, 3, trail)
        assert not list(fd_element(idx, [10, 20, 30], 99, trail))

    def test_element_var_value_var_index(self):
        """Both unbound: Index in [2,3], List=[10,20,30] → Value in {20,30}."""
        trail = fresh_trail()
        idx, val = Var(), Var()
        in_domain(idx, 2, 3, trail)
        in_domain(val, 1, 100, trail)
        assert list(fd_element(idx, [10, 20, 30], val, trail))
        sv = get_attr(val, FD_KEY)
        assert not domain_contains(sv.domain, 10)
        assert domain_contains(sv.domain, 20)
        assert domain_contains(sv.domain, 30)

    def test_element_narrows_bidirectionally(self):
        """Index in [1,3], Value in {10,30}: only indices 1,3 valid → index ≠ 2."""
        trail = fresh_trail()
        idx, val = Var(), Var()
        in_domain(idx, 1, 3, trail)
        in_domain(val, 1, 100, trail)
        # Narrow value to {10,30} by hand
        from clausal.logic.variables import put_attr
        from clausal.logic.clpfd import FDVar
        put_attr(val, FD_KEY, FDVar(((10, 10), (30, 30))), trail)
        assert list(fd_element(idx, [10, 20, 30], val, trail))
        si = get_attr(idx, FD_KEY)
        assert not domain_contains(si.domain, 2)   # 20 not in value domain


class TestCircuitConstraint:
    def test_circuit_prunes_self_loops(self):
        """Domains initially include self-loops; CircuitConstraint removes them."""
        trail = fresh_trail()
        x, y, z = Var(), Var(), Var()
        in_domain(x, 1, 3, trail)
        in_domain(y, 1, 3, trail)
        in_domain(z, 1, 3, trail)
        constraint = CircuitConstraint((x, y, z))
        assert _post_constraint(constraint, trail)
        sx = get_attr(x, FD_KEY)
        sy = get_attr(y, FD_KEY)
        sz = get_attr(z, FD_KEY)
        assert not domain_contains(sx.domain, 1)
        assert not domain_contains(sy.domain, 2)
        assert not domain_contains(sz.domain, 3)

    def test_circuit_detects_forced_subtour(self):
        """x=2, y=1: forms a 2-cycle → must fail."""
        from clausal.logic.variables import unify as _unify
        trail = fresh_trail()
        x, y, z = Var(), Var(), Var()
        in_domain(x, 1, 3, trail)
        in_domain(y, 1, 3, trail)
        in_domain(z, 1, 3, trail)
        _unify(x, 2, trail)   # node 1 → 2
        _unify(y, 1, trail)   # node 2 → 1 (closes 2-cycle)
        constraint = CircuitConstraint((x, y, z))
        assert not _post_constraint(constraint, trail)

    def test_circuit_forces_completion(self):
        """Chain 1→2→3→? with n=3: last node must close to 1."""
        from clausal.logic.variables import unify as _unify
        trail = fresh_trail()
        x, y, z = Var(), Var(), Var()
        in_domain(x, 1, 3, trail)
        in_domain(y, 1, 3, trail)
        in_domain(z, 1, 3, trail)
        _unify(x, 2, trail)   # node 1 → 2
        _unify(y, 3, trail)   # node 2 → 3
        constraint = CircuitConstraint((x, y, z))
        assert _post_constraint(constraint, trail)
        assert deref(z) == 1

    def test_circuit_all_solutions(self):
        """3-node circuit: exactly 2 Hamiltonian circuits."""
        trail = fresh_trail()
        x, y, z = Var(), Var(), Var()
        in_domain(x, 1, 3, trail)
        in_domain(y, 1, 3, trail)
        in_domain(z, 1, 3, trail)
        results = []
        for _ in fd_circuit([x, y, z], trail):
            results.append((deref(x), deref(y), deref(z)))
        assert len(results) == 2
        assert (2, 3, 1) in results
        assert (3, 1, 2) in results
