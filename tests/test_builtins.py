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
from clausal.logic.solve import solve
from clausal.logic.variables import Var, Trail, deref
from clausal.terms import Compound, KWTerm, Call, LoadName


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
        # nv
        t = KWTerm("point", x=1, y=2)
        assert t.functor == "point"
        assert t.x == 1
        assert t.y == 2

    def test_equality_order_independent(self):
        # nv
        assert KWTerm("r", a=1, b=2) == KWTerm("r", b=2, a=1)

    def test_equality_different_functor(self):
        # nv
        assert KWTerm("r", a=1) != KWTerm("s", a=1)

    def test_equality_different_fields(self):
        # nv
        assert KWTerm("r", a=1) != KWTerm("r", a=2)

    def test_len(self):
        # nv
        assert len(KWTerm("r", a=1, b=2)) == 2

    def test_keys_values_items(self):
        # nv
        t = KWTerm("r", a=1, b=2)
        assert list(t.keys()) == ["a", "b"]
        assert list(t.values()) == [1, 2]
        assert list(t.items()) == [("a", 1), ("b", 2)]

    def test_with_overrides(self):
        # nv
        t = KWTerm("r", a=1, b=2)
        t2 = t.with_overrides(b=99)
        assert t2.b == 99
        assert t2.a == 1

    def test_with_overrides_unknown_key(self):
        # nv
        t = KWTerm("r", a=1)
        with pytest.raises(KeyError):
            t.with_overrides(z=9)

    def test_with_extensions(self):
        # nv
        t = KWTerm("r", a=1)
        t2 = t.with_extensions(b=2)
        assert list(t2.keys()) == ["a", "b"]

    def test_with_extensions_existing_key(self):
        # nv
        t = KWTerm("r", a=1)
        with pytest.raises(KeyError):
            t.with_extensions(a=99)

    def test_repr(self):
        # nv
        r = repr(KWTerm("r", x=1))
        assert "KWTerm" in r and "x=1" in r

    def test_hash_consistent(self):
        # nv
        t1 = KWTerm("r", a=1, b=2)
        t2 = KWTerm("r", b=2, a=1)
        assert hash(t1) == hash(t2)

    def test_missing_attr(self):
        # nv
        t = KWTerm("r", a=1)
        with pytest.raises(AttributeError):
            _ = t.z

# ── Migration note ─────────────────────────────────────────────────────────
# TestTypeChecks / TestArithmetic / TestListPredicates / TestAssertRetract /
# TestPairHelpers have been removed — their coverage is in .clausal fixtures:
#   tests/conformity/iso_type_checking.clausal
#   tests/conformity/iso_arithmetic.clausal  (incl. Sign/Gcd/DivMod)
#   tests/conformity/iso_list_operations.clausal + builtins_lists.clausal
#   tests/conformity/iso_database.clausal + builtins_db.clausal
#   tests/fixtures/phase5_builtins.clausal  (pairs_keys_values/_keys/_values)

# ── functor/3 ─────────────────────────────────────────────────────────────────


class TestFunctor:
    def test_decompose_compound(self):
        # nv
        mod = fresh_module()
        f, a = Var(), Var()
        goal = Call(func=LoadName(name="functor"), args=[Compound("foo", (1, 2)), f, a], kwargs=[])
        results = sol_var(goal, f, mod=mod)
        assert results == ["foo"]
        results_a = sol_var(goal, a, mod=mod)
        assert results_a == [2]

    def test_decompose_atom(self):
        # nv
        mod = fresh_module()
        f, a = Var(), Var()
        goal = Call(func=LoadName(name="functor"), args=["hello", f, a], kwargs=[])
        assert sol_var(goal, f, mod=mod) == ["hello"]
        assert sol_var(goal, a, mod=mod) == [0]

    def test_decompose_integer(self):
        # nv
        mod = fresh_module()
        f, a = Var(), Var()
        goal = Call(func=LoadName(name="functor"), args=[42, f, a], kwargs=[])
        assert sol_var(goal, f, mod=mod) == ["42"]
        assert sol_var(goal, a, mod=mod) == [0]

    def test_compose_compound(self):
        # nv
        mod = fresh_module()
        t = Var()
        goal = Call(func=LoadName(name="functor"), args=[t, "bar", 2], kwargs=[])
        results = sol_var(goal, t, mod=mod)
        assert len(results) == 1
        r = results[0]
        assert isinstance(r, Compound)
        assert r.functor == "bar"
        assert len(r.args) == 2

    def test_compose_atom(self):
        # nv
        mod = fresh_module()
        t = Var()
        goal = Call(func=LoadName(name="functor"), args=[t, "hello", 0], kwargs=[])
        assert sol_var(goal, t, mod=mod) == ["hello"]

    def test_fails_both_unbound(self):
        # nv
        mod = fresh_module()
        t, f, a = Var(), Var(), Var()
        goal = Call(func=LoadName(name="functor"), args=[t, f, a], kwargs=[])
        assert sol_var(goal, t, mod=mod) == []

    def test_decompose_dataclass(self):
        # nv
        mod = fresh_module()
        db = Database()

        @dataclasses.dataclass
        class point:
            x: object
            y: object

        f, a = Var(), Var()
        goal = Call(func=LoadName(name="functor"), args=[point(x=1, y=2), f, a], kwargs=[])
        assert sol_var(goal, f, mod=mod) == ["point"]
        assert sol_var(goal, a, mod=mod) == [2]


# ── arg/3 ─────────────────────────────────────────────────────────────────────


class TestArg:
    def test_first_arg(self):
        # nv
        mod = fresh_module()
        a = Var()
        goal = Call(func=LoadName(name="arg"), args=[1, Compound("f", (10, 20)), a], kwargs=[])
        assert sol_var(goal, a, mod=mod) == [10]

    def test_second_arg(self):
        # nv
        mod = fresh_module()
        a = Var()
        goal = Call(func=LoadName(name="arg"), args=[2, Compound("f", (10, 20)), a], kwargs=[])
        assert sol_var(goal, a, mod=mod) == [20]

    def test_out_of_range(self):
        # nv
        mod = fresh_module()
        a = Var()
        goal = Call(func=LoadName(name="arg"), args=[3, Compound("f", (10, 20)), a], kwargs=[])
        assert sol_var(goal, a, mod=mod) == []

    def test_list_arg(self):
        # nv
        mod = fresh_module()
        a = Var()
        goal = Call(func=LoadName(name="arg"), args=[2, [10, 20, 30], a], kwargs=[])
        assert sol_var(goal, a, mod=mod) == [20]


# ── univ/2 ────────────────────────────────────────────────────────────────────


class TestUniv:
    def test_decompose(self):
        # nv
        mod = fresh_module()
        lst = Var()
        goal = Call(func=LoadName(name="unpack"), args=[Compound("f", (1, 2)), lst], kwargs=[])
        results = sol_var(goal, lst, mod=mod)
        assert results == [["f", 1, 2]]

    def test_construct(self):
        # nv
        mod = fresh_module()
        t = Var()
        goal = Call(func=LoadName(name="unpack"), args=[t, ["g", 3, 4]], kwargs=[])
        results = sol_var(goal, t, mod=mod)
        assert len(results) == 1
        r = results[0]
        assert isinstance(r, Compound)
        assert r.functor == "g"
        assert r.args == (3, 4)

    def test_decompose_atom(self):
        # nv
        mod = fresh_module()
        lst = Var()
        goal = Call(func=LoadName(name="unpack"), args=["hello", lst], kwargs=[])
        assert sol_var(goal, lst, mod=mod) == [["hello"]]






# ── assertz/retract ───────────────────────────────────────────────────────────

# ── WK-5: vary, extend, unbound_keys, signature ───────────────────────────────


class TestWK5:
    def test_vary_dataclass(self):
        @dataclasses.dataclass
        # nv
        class point:
            x: object
            y: object

        mod = fresh_module()
        p = point(x=1, y=2)
        new_p = Var()
        goal = Call(
            func=LoadName(name="vary"),
            args=[{"y": 99}, p, new_p],
            kwargs=[],
        )
        results = sol_var(goal, new_p, mod=mod)
        assert len(results) == 1
        assert results[0] == point(x=1, y=99)

    def test_vary_kwterm(self):
        # nv
        mod = fresh_module()
        t = KWTerm("r", a=1, b=2)
        new_t = Var()
        goal = Call(
            func=LoadName(name="vary"), args=[{"b": 99}, t, new_t], kwargs=[]
        )
        results = sol_var(goal, new_t, mod=mod)
        assert len(results) == 1
        assert results[0] == KWTerm("r", a=1, b=99)

    def test_vary_unknown_key(self):
        # nv
        mod = fresh_module()
        t = KWTerm("r", a=1)
        new_t = Var()
        goal = Call(
            func=LoadName(name="vary"), args=[{"z": 9}, t, new_t], kwargs=[]
        )
        assert sol_var(goal, new_t, mod=mod) == []

    def test_extend_kwterm(self):
        # nv
        mod = fresh_module()
        t = KWTerm("r", a=1)
        new_t = Var()
        goal = Call(
            func=LoadName(name="extend"), args=[{"b": 2}, t, new_t], kwargs=[]
        )
        results = sol_var(goal, new_t, mod=mod)
        assert len(results) == 1
        assert results[0] == KWTerm("r", a=1, b=2)

    def test_unbound_keys_dataclass(self):
        @dataclasses.dataclass
        # nv
        class pt:
            x: object
            y: object

        v = Var()
        t = pt(x=1, y=v)  # y is unbound
        mod = fresh_module()
        keys = Var()
        goal = Call(func=LoadName(name="unbound_keys"), args=[t, keys], kwargs=[])
        results = sol_var(goal, keys, mod=mod)
        assert results == [["y"]]

    def test_unbound_keys_kwterm(self):
        # nv
        v = Var()
        t = KWTerm("r", a=1, b=v)
        mod = fresh_module()
        keys = Var()
        goal = Call(func=LoadName(name="unbound_keys"), args=[t, keys], kwargs=[])
        results = sol_var(goal, keys, mod=mod)
        assert results == [["b"]]

    def test_signature(self):
        # nv
        from clausal.logic.database import Clause

        mod = fresh_module()
        # Register a predicate with a signature
        mod.db.register_signature("mypred", 2, ("arg0", "arg1"))
        names = Var()
        goal = Call(
            func=LoadName(name="signature"), args=["mypred", 2, names], kwargs=[]
        )
        results = sol_var(goal, names, mod=mod)
        assert results == [["arg0", "arg1"]]

    def test_signature_unknown(self):
        # nv
        mod = fresh_module()
        names = Var()
        goal = Call(
            func=LoadName(name="signature"), args=["unknown_pred", 3, names], kwargs=[]
        )
        assert sol_var(goal, names, mod=mod) == []



# ── Builtins accessible from compiled predicate bodies ────────────────────────


class TestBuiltinsInCompiledPredicates:
    """Builtins should be accessible via _db.table_for from compiled predicates."""

    def test_between_in_compiled_body(self):
        """A compiled predicate that calls between/3 in its body."""
        # nv
        from clausal.logic.compiler import compile_predicate_trampoline
        from clausal.logic.trampoline import StepGenerator, solutions

        mod = fresh_module()
        db = mod.db

        # range_check(N) :- between(1, 10, N).
        n = Var()
        db.assertz(Clause(
            head=Compound("range_check", (n,)),
            body=[Call(func=LoadName(name="between"), args=[1, 5, n], kwargs=[])],
        ))
        compile_predicate_trampoline("range_check", 1, db.clauses_for("range_check", 1), db)

        out = Var()
        t = Trail()
        fn = db.get_dispatch("range_check", 1)
        results = solutions(StepGenerator(fn, None, out, t), lambda: deref(out))
        assert results == [1, 2, 3, 4, 5]

    def test_member_in_compiled_body(self):
        """A compiled predicate that calls member/2 to enumerate."""
        # nv
        from clausal.logic.compiler import compile_predicate_trampoline
        from clausal.logic.trampoline import StepGenerator, solutions

        mod = fresh_module()
        db = mod.db

        # pick(X) :- member(X, [a, b, c]).
        x = Var()
        db.assertz(Clause(
            head=Compound("pick", (x,)),
            body=[Call(func=LoadName(name="in_"), args=[x, ["a", "b", "c"]], kwargs=[])],
        ))
        compile_predicate_trampoline("pick", 1, db.clauses_for("pick", 1), db)

        out = Var()
        t = Trail()
        fn = db.get_dispatch("pick", 1)
        results = solutions(StepGenerator(fn, None, out, t), lambda: deref(out))
        assert results == ["a", "b", "c"]
