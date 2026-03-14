"""Tests for Step 8 — built-ins and standard library (clausal.logic.builtins).

Tests use the simple query API (clausal.logic.solve) to drive predicates and
collect solutions.  Each test follows the pattern:

    module = Module("test")
    trail = Trail()
    results = [deref(var) for _ in solve(goal, module, trail)]
"""

from __future__ import annotations

import dataclasses
import pytest

from clausal.logic.database import Clause, Database, Module
from clausal.logic.solve import solve, call, query, once
from clausal.logic.variables import Var, Trail, deref, is_var, unify
from clausal.terms import Compound, KWTerm, Unify as Is, And, Call, LoadName, Not, In


# ── Helpers ────────────────────────────────────────────────────────────────────


def fresh_module(name: str = "test") -> Module:
    return Module(name)


def solutions(goal, mod=None, *, limit=50):
    """Return a list of trail snapshots for each solution."""
    if mod is None:
        mod = fresh_module()
    t = Trail()
    return list(solve(goal, mod, t))


def sol_var(goal, var, *, limit=50, mod=None):
    """Return the deref'd value of var for each solution of goal."""
    if mod is None:
        mod = fresh_module()
    t = Trail()
    return [deref(var) for _ in solve(goal, mod, t)]


# ── KWTerm tests ───────────────────────────────────────────────────────────────


class TestKWTerm:
    def test_construction_and_access(self):
        t = KWTerm("point", x=1, y=2)
        assert t.functor == "point"
        assert t.x == 1
        assert t.y == 2

    def test_equality_order_independent(self):
        assert KWTerm("r", a=1, b=2) == KWTerm("r", b=2, a=1)

    def test_equality_different_functor(self):
        assert KWTerm("r", a=1) != KWTerm("s", a=1)

    def test_equality_different_fields(self):
        assert KWTerm("r", a=1) != KWTerm("r", a=2)

    def test_len(self):
        assert len(KWTerm("r", a=1, b=2)) == 2

    def test_keys_values_items(self):
        t = KWTerm("r", a=1, b=2)
        assert list(t.keys()) == ["a", "b"]
        assert list(t.values()) == [1, 2]
        assert list(t.items()) == [("a", 1), ("b", 2)]

    def test_with_overrides(self):
        t = KWTerm("r", a=1, b=2)
        t2 = t.with_overrides(b=99)
        assert t2.b == 99
        assert t2.a == 1

    def test_with_overrides_unknown_key(self):
        t = KWTerm("r", a=1)
        with pytest.raises(KeyError):
            t.with_overrides(z=9)

    def test_with_extensions(self):
        t = KWTerm("r", a=1)
        t2 = t.with_extensions(b=2)
        assert list(t2.keys()) == ["a", "b"]

    def test_with_extensions_existing_key(self):
        t = KWTerm("r", a=1)
        with pytest.raises(KeyError):
            t.with_extensions(a=99)

    def test_repr(self):
        r = repr(KWTerm("r", x=1))
        assert "KWTerm" in r and "x=1" in r

    def test_hash_consistent(self):
        t1 = KWTerm("r", a=1, b=2)
        t2 = KWTerm("r", b=2, a=1)
        assert hash(t1) == hash(t2)

    def test_missing_attr(self):
        t = KWTerm("r", a=1)
        with pytest.raises(AttributeError):
            _ = t.z


# ── functor/3 ─────────────────────────────────────────────────────────────────


class TestFunctor:
    def test_decompose_compound(self):
        mod = fresh_module()
        f, a = Var(), Var()
        goal = Call(func=LoadName(name="Functor"), args=[Compound("foo", (1, 2)), f, a], kwargs=[])
        results = sol_var(goal, f, mod=mod)
        assert results == ["foo"]
        results_a = sol_var(goal, a, mod=mod)
        assert results_a == [2]

    def test_decompose_atom(self):
        mod = fresh_module()
        f, a = Var(), Var()
        goal = Call(func=LoadName(name="Functor"), args=["hello", f, a], kwargs=[])
        assert sol_var(goal, f, mod=mod) == ["hello"]
        assert sol_var(goal, a, mod=mod) == [0]

    def test_decompose_integer(self):
        mod = fresh_module()
        f, a = Var(), Var()
        goal = Call(func=LoadName(name="Functor"), args=[42, f, a], kwargs=[])
        assert sol_var(goal, f, mod=mod) == ["42"]
        assert sol_var(goal, a, mod=mod) == [0]

    def test_compose_compound(self):
        mod = fresh_module()
        t = Var()
        goal = Call(func=LoadName(name="Functor"), args=[t, "bar", 2], kwargs=[])
        results = sol_var(goal, t, mod=mod)
        assert len(results) == 1
        r = results[0]
        assert isinstance(r, Compound)
        assert r.functor == "bar"
        assert len(r.args) == 2

    def test_compose_atom(self):
        mod = fresh_module()
        t = Var()
        goal = Call(func=LoadName(name="Functor"), args=[t, "hello", 0], kwargs=[])
        assert sol_var(goal, t, mod=mod) == ["hello"]

    def test_fails_both_unbound(self):
        mod = fresh_module()
        t, f, a = Var(), Var(), Var()
        goal = Call(func=LoadName(name="Functor"), args=[t, f, a], kwargs=[])
        assert sol_var(goal, t, mod=mod) == []

    def test_decompose_dataclass(self):
        mod = fresh_module()
        db = Database()

        @dataclasses.dataclass
        class point:
            x: object
            y: object

        f, a = Var(), Var()
        goal = Call(func=LoadName(name="Functor"), args=[point(x=1, y=2), f, a], kwargs=[])
        assert sol_var(goal, f, mod=mod) == ["point"]
        assert sol_var(goal, a, mod=mod) == [2]


# ── arg/3 ─────────────────────────────────────────────────────────────────────


class TestArg:
    def test_first_arg(self):
        mod = fresh_module()
        a = Var()
        goal = Call(func=LoadName(name="Arg"), args=[1, Compound("f", (10, 20)), a], kwargs=[])
        assert sol_var(goal, a, mod=mod) == [10]

    def test_second_arg(self):
        mod = fresh_module()
        a = Var()
        goal = Call(func=LoadName(name="Arg"), args=[2, Compound("f", (10, 20)), a], kwargs=[])
        assert sol_var(goal, a, mod=mod) == [20]

    def test_out_of_range(self):
        mod = fresh_module()
        a = Var()
        goal = Call(func=LoadName(name="Arg"), args=[3, Compound("f", (10, 20)), a], kwargs=[])
        assert sol_var(goal, a, mod=mod) == []

    def test_list_arg(self):
        mod = fresh_module()
        a = Var()
        goal = Call(func=LoadName(name="Arg"), args=[2, [10, 20, 30], a], kwargs=[])
        assert sol_var(goal, a, mod=mod) == [20]


# ── univ/2 ────────────────────────────────────────────────────────────────────


class TestUniv:
    def test_decompose(self):
        mod = fresh_module()
        lst = Var()
        goal = Call(func=LoadName(name="Unpack"), args=[Compound("f", (1, 2)), lst], kwargs=[])
        results = sol_var(goal, lst, mod=mod)
        assert results == [["f", 1, 2]]

    def test_construct(self):
        mod = fresh_module()
        t = Var()
        goal = Call(func=LoadName(name="Unpack"), args=[t, ["g", 3, 4]], kwargs=[])
        results = sol_var(goal, t, mod=mod)
        assert len(results) == 1
        r = results[0]
        assert isinstance(r, Compound)
        assert r.functor == "g"
        assert r.args == (3, 4)

    def test_decompose_atom(self):
        mod = fresh_module()
        lst = Var()
        goal = Call(func=LoadName(name="Unpack"), args=["hello", lst], kwargs=[])
        assert sol_var(goal, lst, mod=mod) == [["hello"]]


# ── Type check predicates ──────────────────────────────────────────────────────


class TestTypeChecks:
    def test_var_unbound(self):
        mod = fresh_module()
        v = Var()
        goal = Call(func=LoadName(name="IsVar"), args=[v], kwargs=[])
        assert len(solutions(goal, mod)) == 1

    def test_var_bound(self):
        mod = fresh_module()
        goal = Call(func=LoadName(name="IsVar"), args=[42], kwargs=[])
        assert solutions(goal, mod) == []

    def test_nonvar(self):
        mod = fresh_module()
        goal = Call(func=LoadName(name="IsBound"), args=[42], kwargs=[])
        assert len(solutions(goal, mod)) == 1

    def test_atom_string(self):
        mod = fresh_module()
        goal = Call(func=LoadName(name="IsStr"), args=["hello"], kwargs=[])
        assert len(solutions(goal, mod)) == 1

    def test_atom_int_fails(self):
        mod = fresh_module()
        goal = Call(func=LoadName(name="IsStr"), args=[42], kwargs=[])
        assert solutions(goal, mod) == []

    def test_number_int(self):
        mod = fresh_module()
        goal = Call(func=LoadName(name="IsNumber"), args=[42], kwargs=[])
        assert len(solutions(goal, mod)) == 1

    def test_number_float(self):
        mod = fresh_module()
        goal = Call(func=LoadName(name="IsNumber"), args=[3.14], kwargs=[])
        assert len(solutions(goal, mod)) == 1

    def test_integer(self):
        mod = fresh_module()
        g1 = Call(func=LoadName(name="IsInt"), args=[42], kwargs=[])
        g2 = Call(func=LoadName(name="IsInt"), args=[3.14], kwargs=[])
        assert len(solutions(g1, mod)) == 1
        assert solutions(g2, mod) == []

    def test_string(self):
        mod = fresh_module()
        goal = Call(func=LoadName(name="IsStr"), args=["hi"], kwargs=[])
        assert len(solutions(goal, mod)) == 1

    def test_compound_compound(self):
        mod = fresh_module()
        goal = Call(func=LoadName(name="IsCompound"), args=[Compound("f", (1,))], kwargs=[])
        assert len(solutions(goal, mod)) == 1

    def test_compound_atom_fails(self):
        mod = fresh_module()
        goal = Call(func=LoadName(name="IsCompound"), args=["hello"], kwargs=[])
        assert solutions(goal, mod) == []

    def test_is_list(self):
        mod = fresh_module()
        g1 = Call(func=LoadName(name="IsList"), args=[[1, 2, 3]], kwargs=[])
        g2 = Call(func=LoadName(name="IsList"), args=[42], kwargs=[])
        assert len(solutions(g1, mod)) == 1
        assert solutions(g2, mod) == []

    def test_ground(self):
        mod = fresh_module()
        g1 = Call(func=LoadName(name="IsGround"), args=[42], kwargs=[])
        g2 = Call(func=LoadName(name="IsGround"), args=[Var()], kwargs=[])
        assert len(solutions(g1, mod)) == 1
        assert solutions(g2, mod) == []


# ── Arithmetic predicates ──────────────────────────────────────────────────────


class TestArithmetic:
    def test_between_generate(self):
        mod = fresh_module()
        x = Var()
        goal = Call(func=LoadName(name="Between"), args=[1, 3, x], kwargs=[])
        assert sol_var(goal, x, mod=mod) == [1, 2, 3]

    def test_between_check(self):
        mod = fresh_module()
        g1 = Call(func=LoadName(name="Between"), args=[1, 5, 3], kwargs=[])
        g2 = Call(func=LoadName(name="Between"), args=[1, 5, 6], kwargs=[])
        assert len(solutions(g1, mod)) == 1
        assert solutions(g2, mod) == []

    def test_succ_forward(self):
        mod = fresh_module()
        y = Var()
        goal = Call(func=LoadName(name="Succ"), args=[4, y], kwargs=[])
        assert sol_var(goal, y, mod=mod) == [5]

    def test_succ_backward(self):
        mod = fresh_module()
        x = Var()
        goal = Call(func=LoadName(name="Succ"), args=[x, 5], kwargs=[])
        assert sol_var(goal, x, mod=mod) == [4]

    def test_plus_forward(self):
        mod = fresh_module()
        z = Var()
        goal = Call(func=LoadName(name="Plus"), args=[3, 4, z], kwargs=[])
        assert sol_var(goal, z, mod=mod) == [7]

    def test_plus_backward_x(self):
        mod = fresh_module()
        x = Var()
        goal = Call(func=LoadName(name="Plus"), args=[x, 4, 7], kwargs=[])
        assert sol_var(goal, x, mod=mod) == [3]

    def test_abs_(self):
        mod = fresh_module()
        y = Var()
        goal = Call(func=LoadName(name="Abs"), args=[-5, y], kwargs=[])
        assert sol_var(goal, y, mod=mod) == [5]

    def test_max_(self):
        mod = fresh_module()
        z = Var()
        goal = Call(func=LoadName(name="Max"), args=[3, 7, z], kwargs=[])
        assert sol_var(goal, z, mod=mod) == [7]

    def test_min_(self):
        mod = fresh_module()
        z = Var()
        goal = Call(func=LoadName(name="Min"), args=[3, 7, z], kwargs=[])
        assert sol_var(goal, z, mod=mod) == [3]

    # ── Sign/2 ──

    def test_sign_positive(self):
        mod = fresh_module()
        s = Var()
        goal = Call(func=LoadName(name="Sign"), args=[42, s], kwargs=[])
        assert sol_var(goal, s, mod=mod) == [1]

    def test_sign_negative(self):
        mod = fresh_module()
        s = Var()
        goal = Call(func=LoadName(name="Sign"), args=[-7, s], kwargs=[])
        assert sol_var(goal, s, mod=mod) == [-1]

    def test_sign_zero(self):
        mod = fresh_module()
        s = Var()
        goal = Call(func=LoadName(name="Sign"), args=[0, s], kwargs=[])
        assert sol_var(goal, s, mod=mod) == [0]

    def test_sign_float(self):
        mod = fresh_module()
        s = Var()
        goal = Call(func=LoadName(name="Sign"), args=[-3.14, s], kwargs=[])
        assert sol_var(goal, s, mod=mod) == [-1]

    def test_sign_unbound_fails(self):
        mod = fresh_module()
        x, s = Var(), Var()
        goal = Call(func=LoadName(name="Sign"), args=[x, s], kwargs=[])
        assert solutions(goal, mod) == []

    def test_sign_check_mode(self):
        mod = fresh_module()
        goal = Call(func=LoadName(name="Sign"), args=[5, 1], kwargs=[])
        assert len(solutions(goal, mod)) == 1
        goal2 = Call(func=LoadName(name="Sign"), args=[5, -1], kwargs=[])
        assert solutions(goal2, mod) == []

    # ── Gcd/3 ──

    def test_gcd_basic(self):
        mod = fresh_module()
        g = Var()
        goal = Call(func=LoadName(name="Gcd"), args=[12, 8, g], kwargs=[])
        assert sol_var(goal, g, mod=mod) == [4]

    def test_gcd_coprime(self):
        mod = fresh_module()
        g = Var()
        goal = Call(func=LoadName(name="Gcd"), args=[7, 13, g], kwargs=[])
        assert sol_var(goal, g, mod=mod) == [1]

    def test_gcd_with_zero(self):
        mod = fresh_module()
        g = Var()
        goal = Call(func=LoadName(name="Gcd"), args=[0, 5, g], kwargs=[])
        assert sol_var(goal, g, mod=mod) == [5]

    def test_gcd_negative(self):
        mod = fresh_module()
        g = Var()
        goal = Call(func=LoadName(name="Gcd"), args=[-12, 8, g], kwargs=[])
        assert sol_var(goal, g, mod=mod) == [4]

    def test_gcd_unbound_fails(self):
        mod = fresh_module()
        x, g = Var(), Var()
        goal = Call(func=LoadName(name="Gcd"), args=[x, 8, g], kwargs=[])
        assert solutions(goal, mod) == []

    # ── DivMod/4 ──

    def test_divmod_basic(self):
        mod = fresh_module()
        q, r = Var(), Var()
        goal = Call(func=LoadName(name="DivMod"), args=[17, 5, q, r], kwargs=[])
        t = Trail()
        results = []
        for _ in solve(goal, mod, t):
            results.append((deref(q), deref(r)))
        assert results == [(3, 2)]

    def test_divmod_exact(self):
        mod = fresh_module()
        q, r = Var(), Var()
        goal = Call(func=LoadName(name="DivMod"), args=[10, 5, q, r], kwargs=[])
        t = Trail()
        results = []
        for _ in solve(goal, mod, t):
            results.append((deref(q), deref(r)))
        assert results == [(2, 0)]

    def test_divmod_by_zero_fails(self):
        mod = fresh_module()
        q, r = Var(), Var()
        goal = Call(func=LoadName(name="DivMod"), args=[10, 0, q, r], kwargs=[])
        assert solutions(goal, mod) == []

    def test_divmod_negative(self):
        mod = fresh_module()
        q, r = Var(), Var()
        goal = Call(func=LoadName(name="DivMod"), args=[-7, 2, q, r], kwargs=[])
        t = Trail()
        results = []
        for _ in solve(goal, mod, t):
            results.append((deref(q), deref(r)))
        # Python divmod: -7 // 2 = -4, -7 % 2 = 1
        assert results == [(-4, 1)]

    def test_divmod_unbound_fails(self):
        mod = fresh_module()
        x, q, r = Var(), Var(), Var()
        goal = Call(func=LoadName(name="DivMod"), args=[x, 5, q, r], kwargs=[])
        assert solutions(goal, mod) == []

    def test_divmod_check_mode(self):
        mod = fresh_module()
        goal = Call(func=LoadName(name="DivMod"), args=[17, 5, 3, 2], kwargs=[])
        assert len(solutions(goal, mod)) == 1
        goal2 = Call(func=LoadName(name="DivMod"), args=[17, 5, 3, 99], kwargs=[])
        assert solutions(goal2, mod) == []


# ── List predicates ────────────────────────────────────────────────────────────


class TestListPredicates:
    def test_member_check(self):
        mod = fresh_module()
        g1 = Call(func=LoadName(name="In"), args=[2, [1, 2, 3]], kwargs=[])
        g2 = Call(func=LoadName(name="In"), args=[5, [1, 2, 3]], kwargs=[])
        assert len(solutions(g1, mod)) == 1
        assert solutions(g2, mod) == []

    def test_member_enumerate(self):
        mod = fresh_module()
        x = Var()
        goal = Call(func=LoadName(name="In"), args=[x, [10, 20, 30]], kwargs=[])
        assert sol_var(goal, x, mod=mod) == [10, 20, 30]

    def test_memberchk_first_only(self):
        mod = fresh_module()
        x = Var()
        goal = Call(func=LoadName(name="InCheck"), args=[x, [1, 1, 2]], kwargs=[])
        # memberchk commits to first match
        assert sol_var(goal, x, mod=mod) == [1]

    def test_append_concat(self):
        mod = fresh_module()
        z = Var()
        goal = Call(func=LoadName(name="Append"), args=[[1, 2], [3, 4], z], kwargs=[])
        assert sol_var(goal, z, mod=mod) == [[1, 2, 3, 4]]

    def test_append_split(self):
        mod = fresh_module()
        l1, l2 = Var(), Var()
        goal = Call(func=LoadName(name="Append"), args=[l1, l2, [1, 2, 3]], kwargs=[])
        t = Trail()
        pairs = []
        for _ in solve(goal, mod, t):
            pairs.append((list(deref(l1)), list(deref(l2))))
        assert pairs == [
            ([], [1, 2, 3]),
            ([1], [2, 3]),
            ([1, 2], [3]),
            ([1, 2, 3], []),
        ]

    def test_length_known(self):
        mod = fresh_module()
        n = Var()
        goal = Call(func=LoadName(name="Length"), args=[[1, 2, 3], n], kwargs=[])
        assert sol_var(goal, n, mod=mod) == [3]

    def test_length_generate(self):
        mod = fresh_module()
        lst = Var()
        goal = Call(func=LoadName(name="Length"), args=[lst, 3], kwargs=[])
        results = sol_var(goal, lst, mod=mod)
        assert len(results) == 1
        r = results[0]
        assert isinstance(r, list) and len(r) == 3
        assert all(is_var(x) for x in r)

    def test_last(self):
        mod = fresh_module()
        e = Var()
        goal = Call(func=LoadName(name="Last"), args=[[1, 2, 3], e], kwargs=[])
        assert sol_var(goal, e, mod=mod) == [3]

    def test_reverse(self):
        mod = fresh_module()
        r = Var()
        goal = Call(func=LoadName(name="Reverse"), args=[[1, 2, 3], r], kwargs=[])
        assert sol_var(goal, r, mod=mod) == [[3, 2, 1]]

    def test_nth0(self):
        mod = fresh_module()
        e = Var()
        goal = Call(func=LoadName(name="GetItem"), args=[1, [10, 20, 30], e], kwargs=[])
        assert sol_var(goal, e, mod=mod) == [20]

    def test_getitem_1based_equivalent(self):
        mod = fresh_module()
        e = Var()
        # GetItem is 0-based; index 1 = 2nd element (was nth1 index 2)
        goal = Call(func=LoadName(name="GetItem"), args=[1, [10, 20, 30], e], kwargs=[])
        assert sol_var(goal, e, mod=mod) == [20]

    def test_nth0_enumerate(self):
        mod = fresh_module()
        n, e = Var(), Var()
        goal = Call(func=LoadName(name="GetItem"), args=[n, [10, 20], e], kwargs=[])
        t = Trail()
        pairs = []
        for _ in solve(goal, mod, t):
            pairs.append((deref(n), deref(e)))
        assert pairs == [(0, 10), (1, 20)]

    def test_flatten(self):
        mod = fresh_module()
        f = Var()
        goal = Call(func=LoadName(name="Flatten"), args=[[[1, 2], [3, [4, 5]]], f], kwargs=[])
        assert sol_var(goal, f, mod=mod) == [[1, 2, 3, 4, 5]]

    def test_msort(self):
        mod = fresh_module()
        s = Var()
        goal = Call(func=LoadName(name="MergeSort"), args=[[3, 1, 2, 1], s], kwargs=[])
        assert sol_var(goal, s, mod=mod) == [[1, 1, 2, 3]]

    def test_sort_dedup(self):
        mod = fresh_module()
        s = Var()
        goal = Call(func=LoadName(name="Sort"), args=[[3, 1, 2, 1], s], kwargs=[])
        assert sol_var(goal, s, mod=mod) == [[1, 2, 3]]

    def test_permutation(self):
        mod = fresh_module()
        p = Var()
        goal = Call(func=LoadName(name="Permutation"), args=[[1, 2, 3], p], kwargs=[])
        results = sol_var(goal, p, mod=mod)
        assert len(results) == 6
        assert sorted(results) == sorted([
            [1, 2, 3], [1, 3, 2], [2, 1, 3], [2, 3, 1], [3, 1, 2], [3, 2, 1]
        ])

    def test_select(self):
        mod = fresh_module()
        e, r = Var(), Var()
        goal = Call(func=LoadName(name="Select"), args=[e, [1, 2, 3], r], kwargs=[])
        t = Trail()
        pairs = []
        for _ in solve(goal, mod, t):
            pairs.append((deref(e), list(deref(r))))
        assert pairs == [(1, [2, 3]), (2, [1, 3]), (3, [1, 2])]

    def test_subtract(self):
        mod = fresh_module()
        d = Var()
        goal = Call(func=LoadName(name="Subtract"), args=[[1, 2, 3, 4], [2, 4], d], kwargs=[])
        assert sol_var(goal, d, mod=mod) == [[1, 3]]

    def test_intersection(self):
        mod = fresh_module()
        i = Var()
        goal = Call(func=LoadName(name="Intersection"), args=[[1, 2, 3], [2, 3, 4], i], kwargs=[])
        assert sol_var(goal, i, mod=mod) == [[2, 3]]

    def test_union(self):
        mod = fresh_module()
        u = Var()
        goal = Call(func=LoadName(name="Union"), args=[[1, 2], [2, 3], u], kwargs=[])
        assert sol_var(goal, u, mod=mod) == [[1, 2, 3]]

    def test_sum_list(self):
        mod = fresh_module()
        s = Var()
        goal = Call(func=LoadName(name="SumList"), args=[[1, 2, 3, 4], s], kwargs=[])
        assert sol_var(goal, s, mod=mod) == [10]

    def test_max_list(self):
        mod = fresh_module()
        m = Var()
        goal = Call(func=LoadName(name="MaxList"), args=[[3, 1, 4, 1, 5, 9], m], kwargs=[])
        assert sol_var(goal, m, mod=mod) == [9]

    def test_min_list(self):
        mod = fresh_module()
        m = Var()
        goal = Call(func=LoadName(name="MinList"), args=[[3, 1, 4, 1, 5, 9], m], kwargs=[])
        assert sol_var(goal, m, mod=mod) == [1]

    def test_list_to_set(self):
        mod = fresh_module()
        s = Var()
        goal = Call(func=LoadName(name="ToSet"), args=[[1, 2, 1, 3, 2], s], kwargs=[])
        assert sol_var(goal, s, mod=mod) == [[1, 2, 3]]


# ── assertz/retract ───────────────────────────────────────────────────────────


class TestAssertRetract:
    def test_assertz_fact(self):
        from clausal.logic.compiler import compile_predicate

        mod = fresh_module()
        # Pre-create an empty predicate so table_for can find it later
        # (assertz will compile it after asserting)
        x = Var()
        fact = Compound("dyn_fact", (42,))
        goal_assert = Call(func=LoadName(name="Assert"), args=[fact], kwargs=[])
        # Execute assertz
        list(solve(goal_assert, mod))

        # Now query it
        q_var = Var()
        q_goal = Call(func=LoadName(name="dyn_fact"), args=[q_var], kwargs=[])
        t = Trail()
        results = [deref(q_var) for _ in solve(q_goal, mod, t)]
        assert results == [42]

    def test_assertz_multiple(self):
        mod = fresh_module()
        for v in [1, 2, 3]:
            fact = Compound("dyn_num", (v,))
            goal = Call(func=LoadName(name="Assert"), args=[fact], kwargs=[])
            list(solve(goal, mod))

        q = Var()
        q_goal = Call(func=LoadName(name="dyn_num"), args=[q], kwargs=[])
        t = Trail()
        results = [deref(q) for _ in solve(q_goal, mod, t)]
        assert results == [1, 2, 3]

    def test_retract(self):
        mod = fresh_module()
        for v in [1, 2, 3]:
            fact = Compound("dyn_r", (v,))
            list(solve(Call(func=LoadName(name="Assert"), args=[fact], kwargs=[]), mod))

        # Retract the middle element
        retract_goal = Call(
            func=LoadName(name="Retract"), args=[Compound("dyn_r", (2,))], kwargs=[]
        )
        list(solve(retract_goal, mod))

        q = Var()
        q_goal = Call(func=LoadName(name="dyn_r"), args=[q], kwargs=[])
        t = Trail()
        results = [deref(q) for _ in solve(q_goal, mod, t)]
        assert results == [1, 3]


# ── WK-5: vary, extend, unbound_keys, signature ───────────────────────────────


class TestWK5:
    def test_vary_dataclass(self):
        @dataclasses.dataclass
        class point:
            x: object
            y: object

        mod = fresh_module()
        p = point(x=1, y=2)
        new_p = Var()
        goal = Call(
            func=LoadName(name="Vary"),
            args=[{"y": 99}, p, new_p],
            kwargs=[],
        )
        results = sol_var(goal, new_p, mod=mod)
        assert len(results) == 1
        assert results[0] == point(x=1, y=99)

    def test_vary_kwterm(self):
        mod = fresh_module()
        t = KWTerm("r", a=1, b=2)
        new_t = Var()
        goal = Call(
            func=LoadName(name="Vary"), args=[{"b": 99}, t, new_t], kwargs=[]
        )
        results = sol_var(goal, new_t, mod=mod)
        assert len(results) == 1
        assert results[0] == KWTerm("r", a=1, b=99)

    def test_vary_unknown_key(self):
        mod = fresh_module()
        t = KWTerm("r", a=1)
        new_t = Var()
        goal = Call(
            func=LoadName(name="Vary"), args=[{"z": 9}, t, new_t], kwargs=[]
        )
        assert sol_var(goal, new_t, mod=mod) == []

    def test_extend_kwterm(self):
        mod = fresh_module()
        t = KWTerm("r", a=1)
        new_t = Var()
        goal = Call(
            func=LoadName(name="Extend"), args=[{"b": 2}, t, new_t], kwargs=[]
        )
        results = sol_var(goal, new_t, mod=mod)
        assert len(results) == 1
        assert results[0] == KWTerm("r", a=1, b=2)

    def test_unbound_keys_dataclass(self):
        @dataclasses.dataclass
        class pt:
            x: object
            y: object

        v = Var()
        t = pt(x=1, y=v)  # y is unbound
        mod = fresh_module()
        keys = Var()
        goal = Call(func=LoadName(name="UnboundKeys"), args=[t, keys], kwargs=[])
        results = sol_var(goal, keys, mod=mod)
        assert results == [["y"]]

    def test_unbound_keys_kwterm(self):
        v = Var()
        t = KWTerm("r", a=1, b=v)
        mod = fresh_module()
        keys = Var()
        goal = Call(func=LoadName(name="UnboundKeys"), args=[t, keys], kwargs=[])
        results = sol_var(goal, keys, mod=mod)
        assert results == [["b"]]

    def test_signature(self):
        from clausal.logic.database import Clause

        mod = fresh_module()
        # Register a predicate with a signature
        mod.db.register_signature("mypred", 2, ("arg0", "arg1"))
        names = Var()
        goal = Call(
            func=LoadName(name="Signature"), args=["mypred", 2, names], kwargs=[]
        )
        results = sol_var(goal, names, mod=mod)
        assert results == [["arg0", "arg1"]]

    def test_signature_unknown(self):
        mod = fresh_module()
        names = Var()
        goal = Call(
            func=LoadName(name="Signature"), args=["unknown_pred", 3, names], kwargs=[]
        )
        assert sol_var(goal, names, mod=mod) == []


# ── Pair helpers ──────────────────────────────────────────────────────────────


class TestPairHelpers:
    def test_pairs_keys_values_decompose(self):
        mod = fresh_module()
        k, v = Var(), Var()
        goal = Call(
            func=LoadName(name="Unzip"),
            args=[[[1, "a"], [2, "b"]], k, v],
            kwargs=[],
        )
        assert sol_var(goal, k, mod=mod) == [[1, 2]]
        assert sol_var(goal, v, mod=mod) == [["a", "b"]]

    def test_pairs_keys_values_compose(self):
        mod = fresh_module()
        p = Var()
        goal = Call(
            func=LoadName(name="Unzip"),
            args=[p, [1, 2], ["a", "b"]],
            kwargs=[],
        )
        assert sol_var(goal, p, mod=mod) == [[[1, "a"], [2, "b"]]]

    def test_pairs_keys(self):
        mod = fresh_module()
        k = Var()
        goal = Call(
            func=LoadName(name="PairKeys"),
            args=[[[1, "a"], [2, "b"]], k],
            kwargs=[],
        )
        assert sol_var(goal, k, mod=mod) == [[1, 2]]

    def test_pairs_values(self):
        mod = fresh_module()
        v = Var()
        goal = Call(
            func=LoadName(name="PairValues"),
            args=[[[1, "a"], [2, "b"]], v],
            kwargs=[],
        )
        assert sol_var(goal, v, mod=mod) == [["a", "b"]]


# ── Builtins accessible from compiled predicate bodies ────────────────────────


class TestBuiltinsInCompiledPredicates:
    """Builtins should be accessible via _db.table_for from compiled predicates."""

    def test_between_in_compiled_body(self):
        """A compiled predicate that calls between/3 in its body."""
        from clausal.logic.compiler import compile_predicate_trampoline
        from clausal.logic.trampoline import StepGenerator, solutions

        mod = fresh_module()
        db = mod.db

        # range_check(N) :- between(1, 10, N).
        n = Var()
        db.assertz(Clause(
            head=Compound("range_check", (n,)),
            body=[Call(func=LoadName(name="Between"), args=[1, 5, n], kwargs=[])],
        ))
        compile_predicate_trampoline("range_check", 1, db.clauses_for("range_check", 1), db)

        out = Var()
        t = Trail()
        fn = db.get_dispatch("range_check", 1)
        results = solutions(StepGenerator(fn, None, out, t), lambda: deref(out))
        assert results == [1, 2, 3, 4, 5]

    def test_member_in_compiled_body(self):
        """A compiled predicate that calls member/2 to enumerate."""
        from clausal.logic.compiler import compile_predicate_trampoline
        from clausal.logic.trampoline import StepGenerator, solutions

        mod = fresh_module()
        db = mod.db

        # pick(X) :- member(X, [a, b, c]).
        x = Var()
        db.assertz(Clause(
            head=Compound("pick", (x,)),
            body=[Call(func=LoadName(name="In"), args=[x, ["a", "b", "c"]], kwargs=[])],
        ))
        compile_predicate_trampoline("pick", 1, db.clauses_for("pick", 1), db)

        out = Var()
        t = Trail()
        fn = db.get_dispatch("pick", 1)
        results = solutions(StepGenerator(fn, None, out, t), lambda: deref(out))
        assert results == ["a", "b", "c"]
