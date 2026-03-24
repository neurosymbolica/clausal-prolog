"""Tests for Phase 5 — gap-filling builtin extensions.

Covers: Lcm, ExpMod, Popcount, Msb, Lsb (arithmetic),
Numlist, SameLength, Transpose (lists), GroupPairsByKey (pairs),
MustBe, CanBe (error checking), CurrentTime, Statistics (time),
Sequence (DCG).
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
        goal = Call(func=LoadName(name="Lcm"), args=[4, 6, l], kwargs=[])
        assert sol_var(goal, l) == [12]

    def test_coprime(self):
        l = Var()
        goal = Call(func=LoadName(name="Lcm"), args=[7, 13, l], kwargs=[])
        assert sol_var(goal, l) == [91]

    def test_with_zero(self):
        l = Var()
        goal = Call(func=LoadName(name="Lcm"), args=[0, 5, l], kwargs=[])
        assert sol_var(goal, l) == [0]

    def test_negative(self):
        l = Var()
        goal = Call(func=LoadName(name="Lcm"), args=[-4, 6, l], kwargs=[])
        assert sol_var(goal, l) == [12]

    def test_unbound_fails(self):
        goal = Call(func=LoadName(name="Lcm"), args=[Var(), 6, Var()], kwargs=[])
        assert solutions(goal) == []


class TestExpMod:
    def test_basic(self):
        r = Var()
        goal = Call(func=LoadName(name="ExpMod"), args=[2, 10, 1000, r], kwargs=[])
        assert sol_var(goal, r) == [1024 % 1000]

    def test_zero_exp(self):
        r = Var()
        goal = Call(func=LoadName(name="ExpMod"), args=[3, 0, 7, r], kwargs=[])
        assert sol_var(goal, r) == [1]

    def test_mod_zero_fails(self):
        goal = Call(func=LoadName(name="ExpMod"), args=[2, 3, 0, Var()], kwargs=[])
        assert solutions(goal) == []

    def test_unbound_fails(self):
        goal = Call(func=LoadName(name="ExpMod"), args=[Var(), 3, 7, Var()], kwargs=[])
        assert solutions(goal) == []


class TestPopcount:
    def test_zero(self):
        c = Var()
        goal = Call(func=LoadName(name="Popcount"), args=[0, c], kwargs=[])
        assert sol_var(goal, c) == [0]

    def test_255(self):
        c = Var()
        goal = Call(func=LoadName(name="Popcount"), args=[255, c], kwargs=[])
        assert sol_var(goal, c) == [8]

    def test_power_of_two(self):
        c = Var()
        goal = Call(func=LoadName(name="Popcount"), args=[16, c], kwargs=[])
        assert sol_var(goal, c) == [1]

    def test_negative_fails(self):
        goal = Call(func=LoadName(name="Popcount"), args=[-1, Var()], kwargs=[])
        assert solutions(goal) == []


class TestMsb:
    def test_one(self):
        b = Var()
        goal = Call(func=LoadName(name="Msb"), args=[1, b], kwargs=[])
        assert sol_var(goal, b) == [0]

    def test_eight(self):
        b = Var()
        goal = Call(func=LoadName(name="Msb"), args=[8, b], kwargs=[])
        assert sol_var(goal, b) == [3]

    def test_255(self):
        b = Var()
        goal = Call(func=LoadName(name="Msb"), args=[255, b], kwargs=[])
        assert sol_var(goal, b) == [7]

    def test_zero_fails(self):
        goal = Call(func=LoadName(name="Msb"), args=[0, Var()], kwargs=[])
        assert solutions(goal) == []


class TestLsb:
    def test_one(self):
        b = Var()
        goal = Call(func=LoadName(name="Lsb"), args=[1, b], kwargs=[])
        assert sol_var(goal, b) == [0]

    def test_twelve(self):
        b = Var()
        goal = Call(func=LoadName(name="Lsb"), args=[12, b], kwargs=[])
        assert sol_var(goal, b) == [2]

    def test_eight(self):
        b = Var()
        goal = Call(func=LoadName(name="Lsb"), args=[8, b], kwargs=[])
        assert sol_var(goal, b) == [3]

    def test_zero_fails(self):
        goal = Call(func=LoadName(name="Lsb"), args=[0, Var()], kwargs=[])
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

    # ── Abs ──

    def test_abs_quantity(self):
        from clausal.logic.builtins.arithmetic import _abs__2
        q = self._q(-5, m=1)
        result_var = Var()
        results = self._simple_var(_abs__2, result_var, q, result_var)
        assert len(results) == 1
        assert isinstance(results[0], Quantity)
        assert results[0].value == 5

    # ── Sign (always dimensionless) ──

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

    # ── Max / Min (same dims required, raises on mismatch) ──

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
        """Max with different dimensions raises UnitsMismatch."""
        from clausal.logic.builtins.arithmetic import _max__3
        from clausal.terms import UnitsMismatch
        q1, q2 = self._q(3, m=1), self._q(7, s=1)
        with pytest.raises(UnitsMismatch):
            self._simple(_max__3, q1, q2, Var())

    # ── Plus (same dims required, raises on mismatch) ──

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

    # ── Gcd (same dims, result preserves dims) ──

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
        """Gcd(plain_int, Quantity(dims)) raises UnitsMismatch."""
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

    # ── Lcm (same dims, result preserves dims) ──

    def test_lcm_quantity(self):
        from clausal.logic.builtins.arithmetic import _lcm__3
        q1, q2 = self._q(4, m=1), self._q(6, m=1)
        l = Var()
        results = self._simple_var(_lcm__3, l, q1, q2, l)
        assert len(results) == 1
        assert isinstance(results[0], Quantity)
        assert results[0].value == 12

    # ── DivMod (same dims; quotient dimensionless, remainder keeps dims) ──

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


# ── Partition/4 ─────────────────────────────────────────────────────────


class TestPartition:
    def test_basic_partition(self):
        """Partition(IsInt, [1, "a", 2, "b"], Yes, No)."""
        yes, no = Var(), Var()
        goal = Call(func=LoadName(name="Partition"),
                    args=[LoadName(name="IsInt"), [1, "a", 2, "b"], yes, no], kwargs=[])
        mod = fresh_module()
        t = Trail()
        results = [(deref(yes), deref(no)) for _ in solve(goal, mod, t)]
        assert len(results) == 1
        assert results[0] == ([1, 2], ["a", "b"])

    def test_all_match(self):
        yes, no = Var(), Var()
        goal = Call(func=LoadName(name="Partition"),
                    args=[LoadName(name="IsInt"), [1, 2, 3], yes, no], kwargs=[])
        mod = fresh_module()
        t = Trail()
        results = [(deref(yes), deref(no)) for _ in solve(goal, mod, t)]
        assert results == [([1, 2, 3], [])]

    def test_none_match(self):
        yes, no = Var(), Var()
        goal = Call(func=LoadName(name="Partition"),
                    args=[LoadName(name="IsInt"), ["a", "b"], yes, no], kwargs=[])
        mod = fresh_module()
        t = Trail()
        results = [(deref(yes), deref(no)) for _ in solve(goal, mod, t)]
        assert results == [([], ["a", "b"])]

    def test_empty_list(self):
        yes, no = Var(), Var()
        goal = Call(func=LoadName(name="Partition"),
                    args=[LoadName(name="IsInt"), [], yes, no], kwargs=[])
        mod = fresh_module()
        t = Trail()
        results = [(deref(yes), deref(no)) for _ in solve(goal, mod, t)]
        assert results == [([], [])]


# ── TFilter/3 and TPartition/4 (reified) ────────────────────────────────


class TestTFilter:
    """TFilter calls Goal(Elem, T) and keeps elements where T=True."""

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
    """TPartition calls Goal(Elem, T) and splits by T=True/T=False."""

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
        goal = Call(func=LoadName(name="Numlist"), args=[1, 5, l], kwargs=[])
        assert sol_var(goal, l) == [[1, 2, 3, 4, 5]]

    def test_single(self):
        l = Var()
        goal = Call(func=LoadName(name="Numlist"), args=[3, 3, l], kwargs=[])
        assert sol_var(goal, l) == [[3]]

    def test_empty_fails(self):
        goal = Call(func=LoadName(name="Numlist"), args=[5, 3, Var()], kwargs=[])
        assert solutions(goal) == []

    def test_shorthand(self):
        l = Var()
        goal = Call(func=LoadName(name="Numlist"), args=[5, l], kwargs=[])
        assert sol_var(goal, l) == [[1, 2, 3, 4, 5]]

    def test_shorthand_one(self):
        l = Var()
        goal = Call(func=LoadName(name="Numlist"), args=[1, l], kwargs=[])
        assert sol_var(goal, l) == [[1]]

    def test_unbound_fails(self):
        goal = Call(func=LoadName(name="Numlist"), args=[Var(), 5, Var()], kwargs=[])
        assert solutions(goal) == []


class TestSameLength:
    def test_both_ground_equal(self):
        goal = Call(func=LoadName(name="SameLength"), args=[[1, 2, 3], ["a", "b", "c"]], kwargs=[])
        assert len(solutions(goal)) == 1

    def test_both_ground_unequal(self):
        goal = Call(func=LoadName(name="SameLength"), args=[[1, 2], ["a", "b", "c"]], kwargs=[])
        assert solutions(goal) == []

    def test_generate_from_first(self):
        l2 = Var()
        goal = Call(func=LoadName(name="SameLength"), args=[[1, 2, 3], l2], kwargs=[])
        mod = fresh_module()
        t = Trail()
        results = [deref(l2) for _ in solve(goal, mod, t)]
        assert len(results) == 1
        assert isinstance(results[0], list)
        assert len(results[0]) == 3

    def test_generate_from_second(self):
        l1 = Var()
        goal = Call(func=LoadName(name="SameLength"), args=[l1, ["a", "b"]], kwargs=[])
        mod = fresh_module()
        t = Trail()
        results = [deref(l1) for _ in solve(goal, mod, t)]
        assert len(results) == 1
        assert isinstance(results[0], list)
        assert len(results[0]) == 2

    def test_empty_lists(self):
        goal = Call(func=LoadName(name="SameLength"), args=[[], []], kwargs=[])
        assert len(solutions(goal)) == 1


class TestTranspose:
    def test_2x2(self):
        t = Var()
        goal = Call(func=LoadName(name="Transpose"), args=[[[1, 2], [3, 4]], t], kwargs=[])
        assert sol_var(goal, t) == [[[1, 3], [2, 4]]]

    def test_2x3(self):
        t = Var()
        goal = Call(func=LoadName(name="Transpose"), args=[[[1, 2, 3], [4, 5, 6]], t], kwargs=[])
        assert sol_var(goal, t) == [[[1, 4], [2, 5], [3, 6]]]

    def test_empty(self):
        t = Var()
        goal = Call(func=LoadName(name="Transpose"), args=[[], t], kwargs=[])
        assert sol_var(goal, t) == [[]]

    def test_non_rectangular_fails(self):
        goal = Call(func=LoadName(name="Transpose"), args=[[[1, 2], [3]], Var()], kwargs=[])
        assert solutions(goal) == []


# ── 5f: Pairs ───────────────────────────────────────────────────────────


class TestGroupPairsByKey:
    def test_basic(self):
        g = Var()
        goal = Call(func=LoadName(name="GroupPairsByKey"),
                    args=[[["a", 1], ["b", 2], ["a", 3]], g], kwargs=[])
        result = sol_var(goal, g)
        assert len(result) == 1
        groups = result[0]
        assert groups == [["a", [1, 3]], ["b", [2]]]

    def test_all_unique(self):
        g = Var()
        goal = Call(func=LoadName(name="GroupPairsByKey"),
                    args=[[["x", 1], ["y", 2], ["z", 3]], g], kwargs=[])
        result = sol_var(goal, g)
        assert result == [[["x", [1]], ["y", [2]], ["z", [3]]]]

    def test_empty(self):
        g = Var()
        goal = Call(func=LoadName(name="GroupPairsByKey"), args=[[], g], kwargs=[])
        assert sol_var(goal, g) == [[]]

    def test_single_pair(self):
        g = Var()
        goal = Call(func=LoadName(name="GroupPairsByKey"),
                    args=[[["a", 1]], g], kwargs=[])
        assert sol_var(goal, g) == [[["a", [1]]]]

    def test_order_preserved(self):
        g = Var()
        goal = Call(func=LoadName(name="GroupPairsByKey"),
                    args=[[["b", 1], ["a", 2], ["b", 3]], g], kwargs=[])
        result = sol_var(goal, g)
        assert result[0][0][0] == "b"  # b appears first
        assert result[0][1][0] == "a"


# ── 5g: Error ───────────────────────────────────────────────────────────


class TestMustBe:
    def test_integer_succeeds(self):
        goal = Call(func=LoadName(name="MustBe"), args=["integer", 42], kwargs=[])
        assert len(solutions(goal)) == 1

    def test_integer_string_throws(self):
        from clausal.logic.exceptions import LogicException
        goal = Call(func=LoadName(name="MustBe"), args=["integer", "hello"], kwargs=[])
        with pytest.raises(LogicException):
            solutions(goal)

    def test_unbound_throws_instantiation(self):
        from clausal.logic.exceptions import LogicException
        goal = Call(func=LoadName(name="MustBe"), args=["integer", Var()], kwargs=[])
        with pytest.raises(LogicException):
            solutions(goal)

    def test_list_succeeds(self):
        goal = Call(func=LoadName(name="MustBe"), args=["list", [1, 2]], kwargs=[])
        assert len(solutions(goal)) == 1

    def test_number_float_succeeds(self):
        goal = Call(func=LoadName(name="MustBe"), args=["number", 3.14], kwargs=[])
        assert len(solutions(goal)) == 1

    def test_atom_int_throws(self):
        from clausal.logic.exceptions import LogicException
        goal = Call(func=LoadName(name="MustBe"), args=["atom", 42], kwargs=[])
        with pytest.raises(LogicException):
            solutions(goal)


class TestCanBe:
    def test_integer_succeeds(self):
        goal = Call(func=LoadName(name="CanBe"), args=["integer", 42], kwargs=[])
        assert len(solutions(goal)) == 1

    def test_unbound_succeeds(self):
        goal = Call(func=LoadName(name="CanBe"), args=["integer", Var()], kwargs=[])
        assert len(solutions(goal)) == 1

    def test_wrong_type_throws(self):
        from clausal.logic.exceptions import LogicException
        goal = Call(func=LoadName(name="CanBe"), args=["integer", "hello"], kwargs=[])
        with pytest.raises(LogicException):
            solutions(goal)

    def test_dict_succeeds(self):
        from clausal.terms import DictTerm
        goal = Call(func=LoadName(name="CanBe"), args=["dict", DictTerm({"a": 1})], kwargs=[])
        assert len(solutions(goal)) == 1


# ── 5i: Time & Statistics ───────────────────────────────────────────────


class TestCurrentTime:
    def test_returns_float(self):
        t = Var()
        goal = Call(func=LoadName(name="CurrentTime"), args=[t], kwargs=[])
        result = sol_var(goal, t)
        assert len(result) == 1
        assert isinstance(result[0], float)
        assert result[0] > 0

    def test_monotonic(self):
        """Two calls return non-decreasing values."""
        t1 = Var()
        goal1 = Call(func=LoadName(name="CurrentTime"), args=[t1], kwargs=[])
        v1 = sol_var(goal1, t1)[0]
        t2 = Var()
        goal2 = Call(func=LoadName(name="CurrentTime"), args=[t2], kwargs=[])
        v2 = sol_var(goal2, t2)[0]
        assert v2 >= v1


class TestStatistics:
    def test_cpu_time(self):
        v = Var()
        goal = Call(func=LoadName(name="Statistics"), args=["cpu_time", v], kwargs=[])
        result = sol_var(goal, v)
        assert len(result) == 1
        assert isinstance(result[0], float)
        assert result[0] >= 0

    def test_wall_time(self):
        v = Var()
        goal = Call(func=LoadName(name="Statistics"), args=["wall_time", v], kwargs=[])
        result = sol_var(goal, v)
        assert len(result) == 1
        assert isinstance(result[0], float)
        assert result[0] >= 0

    def test_enumerate(self):
        """Unbound key enumerates all stats."""
        k, v = Var(), Var()
        goal = Call(func=LoadName(name="Statistics"), args=[k, v], kwargs=[])
        mod = fresh_module()
        t = Trail()
        count = 0
        for _ in solve(goal, mod, t):
            count += 1
        assert count >= 2  # at least wall_time and cpu_time

    def test_unknown_key_fails(self):
        goal = Call(func=LoadName(name="Statistics"), args=["nonexistent", Var()], kwargs=[])
        assert solutions(goal) == []


# ── 5c: CLP(FD) Global Constraints ──────────────────────────────────────


class TestSum:
    def test_ground_eq(self):
        """Sum([1, 2, 3], #=, 6) succeeds."""
        goal = Call(func=LoadName(name="Sum"), args=[[1, 2, 3], "#=", 6], kwargs=[])
        assert len(solutions(goal)) == 1

    def test_ground_eq_fails(self):
        """Sum([1, 2, 3], #=, 7) fails."""
        goal = Call(func=LoadName(name="Sum"), args=[[1, 2, 3], "#=", 7], kwargs=[])
        assert solutions(goal) == []

    def test_ground_lt(self):
        """Sum([1, 2, 3], #<, 10) succeeds."""
        goal = Call(func=LoadName(name="Sum"), args=[[1, 2, 3], "#<", 10], kwargs=[])
        assert len(solutions(goal)) == 1

    def test_ground_lt_fails(self):
        """Sum([1, 2, 3], #<, 5) fails."""
        goal = Call(func=LoadName(name="Sum"), args=[[1, 2, 3], "#<", 5], kwargs=[])
        assert solutions(goal) == []

    def test_empty_list(self):
        """Sum([], #=, 0) succeeds."""
        goal = Call(func=LoadName(name="Sum"), args=[[], "#=", 0], kwargs=[])
        assert len(solutions(goal)) == 1

    def test_unify_value(self):
        """Sum([1, 2, 3], #=, V) with V unbound → V = 6."""
        v = Var()
        goal = Call(func=LoadName(name="Sum"), args=[[1, 2, 3], "#=", v], kwargs=[])
        result = sol_var(goal, v)
        assert result == [6]


class TestScalarProduct:
    def test_ground(self):
        """ScalarProduct([2, 3], [4, 5], #=, 23) succeeds (2*4 + 3*5 = 23)."""
        goal = Call(func=LoadName(name="ScalarProduct"),
                    args=[[2, 3], [4, 5], "#=", 23], kwargs=[])
        assert len(solutions(goal)) == 1

    def test_ground_fails(self):
        goal = Call(func=LoadName(name="ScalarProduct"),
                    args=[[2, 3], [4, 5], "#=", 10], kwargs=[])
        assert solutions(goal) == []

    def test_mismatched_lengths_fails(self):
        goal = Call(func=LoadName(name="ScalarProduct"),
                    args=[[1, 2, 3], [4, 5], "#=", 0], kwargs=[])
        assert solutions(goal) == []


class TestElement:
    def test_ground_index(self):
        """Element(2, [10, 20, 30], V) → V = 20."""
        v = Var()
        goal = Call(func=LoadName(name="Element"), args=[2, [10, 20, 30], v], kwargs=[])
        result = sol_var(goal, v)
        assert result == [20]

    def test_ground_index_first(self):
        v = Var()
        goal = Call(func=LoadName(name="Element"), args=[1, [10, 20, 30], v], kwargs=[])
        assert sol_var(goal, v) == [10]

    def test_index_out_of_range_fails(self):
        goal = Call(func=LoadName(name="Element"), args=[4, [10, 20, 30], Var()], kwargs=[])
        assert solutions(goal) == []

    def test_index_zero_fails(self):
        goal = Call(func=LoadName(name="Element"), args=[0, [10, 20, 30], Var()], kwargs=[])
        assert solutions(goal) == []


class TestCircuit:
    def test_valid_circuit(self):
        """Circuit([2, 3, 1]) succeeds (1→2→3→1)."""
        goal = Call(func=LoadName(name="Circuit"), args=[[2, 3, 1]], kwargs=[])
        assert len(solutions(goal)) == 1

    def test_self_loop_fails(self):
        """Circuit([1, 2, 3]) fails (node 1 points to itself)."""
        goal = Call(func=LoadName(name="Circuit"), args=[[1, 2, 3]], kwargs=[])
        assert solutions(goal) == []

    def test_sub_tour_fails(self):
        """Circuit([2, 1, 4, 3]) fails (two sub-tours: 1→2→1 and 3→4→3)."""
        goal = Call(func=LoadName(name="Circuit"), args=[[2, 1, 4, 3]], kwargs=[])
        assert solutions(goal) == []

    def test_valid_4_node(self):
        """Circuit([2, 3, 4, 1]) succeeds (1→2→3→4→1)."""
        goal = Call(func=LoadName(name="Circuit"), args=[[2, 3, 4, 1]], kwargs=[])
        assert len(solutions(goal)) == 1


# ── 5d: DCG Sequence ────────────────────────────────────────────────────


class TestSequence:
    def test_match_exact(self):
        """phrase(Sequence([a, b, c]), [a, b, c]) succeeds."""
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
        """Sequence([a, b], [a, b, c], Rest) → Rest = [c]."""
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
        """Sequence([a], [b]) fails."""
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
        """Sequence([], []) succeeds."""
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
        """Sequence([a, b, c], [a, b]) fails."""
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
