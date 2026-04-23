"""Tests for DictTerm and SetTerm — Phase 1 of dicts/sets support.

Covers:
  - DictTerm: construction, equality, hashing, repr, term_str
  - DictTerm unification: same keys, different keys, nested vars, trail undo
  - DictTerm walk: variables inside dict values are substituted
  - DictTerm occurs_check: detects vars inside dict values
  - SetTerm: construction, equality, hashing, repr, term_str
  - SetTerm unification: same elements, different elements
  - _collect_vars: extracts vars from DictTerm values
"""

from __future__ import annotations

import pytest

from clausal.logic.builtins import structural_unify
from clausal.logic.variables import Var, Trail, deref, walk, is_var, unify
from clausal.terms import DictTerm, SetTerm, term_str


def fresh() -> Trail:
    return Trail()


# ── DictTerm basics ──────────────────────────────────────────────────────────


class TestDictTermBasics:
    def test_construction(self):
        # nv
        d = DictTerm({"x": 1, "y": 2})
        assert d["x"] == 1
        assert d["y"] == 2
        assert len(d) == 2

    def test_defensive_copy(self):
        # nv
        data = {"a": 1}
        d = DictTerm(data)
        data["b"] = 2
        assert len(d) == 1  # original not mutated

    def test_keys_values_items(self):
        # nv
        d = DictTerm({"x": 1, "y": 2})
        assert set(d.keys()) == {"x", "y"}
        assert set(d.values()) == {1, 2}
        assert set(d.items()) == {("x", 1), ("y", 2)}

    def test_contains(self):
        # nv
        d = DictTerm({"x": 1})
        assert "x" in d
        assert "y" not in d

    def test_equality(self):
        # nv
        d1 = DictTerm({"x": 1, "y": 2})
        d2 = DictTerm({"y": 2, "x": 1})
        assert d1 == d2

    def test_inequality_different_keys(self):
        # nv
        d1 = DictTerm({"x": 1})
        d2 = DictTerm({"y": 1})
        assert d1 != d2

    def test_inequality_different_values(self):
        # nv
        d1 = DictTerm({"x": 1})
        d2 = DictTerm({"x": 2})
        assert d1 != d2

    def test_equals_plain_dict_with_matching_content(self):
        # nv — symmetric equality: DictTerm and plain dict are treated as
        # equivalent representations of the same mapping.
        assert DictTerm({"x": 1}) == {"x": 1}
        assert {"x": 1} == DictTerm({"x": 1})

    def test_differs_from_plain_dict_with_different_content(self):
        # nv
        assert DictTerm({"x": 1}) != {"x": 2}
        assert DictTerm({"x": 1}) != {"y": 1}

    def test_hash(self):
        # nv
        d1 = DictTerm({"x": 1, "y": 2})
        d2 = DictTerm({"y": 2, "x": 1})
        assert hash(d1) == hash(d2)

    def test_repr(self):
        # nv
        d = DictTerm({"x": 1})
        assert "DictTerm" in repr(d)
        assert "'x': 1" in repr(d)

    def test_term_str(self):
        # nv
        d = DictTerm({"x": 1})
        s = term_str(d)
        assert "'x': 1" in s


# ── DictTerm unification ─────────────────────────────────────────────────────


class TestDictTermUnification:
    def test_same_ground_succeeds(self):
        # nv
        t = fresh()
        d1 = DictTerm({"x": 1, "y": 2})
        d2 = DictTerm({"x": 1, "y": 2})
        assert structural_unify(d1, d2, t)

    def test_different_keys_fails(self):
        # nv
        t = fresh()
        d1 = DictTerm({"x": 1})
        d2 = DictTerm({"y": 1})
        assert not structural_unify(d1, d2, t)

    def test_different_key_count_fails(self):
        # nv
        t = fresh()
        d1 = DictTerm({"x": 1})
        d2 = DictTerm({"x": 1, "y": 2})
        assert not structural_unify(d1, d2, t)

    def test_different_values_fails(self):
        # nv
        t = fresh()
        d1 = DictTerm({"x": 1})
        d2 = DictTerm({"x": 2})
        assert not structural_unify(d1, d2, t)

    def test_var_in_value_binds(self):
        # nv
        t = fresh()
        v = Var()
        d1 = DictTerm({"x": v, "y": 2})
        d2 = DictTerm({"x": 42, "y": 2})
        assert structural_unify(d1, d2, t)
        assert deref(v) == 42

    def test_var_on_both_sides(self):
        # nv
        t = fresh()
        v1 = Var()
        v2 = Var()
        d1 = DictTerm({"x": v1, "y": 10})
        d2 = DictTerm({"x": 5, "y": v2})
        assert structural_unify(d1, d2, t)
        assert deref(v1) == 5
        assert deref(v2) == 10

    def test_nested_dict_with_vars(self):
        # nv
        t = fresh()
        v = Var()
        d1 = DictTerm({"inner": DictTerm({"a": v})})
        d2 = DictTerm({"inner": DictTerm({"a": 99})})
        assert structural_unify(d1, d2, t)
        assert deref(v) == 99

    def test_trail_undo_on_failure(self):
        # nv
        t = fresh()
        v = Var()
        d1 = DictTerm({"x": v, "y": 1})
        d2 = DictTerm({"x": 42, "y": 2})  # y mismatch
        mark = t.mark()
        assert not structural_unify(d1, d2, t)
        # v should NOT remain bound after failure + undo
        t.undo(mark)
        assert is_var(v)

    def test_empty_dicts_unify(self):
        # nv
        t = fresh()
        assert structural_unify(DictTerm({}), DictTerm({}), t)

    def test_dict_does_not_unify_with_non_dict(self):
        # nv
        t = fresh()
        d = DictTerm({"x": 1})
        assert not structural_unify(d, 42, t)
        assert not structural_unify(d, [1, 2], t)

    def test_var_unifies_with_dict(self):
        # nv
        t = fresh()
        v = Var()
        d = DictTerm({"x": 1})
        assert structural_unify(v, d, t)
        assert deref(v) == d


# ── DictTerm walk ────────────────────────────────────────────────────────────


class TestDictTermWalk:
    def test_walk_substitutes_vars(self):
        # nv
        t = fresh()
        v = Var()
        d = DictTerm({"x": v, "y": 2})
        unify(v, 42, t)
        walked = walk(d)
        assert isinstance(walked, DictTerm)
        assert walked["x"] == 42
        assert walked["y"] == 2

    def test_walk_nested(self):
        # nv
        t = fresh()
        v = Var()
        d = DictTerm({"inner": [v, 1]})
        unify(v, "hello", t)
        walked = walk(d)
        assert isinstance(walked, DictTerm)
        assert walked["inner"] == ["hello", 1]

    def test_walk_no_vars_returns_equivalent(self):
        # nv
        d = DictTerm({"x": 1, "y": 2})
        walked = walk(d)
        assert walked == d


# ── DictTerm occurs_check ────────────────────────────────────────────────────


class TestDictTermOccursCheck:
    def test_occurs_check_detects_var_in_value(self):
        # nv
        from clausal.logic.variables import unify_with_occurs_check
        t = fresh()
        v = Var()
        d = DictTerm({"x": v})
        # Unifying v with a DictTerm containing v should fail with occurs check
        assert not unify_with_occurs_check(v, d, t)

    def test_occurs_check_allows_non_circular(self):
        # nv
        from clausal.logic.variables import unify_with_occurs_check
        t = fresh()
        v = Var()
        d = DictTerm({"x": 1})
        assert unify_with_occurs_check(v, d, t)
        assert deref(v) == d


# ── SetTerm basics ───────────────────────────────────────────────────────────


class TestSetTermBasics:
    def test_construction(self):
        # nv
        s = SetTerm([1, 2, 3])
        assert len(s) == 3
        assert 1 in s
        assert 4 not in s

    def test_from_set(self):
        # nv
        s = SetTerm({1, 2, 3})
        assert len(s) == 3

    def test_equality_order_independent(self):
        # nv
        s1 = SetTerm([3, 1, 2])
        s2 = SetTerm([1, 2, 3])
        assert s1 == s2

    def test_inequality(self):
        # nv
        s1 = SetTerm([1, 2])
        s2 = SetTerm([1, 3])
        assert s1 != s2

    def test_equals_plain_set_with_matching_content(self):
        # nv — symmetric equality: SetTerm, plain set, and frozenset with
        # the same elements all compare equal.
        assert SetTerm([1, 2]) == {1, 2}
        assert {1, 2} == SetTerm([1, 2])
        assert SetTerm([1, 2]) == frozenset([1, 2])
        assert frozenset([1, 2]) == SetTerm([1, 2])

    def test_differs_from_plain_set_with_different_content(self):
        # nv
        assert SetTerm([1, 2]) != {1, 3}
        assert SetTerm([1, 2]) != {1, 2, 3}

    def test_hash(self):
        # nv
        s1 = SetTerm([3, 1, 2])
        s2 = SetTerm([1, 2, 3])
        assert hash(s1) == hash(s2)

    def test_iter(self):
        # nv
        s = SetTerm([1, 2, 3])
        assert set(s) == {1, 2, 3}

    def test_repr(self):
        # nv
        s = SetTerm([1])
        assert "SetTerm" in repr(s)

    def test_term_str(self):
        # nv
        s = SetTerm([1, 2])
        result = term_str(s)
        assert "1" in result and "2" in result


# ── SetTerm unification ──────────────────────────────────────────────────────


class TestSetTermUnification:
    def test_same_sets_unify(self):
        # nv
        t = fresh()
        s1 = SetTerm([1, 2, 3])
        s2 = SetTerm([3, 2, 1])
        assert structural_unify(s1, s2, t)

    def test_different_sets_fail(self):
        # nv
        t = fresh()
        s1 = SetTerm([1, 2])
        s2 = SetTerm([1, 3])
        assert not structural_unify(s1, s2, t)

    def test_different_size_fails(self):
        # nv
        t = fresh()
        s1 = SetTerm([1, 2])
        s2 = SetTerm([1, 2, 3])
        assert not structural_unify(s1, s2, t)

    def test_empty_sets_unify(self):
        # nv
        t = fresh()
        assert structural_unify(SetTerm([]), SetTerm([]), t)

    def test_var_unifies_with_set(self):
        # nv
        t = fresh()
        v = Var()
        s = SetTerm([1, 2])
        assert structural_unify(v, s, t)
        assert deref(v) == s

    def test_set_does_not_unify_with_non_set(self):
        # nv
        t = fresh()
        s = SetTerm([1, 2])
        assert not structural_unify(s, [1, 2], t)


# ── _collect_vars integration ────────────────────────────────────────────────


class TestCollectVars:
    def test_collect_vars_from_dictterm(self):
        from clausal.logic.compiler._vars import _collect_vars
        v1 = Var()
        v2 = Var()
        d = DictTerm({"x": v1, "y": v2, "z": 42})
        vars_found = _collect_vars(d)
        assert v1 in vars_found
        assert v2 in vars_found
        assert len(vars_found) == 2

    def test_collect_vars_from_setterm_empty(self):
        from clausal.logic.compiler._vars import _collect_vars
        s = SetTerm([1, 2, 3])
        vars_found = _collect_vars(s)
        assert vars_found == []
