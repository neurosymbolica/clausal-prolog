"""Tests for .clausal module files — Python-level term-inspection cases.

Behavior tests for predicates in meta.clausal / higher_order.clausal /
lambdas.clausal / exceptions.clausal have been migrated to Test clauses
inside those .clausal modules. What remains here is term-inspection
behavior that requires Python-level Compound/Var construction (the
term_inspection.clausal module's predicates take Compound/Var arguments
that can't be expressed at clausal surface).
"""

from __future__ import annotations

import os

from clausal.logic.atoms import mint
from clausal.logic.database import Module
from clausal.logic.solve import call, _deref_walk
from clausal.logic.variables import Var, deref
from clausal.import_hook import _load_module


# ── Helpers ────────────────────────────────────────────────────────────────────


def _load_clausal_module(filename: str) -> Module:
    """Load a .clausal file from tests/clausal_modules/ and return its LogicModule."""
    path = os.path.join(os.path.dirname(__file__), "clausal_modules", filename)
    name = f"_test_cm_{filename.replace('.', '_')}"
    mod = _load_module(name, path)
    return mod.__dict__["$module"]


def _call_collect(functor: str, *args, mod: Module) -> list:
    """Call functor with args, collect deref'd value of last Var arg."""
    var = args[-1]
    return [_deref_walk(var) for _ in call(functor, *args, module=mod)]


def _call_succeeds(functor: str, *args, mod: Module) -> int:
    """Call functor with args, return number of solutions."""
    return len(list(call(functor, *args, module=mod)))


# ══════════════════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════════════════
# Term inspection builtins (term_inspection.clausal) — V2-13
# ══════════════════════════════════════════════════════════════════════════════


class TestTermInspectionCopyFresh:
    def setup_method(self):
        self.mod = _load_clausal_module("term_inspection.clausal")

    def test_copy_ground_term(self):
        # nv
        from clausal.terms import Compound
        term = Compound("foo", (1, 2))
        r = Var()
        result = _call_collect("copy_fresh", term, r, mod=self.mod)
        assert len(result) == 1
        assert result[0] == Compound("foo", (1, 2))

    def test_copy_returns_fresh_copy(self):
        # nv
        from clausal.terms import Compound
        from clausal.logic.variables import is_var
        x = Var()
        term = Compound("f", (x,))
        r = Var()
        result = _call_collect("copy_fresh", term, r, mod=self.mod)
        assert len(result) == 1
        c = result[0]
        assert isinstance(c, Compound)
        assert is_var(c.args[0])
        assert c.args[0] is not x

    def test_copy_atom(self):
        # nv
        r = Var()
        result = _call_collect("copy_fresh", "hello", r, mod=self.mod)
        assert result == ["hello"]

    def test_copy_integer(self):
        # nv
        r = Var()
        result = _call_collect("copy_fresh", 42, r, mod=self.mod)
        assert result == [42]

    def test_copy_list(self):
        # nv
        r = Var()
        result = _call_collect("copy_fresh", [1, 2, 3], r, mod=self.mod)
        assert result == [[1, 2, 3]]


class TestTermInspectionHasNoVars:
    def setup_method(self):
        self.mod = _load_clausal_module("term_inspection.clausal")

    def test_ground_term_no_vars(self):
        # nv
        from clausal.terms import Compound
        assert _call_succeeds("has_no_vars", Compound("f", (1, 2)), mod=self.mod) == 1

    def test_ground_atom(self):
        # nv
        assert _call_succeeds("has_no_vars", "hello", mod=self.mod) == 1

    def test_term_with_var_fails(self):
        # nv
        from clausal.terms import Compound
        term = Compound("f", (Var(),))
        assert _call_succeeds("has_no_vars", term, mod=self.mod) == 0

    def test_ground_list(self):
        # nv
        assert _call_succeeds("has_no_vars", [1, 2, 3], mod=self.mod) == 1

    def test_list_with_var_fails(self):
        # nv
        assert _call_succeeds("has_no_vars", [1, Var(), 3], mod=self.mod) == 0


class TestTermInspectionCountVars:
    def setup_method(self):
        self.mod = _load_clausal_module("term_inspection.clausal")

    def test_no_vars(self):
        # nv
        from clausal.terms import Compound
        r = Var()
        result = _call_collect("count_vars", Compound("f", (1, 2)), r, mod=self.mod)
        assert result == [0]

    def test_one_var(self):
        # nv
        from clausal.terms import Compound
        r = Var()
        result = _call_collect("count_vars", Compound("f", (Var(),)), r, mod=self.mod)
        assert result == [1]

    def test_two_vars(self):
        # nv
        from clausal.terms import Compound
        r = Var()
        result = _call_collect("count_vars", Compound("f", (Var(), Var())), r, mod=self.mod)
        assert result == [2]

    def test_repeated_var_counts_once(self):
        # nv
        from clausal.terms import Compound
        x = Var()
        r = Var()
        result = _call_collect("count_vars", Compound("f", (x, x)), r, mod=self.mod)
        assert result == [1]

    def test_list_vars(self):
        # nv
        r = Var()
        result = _call_collect("count_vars", [Var(), Var(), Var()], r, mod=self.mod)
        assert result == [3]


class TestTermInspectionNumberAndCount:
    def setup_method(self):
        self.mod = _load_clausal_module("term_inspection.clausal")

    def test_no_vars(self):
        # nv
        from clausal.terms import Compound
        r = Var()
        result = _call_collect("number_and_count", Compound("f", (1, 2)), 0, r, mod=self.mod)
        assert result == [0]

    def test_one_var(self):
        # nv
        from clausal.terms import Compound
        r = Var()
        result = _call_collect("number_and_count", Compound("f", (Var(),)), 0, r, mod=self.mod)
        assert result == [1]

    def test_start_offset(self):
        # nv
        from clausal.terms import Compound
        r = Var()
        result = _call_collect("number_and_count", Compound("f", (Var(), Var())), 5, r, mod=self.mod)
        assert result == [7]

    def test_two_vars_consecutive(self):
        # nv
        r = Var()
        result = _call_collect("number_and_count", [Var(), Var()], 0, r, mod=self.mod)
        assert result == [2]


class TestTermInspectionCopyShared:
    def setup_method(self):
        self.mod = _load_clausal_module("term_inspection.clausal")

    def test_sharing_preserved(self):
        """f(X, X) copied: the two args in copy should be the same fresh Var."""
        # nv
        from clausal.terms import Compound
        from clausal.logic.variables import is_var
        x = Var()
        term = Compound("f", (x, x))
        a, b = Var(), Var()
        shared = []
        for _ in call("copy_shared", term, a, b, module=self.mod):
            shared.append((deref(a), deref(b)))
        assert len(shared) == 1
        av, bv = shared[0]
        assert is_var(av) and is_var(bv)
        assert av is bv

    def test_sharing_independent_from_original(self):
        """Fresh vars in copy are distinct from original Var."""
        # nv
        from clausal.terms import Compound
        from clausal.logic.variables import is_var
        x = Var()
        term = Compound("f", (x, x))
        a, b = Var(), Var()
        captured = []
        for _ in call("copy_shared", term, a, b, module=self.mod):
            captured.append(deref(a))
        assert len(captured) == 1
        assert captured[0] is not x


class TestTermInspectionVarList:
    def setup_method(self):
        self.mod = _load_clausal_module("term_inspection.clausal")

    def test_empty_list(self):
        # nv
        r = Var()
        result = _call_collect("var_list", [], r, mod=self.mod)
        assert result == [[]]

    def test_list_no_vars(self):
        # nv
        r = Var()
        result = _call_collect("var_list", [1, 2, 3], r, mod=self.mod)
        assert result == [[]]

    def test_list_with_vars(self):
        # nv
        from clausal.logic.variables import is_var
        x, y = Var(), Var()
        r = Var()
        results = []
        for _ in call("var_list", [1, x, 2, y], r, module=self.mod):
            vs = _deref_walk(r)
            results.append(vs)
        assert len(results) == 1
        assert len(results[0]) == 2
        assert all(is_var(v) for v in results[0])


# ══════════════════════════════════════════════════════════════════════════════
# Exception handling (exceptions.clausal) — V2-14
# ══════════════════════════════════════════════════════════════════════════════


class TestExceptionsCatchAll:
    def setup_method(self):
        self.mod = _load_clausal_module("exceptions.clausal")

    def test_catch_integer(self):
        # nv
        r = Var()
        assert _call_collect("catch_all", 42, r, mod=self.mod) == [42]

    def test_catch_string(self):
        # nv
        r = Var()
        assert _call_collect("catch_all", "oops", r, mod=self.mod) == ["oops"]


class TestExceptionsSafeRecip:
    def setup_method(self):
        self.mod = _load_clausal_module("exceptions.clausal")

    def test_safe_recip_nonzero(self):
        # nv
        r = Var()
        assert _call_collect("safe_recip", 2, r, mod=self.mod) == [0.5]

    def test_safe_recip_zero(self):
        # nv
        r = Var()
        assert _call_collect("safe_recip", 0, r, mod=self.mod) == [0]


class TestExceptionsNested:
    def setup_method(self):
        self.mod = _load_clausal_module("exceptions.clausal")

    def test_inner_miss(self):
        # nv
        r = Var()
        assert _call_collect("inner_miss", r, mod=self.mod) == [mint("outer_problem")]

    def test_inner_hit(self):
        # nv
        r = Var()
        assert _call_collect("inner_hit", r, mod=self.mod) == [mint("inner_caught")]


class TestExceptionsDeadChildRecovery:
    """Critical regression test: after catch swallows an exception from the
    first attempt (input=0), the parent backtracks and retries with input=1.
    The second attempt must create fresh generators — no dead child reuse."""

    def setup_method(self):
        self.mod = _load_clausal_module("exceptions.clausal")

    def test_parent_backtracks(self):
        # nv
        r = Var()
        assert _call_collect("parent", r, mod=self.mod) == [10]


class TestExceptionsCatchTransparent:
    def setup_method(self):
        self.mod = _load_clausal_module("exceptions.clausal")

    def test_no_throw(self):
        # nv
        r = Var()
        assert _call_collect("catch_no_throw", r, mod=self.mod) == [mint("normal")]

    def test_multiple_solutions(self):
        # nv
        r = Var()
        assert _call_collect("catch_multiple", r, mod=self.mod) == [10, 20, 30]
