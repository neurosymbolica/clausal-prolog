"""Tests for DictTerm and SetTerm compiler integration (Phase 2).

Covers:
  - C-level __unify__ protocol: DictTerm pairwise unification, SetTerm equality
  - Trail undo on failed DictTerm unification
  - NotImplemented return for type mismatch
  - Fixture integration: dict_set_patterns.clausal (13 tests)
  - Backtracking with DictTerm clauses
"""

from __future__ import annotations

import os
import pytest
from clausal.logic.variables import Var, Trail, deref, unify
from clausal.logic.solve import call, solve, _deref_walk
from clausal.import_hook import _load_module
from clausal.terms import DictTerm, SetTerm

_FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_fixture():
    return _load_module(
        "dict_set_patterns",
        os.path.join(_FIXTURE_DIR, "dict_set_patterns.clausal"),
    )


# ── C-level __unify__ protocol ───────────────────────────────────────────────

class TestCLevelUnify:
    def test_dictterm_unify_with_vars(self):
        # nv
        t = Trail()
        x, y = Var(), Var()
        d1 = DictTerm({"a": x, "b": 2})
        d2 = DictTerm({"a": 42, "b": y})
        assert unify(d1, d2, t)
        assert deref(x) == 42
        assert deref(y) == 2

    def test_dictterm_unify_fails_different_keys(self):
        # nv
        t = Trail()
        assert not unify(DictTerm({"a": 1}), DictTerm({"b": 1}), t)

    def test_dictterm_unify_fails_value_mismatch(self):
        # nv
        t = Trail()
        assert not unify(DictTerm({"a": 1}), DictTerm({"a": 2}), t)

    def test_dictterm_unify_trail_undo(self):
        """On failure, __unify__ undoes partial bindings."""
        # nv
        t = Trail()
        x = Var()
        d1 = DictTerm({"a": x, "b": 1})
        d2 = DictTerm({"a": 42, "b": 99})  # b mismatch
        assert not unify(d1, d2, t)
        assert not isinstance(deref(x), int)

    def test_setterm_unify_same(self):
        # nv
        t = Trail()
        assert unify(SetTerm([1, 2, 3]), SetTerm([3, 1, 2]), t)

    def test_setterm_unify_different(self):
        # nv
        t = Trail()
        assert not unify(SetTerm([1, 2]), SetTerm([1, 3]), t)

    def test_var_unifies_with_dictterm(self):
        # nv
        t = Trail()
        x = Var()
        d = DictTerm({"k": "v"})
        assert unify(x, d, t)
        assert deref(x) == d

    def test_var_unifies_with_setterm(self):
        # nv
        t = Trail()
        x = Var()
        s = SetTerm([1, 2])
        assert unify(x, s, t)
        assert deref(x) == s

    def test_dictterm_unifies_with_plain_dict(self):
        # nv — DictTerm and plain dict are treated as equivalent under
        # unification. See TestDictTermPlainDictEquality in
        # test_dict_set_builtins.py for the full matrix.
        t = Trail()
        assert unify(DictTerm({"a": 1}), {"a": 1}, t)

    def test_empty_dictterms_unify(self):
        # nv
        t = Trail()
        assert unify(DictTerm({}), DictTerm({}), t)

    def test_nested_dictterm_unify(self):
        # nv
        t = Trail()
        x = Var()
        d1 = DictTerm({"inner": DictTerm({"val": x})})
        d2 = DictTerm({"inner": DictTerm({"val": 99})})
        assert unify(d1, d2, t)
        assert deref(x) == 99

    def test_setterm_unifies_with_plain_set(self):
        # nv — SetTerm and plain set/frozenset are equivalent under
        # unification. Full matrix in TestSetTermPlainSetEquality in
        # test_dict_set_builtins.py.
        t = Trail()
        assert unify(SetTerm([1, 2]), frozenset([1, 2]), t)
        assert unify(SetTerm([1, 2]), {1, 2}, Trail())

    def test_empty_setterms_unify(self):
        # nv
        t = Trail()
        assert unify(SetTerm([]), SetTerm([]), t)


# ── Fixture integration ─────────────────────────────────────────────────────

class TestDictSetFixture:
    """Integration tests via dict_set_patterns.clausal fixture."""

    @pytest.fixture(scope="class")
    def mod(self):
        return _load_fixture()

    @pytest.fixture(scope="class")
    def logic_mod(self, mod):
        return mod.__dict__["$module"]

    def _query_test(self, mod, logic_mod, test_name):
        result = Var()
        sols = [deref(result) for _ in call("Test", test_name, module=logic_mod)]
        return sols

    def test_origin(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "origin")

    def test_x_axis(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "x_axis")

    def test_get_x(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "get_x")

    def test_get_y(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "get_y")

    def test_nested_city(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "nested city")

    def test_make_point(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "make_point")

    def test_dict_unify(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "dict unify")

    def test_dict_key_mismatch(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "dict key mismatch fails")

    def test_set_match(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "set match")

    def test_set_primary(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "set primary")

    def test_set_mismatch(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "set mismatch fails")

    def test_var_binds_dict(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "var binds dict")

    def test_empty_dict(self, mod, logic_mod):
        # nv
        assert self._query_test(mod, logic_mod, "empty dict")


# ── Backtracking tests ──────────────────────────────────────────────────────

class TestDictBacktracking:
    """Test that DictTerm unification backtracks correctly."""

    @pytest.fixture(scope="class")
    def mod(self):
        return _load_fixture()

    @pytest.fixture(scope="class")
    def logic_mod(self, mod):
        return mod.__dict__["$module"]

    def test_multiple_dict_clauses(self, mod, logic_mod):
        """point_type has 3 clauses; querying with Var should yield all 3."""
        # nv
        r = list(call("point_type", Var(), Var(), module=logic_mod))
        assert len(r) == 3

    def test_get_x_different_inputs(self, mod, logic_mod):
        """get_x extracts correct X from different dicts."""
        # nv
        x = Var()
        for trail in call("get_x", DictTerm({"x": 10, "y": 20}), x, module=logic_mod):
            assert deref(x) == 10
            break

    def test_get_x_another_input(self, mod, logic_mod):
        # nv
        x = Var()
        for trail in call("get_x", DictTerm({"x": 77, "y": 88}), x, module=logic_mod):
            assert deref(x) == 77
            break
