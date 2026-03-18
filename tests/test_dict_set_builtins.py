"""Tests for Dict and Set builtins (Phase 3 + Phase 4).

Covers:
  - IsDict/1, DictSize/2, DictKeys/2, DictValues/2
  - DictPairs/2 (both directions)
  - DictGet/3, DictPut/4, DictPutPairs/3, DictRemove/3, DictMerge/3
  - GenDict/3 (nondeterministic enumeration)
  - SubDict/2 (partial dict matching)
  - IsSet/1, SetSize/2, SetList/2 (both directions)
  - SetUnion/3, SetIntersection/3, SetSubtract/3, SetSymDiff/3
  - SetSubset/2, SetDisjoint/2
  - SetAdd/3, SetRemove/3
  - GenSet/2 (nondeterministic enumeration)
  - Splat sugar: {**OLD, k: v} in .clausal files
"""

from __future__ import annotations

import os
import pytest

from clausal.logic.database import Module
from clausal.logic.solve import solve, query
from clausal.logic.variables import Var, Trail, deref, unify
from clausal.terms import Call, LoadName, DictTerm, SetTerm
from clausal.import_hook import _load_module

_FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


# ── Helpers ───────────────────────────────────────────────────────────────────


def fresh_mod():
    return Module("test")


def _goal(name, *args):
    return Call(func=LoadName(name=name), args=list(args), kwargs=[])


def _succeeds(name, *args):
    return bool(list(solve(_goal(name, *args), fresh_mod())))


def _fails(name, *args):
    return not _succeeds(name, *args)


def _sols(name, *args):
    """Return list of dicts {index: deref'd value} for Var args."""
    var_positions = {i: a for i, a in enumerate(args) if isinstance(a, Var)}
    t = Trail()
    results = []
    for _ in solve(_goal(name, *args), fresh_mod(), t):
        results.append({i: deref(v) for i, v in var_positions.items()})
    return results


# ── IsDict ────────────────────────────────────────────────────────────────────


class TestIsDict:
    def test_is_dict_succeeds(self):
        assert _succeeds("IsDict", DictTerm({"a": 1}))

    def test_is_dict_fails_on_atom(self):
        assert _fails("IsDict", "not_a_dict")

    def test_is_dict_fails_on_set(self):
        assert _fails("IsDict", SetTerm([1, 2]))

    def test_is_dict_fails_on_atom(self):
        assert _fails("IsDict", "hello")

    def test_is_dict_fails_on_var(self):
        assert _fails("IsDict", Var())


# ── DictSize ──────────────────────────────────────────────────────────────────


class TestDictSize:
    def test_size_empty(self):
        v = Var()
        sols = _sols("DictSize", DictTerm({}), v)
        assert sols[0][1] == 0

    def test_size_three(self):
        v = Var()
        d = DictTerm({"a": 1, "b": 2, "c": 3})
        sols = _sols("DictSize", d, v)
        assert sols[0][1] == 3

    def test_size_fails_on_non_dict(self):
        assert _fails("DictSize", "not_a_dict", Var())


# ── DictKeys ──────────────────────────────────────────────────────────────────


class TestDictKeys:
    def test_keys_sorted(self):
        v = Var()
        d = DictTerm({"c": 1, "a": 2, "b": 3})
        sols = _sols("DictKeys", d, v)
        assert sols[0][1] == ["a", "b", "c"]

    def test_keys_unify_succeeds(self):
        d = DictTerm({"x": 1, "y": 2})
        assert _succeeds("DictKeys", d, ["x", "y"])

    def test_keys_wrong_order_fails(self):
        d = DictTerm({"x": 1, "y": 2})
        assert _fails("DictKeys", d, ["y", "x"])


# ── DictValues ────────────────────────────────────────────────────────────────


class TestDictValues:
    def test_values_in_key_order(self):
        v = Var()
        d = DictTerm({"b": 20, "a": 10})
        sols = _sols("DictValues", d, v)
        assert sols[0][1] == [10, 20]  # sorted by key: a→10, b→20


# ── DictPairs ─────────────────────────────────────────────────────────────────


class TestDictPairs:
    def test_dict_to_pairs(self):
        v = Var()
        d = DictTerm({"a": 1, "b": 2})
        sols = _sols("DictPairs", d, v)
        assert sols[0][1] == [["a", 1], ["b", 2]]

    def test_pairs_to_dict(self):
        v = Var()
        pairs = [["x", 10], ["y", 20]]
        sols = _sols("DictPairs", v, pairs)
        assert sols[0][0] == DictTerm({"x": 10, "y": 20})

    def test_pairs_to_dict_unordered(self):
        v = Var()
        pairs = [["b", 2], ["a", 1]]
        sols = _sols("DictPairs", v, pairs)
        assert sols[0][0] == DictTerm({"a": 1, "b": 2})


# ── DictGet ───────────────────────────────────────────────────────────────────


class TestDictGet:
    def test_get_existing_key(self):
        v = Var()
        d = DictTerm({"name": "Alice", "age": 30})
        sols = _sols("DictGet", "name", d, v)
        assert sols[0][2] == "Alice"

    def test_get_missing_key_fails(self):
        d = DictTerm({"name": "Alice"})
        assert _fails("DictGet", "missing", d, Var())

    def test_get_value_unify_succeeds(self):
        d = DictTerm({"x": 42})
        assert _succeeds("DictGet", "x", d, 42)

    def test_get_value_unify_fails(self):
        d = DictTerm({"x": 42})
        assert _fails("DictGet", "x", d, 99)

    def test_get_fails_unbound_key(self):
        d = DictTerm({"x": 1})
        assert _fails("DictGet", Var(), d, Var())


# ── DictPut ───────────────────────────────────────────────────────────────────


class TestDictPut:
    def test_put_new_key(self):
        v = Var()
        old = DictTerm({"a": 1})
        sols = _sols("DictPut", "b", 2, old, v)
        assert sols[0][3] == DictTerm({"a": 1, "b": 2})

    def test_put_overwrite_key(self):
        v = Var()
        old = DictTerm({"a": 1, "b": 99})
        sols = _sols("DictPut", "b", 2, old, v)
        assert sols[0][3] == DictTerm({"a": 1, "b": 2})

    def test_put_fails_unbound_key(self):
        old = DictTerm({"a": 1})
        assert _fails("DictPut", Var(), 2, old, Var())


# ── DictPutPairs ──────────────────────────────────────────────────────────────


class TestDictPutPairs:
    def test_put_pairs_bulk(self):
        v = Var()
        old = DictTerm({"a": 1})
        pairs = [["b", 2], ["c", 3]]
        sols = _sols("DictPutPairs", pairs, old, v)
        assert sols[0][2] == DictTerm({"a": 1, "b": 2, "c": 3})

    def test_put_pairs_overwrite(self):
        v = Var()
        old = DictTerm({"a": 1, "b": 0})
        sols = _sols("DictPutPairs", [["b", 99]], old, v)
        assert sols[0][2] == DictTerm({"a": 1, "b": 99})


# ── DictRemove ────────────────────────────────────────────────────────────────


class TestDictRemove:
    def test_remove_existing_key(self):
        v = Var()
        old = DictTerm({"a": 1, "b": 2, "c": 3})
        sols = _sols("DictRemove", "b", old, v)
        assert sols[0][2] == DictTerm({"a": 1, "c": 3})

    def test_remove_missing_key_fails(self):
        old = DictTerm({"a": 1})
        assert _fails("DictRemove", "x", old, Var())


# ── DictMerge ─────────────────────────────────────────────────────────────────


class TestDictMerge:
    def test_merge_disjoint(self):
        v = Var()
        d1 = DictTerm({"a": 1})
        d2 = DictTerm({"b": 2})
        sols = _sols("DictMerge", d1, d2, v)
        assert sols[0][2] == DictTerm({"a": 1, "b": 2})

    def test_merge_d2_overrides(self):
        v = Var()
        d1 = DictTerm({"a": 1, "b": 1})
        d2 = DictTerm({"b": 99, "c": 3})
        sols = _sols("DictMerge", d1, d2, v)
        assert sols[0][2] == DictTerm({"a": 1, "b": 99, "c": 3})

    def test_merge_empty_d1(self):
        v = Var()
        d2 = DictTerm({"x": 5})
        sols = _sols("DictMerge", DictTerm({}), d2, v)
        assert sols[0][2] == DictTerm({"x": 5})


# ── GenDict ───────────────────────────────────────────────────────────────────


class TestGenDict:
    def test_gen_dict_all_pairs(self):
        d = DictTerm({"a": 1, "b": 2, "c": 3})
        k_var, v_var = Var(), Var()
        t = Trail()
        pairs = {}
        for _ in solve(_goal("GenDict", k_var, d, v_var), fresh_mod(), t):
            pairs[deref(k_var)] = deref(v_var)
        assert pairs == {"a": 1, "b": 2, "c": 3}

    def test_gen_dict_count(self):
        d = DictTerm({"x": 10, "y": 20})
        sols = list(solve(_goal("GenDict", Var(), d, Var()), fresh_mod()))
        assert len(sols) == 2

    def test_gen_dict_filter_by_key(self):
        d = DictTerm({"a": 1, "b": 2})
        v = Var()
        sols = _sols("GenDict", "a", d, v)
        assert len(sols) == 1
        assert sols[0][2] == 1

    def test_gen_dict_empty(self):
        d = DictTerm({})
        assert _fails("GenDict", Var(), d, Var())


# ── SubDict ───────────────────────────────────────────────────────────────────


class TestSubDict:
    def test_subdict_exact_match(self):
        pat = DictTerm({"a": 1})
        full = DictTerm({"a": 1, "b": 2})
        assert _succeeds("SubDict", pat, full)

    def test_subdict_with_var_binds_value(self):
        v = Var()
        pat = DictTerm({"name": v})
        full = DictTerm({"name": "Alice", "age": 30})
        t = Trail()
        captured = []
        for _ in solve(_goal("SubDict", pat, full), fresh_mod(), t):
            captured.append(deref(v))
        assert captured == ["Alice"]

    def test_subdict_fails_missing_key(self):
        pat = DictTerm({"x": 1, "z": 99})
        full = DictTerm({"x": 1, "y": 2})
        assert _fails("SubDict", pat, full)

    def test_subdict_fails_value_mismatch(self):
        pat = DictTerm({"a": 99})
        full = DictTerm({"a": 1})
        assert _fails("SubDict", pat, full)

    def test_subdict_empty_pattern_always_succeeds(self):
        full = DictTerm({"a": 1, "b": 2})
        assert _succeeds("SubDict", DictTerm({}), full)

    def test_subdict_fails_non_dict_pattern(self):
        assert _fails("SubDict", "not_a_dict", DictTerm({"a": 1}))

    def test_subdict_fails_non_dict_full(self):
        assert _fails("SubDict", DictTerm({"a": 1}), "not_a_dict")

    def test_subdict_backtracking_undo(self):
        """Failed SubDict does not leave bindings on var in pattern."""
        v = Var()
        pat = DictTerm({"a": v, "z": 99})  # z missing from full → fails
        full = DictTerm({"a": 1, "b": 2})
        t = Trail()
        mark = t.mark()
        list(solve(_goal("SubDict", pat, full), fresh_mod(), t))
        # After failure, v should be unbound
        assert isinstance(deref(v), Var)


# ── IsSet ─────────────────────────────────────────────────────────────────────


class TestIsSet:
    def test_is_set_succeeds(self):
        assert _succeeds("IsSet", SetTerm([1, 2, 3]))

    def test_is_set_fails_on_list(self):
        assert _fails("IsSet", [1, 2, 3])

    def test_is_set_fails_on_dict(self):
        assert _fails("IsSet", DictTerm({"a": 1}))

    def test_is_set_fails_on_var(self):
        assert _fails("IsSet", Var())


# ── SetSize ───────────────────────────────────────────────────────────────────


class TestSetSize:
    def test_size(self):
        v = Var()
        s = SetTerm([1, 2, 3])
        sols = _sols("SetSize", s, v)
        assert sols[0][1] == 3

    def test_size_empty(self):
        v = Var()
        sols = _sols("SetSize", SetTerm([]), v)
        assert sols[0][1] == 0


# ── SetList ───────────────────────────────────────────────────────────────────


class TestSetList:
    def test_set_to_list(self):
        v = Var()
        s = SetTerm([3, 1, 2])
        sols = _sols("SetList", s, v)
        lst = sols[0][1]
        assert sorted(lst) == [1, 2, 3]

    def test_list_to_set(self):
        v = Var()
        sols = _sols("SetList", v, [1, 2, 3])
        assert sols[0][0] == SetTerm([1, 2, 3])

    def test_list_to_set_deduplicates(self):
        v = Var()
        sols = _sols("SetList", v, [1, 1, 2])
        assert sols[0][0] == SetTerm([1, 2])


# ── SetUnion ──────────────────────────────────────────────────────────────────


class TestSetUnion:
    def test_union(self):
        v = Var()
        s1 = SetTerm([1, 2])
        s2 = SetTerm([2, 3])
        sols = _sols("SetUnion", s1, s2, v)
        assert sols[0][2] == SetTerm([1, 2, 3])

    def test_union_disjoint(self):
        v = Var()
        sols = _sols("SetUnion", SetTerm([1]), SetTerm([2]), v)
        assert sols[0][2] == SetTerm([1, 2])


# ── SetIntersection ───────────────────────────────────────────────────────────


class TestSetIntersection:
    def test_intersection(self):
        v = Var()
        s1 = SetTerm([1, 2, 3])
        s2 = SetTerm([2, 3, 4])
        sols = _sols("SetIntersection", s1, s2, v)
        assert sols[0][2] == SetTerm([2, 3])

    def test_intersection_empty(self):
        v = Var()
        sols = _sols("SetIntersection", SetTerm([1]), SetTerm([2]), v)
        assert sols[0][2] == SetTerm([])


# ── SetSubtract ───────────────────────────────────────────────────────────────


class TestSetSubtract:
    def test_subtract(self):
        v = Var()
        s1 = SetTerm([1, 2, 3])
        s2 = SetTerm([2, 3])
        sols = _sols("SetSubtract", s1, s2, v)
        assert sols[0][2] == SetTerm([1])

    def test_subtract_all(self):
        v = Var()
        sols = _sols("SetSubtract", SetTerm([1, 2]), SetTerm([1, 2, 3]), v)
        assert sols[0][2] == SetTerm([])


# ── SetSymDiff ────────────────────────────────────────────────────────────────


class TestSetSymDiff:
    def test_symdiff(self):
        v = Var()
        s1 = SetTerm([1, 2, 3])
        s2 = SetTerm([2, 3, 4])
        sols = _sols("SetSymDiff", s1, s2, v)
        assert sols[0][2] == SetTerm([1, 4])

    def test_symdiff_disjoint(self):
        v = Var()
        sols = _sols("SetSymDiff", SetTerm([1]), SetTerm([2]), v)
        assert sols[0][2] == SetTerm([1, 2])


# ── SetSubset / SetDisjoint ───────────────────────────────────────────────────


class TestSetSubsetDisjoint:
    def test_subset_true(self):
        assert _succeeds("SetSubset", SetTerm([1, 2]), SetTerm([1, 2, 3]))

    def test_subset_false(self):
        assert _fails("SetSubset", SetTerm([1, 4]), SetTerm([1, 2, 3]))

    def test_subset_equal(self):
        assert _succeeds("SetSubset", SetTerm([1, 2]), SetTerm([1, 2]))

    def test_empty_is_subset_of_anything(self):
        assert _succeeds("SetSubset", SetTerm([]), SetTerm([1, 2, 3]))

    def test_disjoint_true(self):
        assert _succeeds("SetDisjoint", SetTerm([1, 2]), SetTerm([3, 4]))

    def test_disjoint_false(self):
        assert _fails("SetDisjoint", SetTerm([1, 2]), SetTerm([2, 3]))

    def test_disjoint_empty(self):
        assert _succeeds("SetDisjoint", SetTerm([]), SetTerm([1, 2]))


# ── SetAdd / SetRemove ────────────────────────────────────────────────────────


class TestSetAddRemove:
    def test_add(self):
        v = Var()
        old = SetTerm([1, 2])
        sols = _sols("SetAdd", 3, old, v)
        assert sols[0][2] == SetTerm([1, 2, 3])

    def test_add_existing_is_noop(self):
        v = Var()
        old = SetTerm([1, 2])
        sols = _sols("SetAdd", 2, old, v)
        assert sols[0][2] == SetTerm([1, 2])

    def test_remove(self):
        v = Var()
        old = SetTerm([1, 2, 3])
        sols = _sols("SetRemove", 2, old, v)
        assert sols[0][2] == SetTerm([1, 3])

    def test_remove_absent_is_noop(self):
        v = Var()
        old = SetTerm([1, 2])
        sols = _sols("SetRemove", 99, old, v)
        assert sols[0][2] == SetTerm([1, 2])


# ── GenSet ────────────────────────────────────────────────────────────────────


class TestGenSet:
    def test_gen_set_all(self):
        s = SetTerm([1, 2, 3])
        e_var = Var()
        t = Trail()
        elems = set()
        for _ in solve(_goal("GenSet", e_var, s), fresh_mod(), t):
            elems.add(deref(e_var))
        assert elems == {1, 2, 3}

    def test_gen_set_count(self):
        s = SetTerm(["a", "b"])
        sols = list(solve(_goal("GenSet", Var(), s), fresh_mod()))
        assert len(sols) == 2

    def test_gen_set_empty(self):
        assert _fails("GenSet", Var(), SetTerm([]))


# ── .clausal integration ──────────────────────────────────────────────────────


def _load_fixture(name):
    return _load_module(name, os.path.join(_FIXTURE_DIR, f"{name}.clausal"))


class TestClausalIntegration:
    @pytest.fixture(autouse=True)
    def _load(self):
        mod = _load_fixture("dict_set_builtins")
        self.logic_mod = mod.__dict__["$module"]

    def _capture(self, pred_name, *args):
        """Run pred, capture deref'd values of any Var args per solution."""
        from clausal.logic.solve import call as lc_call
        var_positions = {i: a for i, a in enumerate(args) if isinstance(a, Var)}
        results = []
        for _ in lc_call(pred_name, *args, module=self.logic_mod):
            results.append({i: deref(v) for i, v in var_positions.items()})
        return results

    def test_get_name(self):
        """get_name/2 uses SubDict to extract a name field."""
        name_var = Var()
        sols = self._capture("get_name", DictTerm({"name": "Alice", "age": 30}), name_var)
        assert sols
        assert sols[0][1] == "Alice"

    def test_is_admin(self):
        from clausal.logic.solve import call as lc_call
        admin = DictTerm({"name": "Bob", "role": "admin"})
        user = DictTerm({"name": "Alice", "role": "user"})
        assert list(lc_call("is_admin", admin, module=self.logic_mod))
        assert not list(lc_call("is_admin", user, module=self.logic_mod))

    def test_update_field(self):
        new_var = Var()
        old = DictTerm({"x": 1, "y": 2})
        sols = self._capture("update_field", "x", 99, old, new_var)
        assert sols[0][3] == DictTerm({"x": 99, "y": 2})

    def test_dict_member(self):
        d = DictTerm({"a": 1, "b": 2})
        k_var, v_var = Var(), Var()
        sols = self._capture("dict_member", k_var, d, v_var)
        pairs = {s[0]: s[2] for s in sols}
        assert pairs == {"a": 1, "b": 2}

    def test_set_common(self):
        s1 = SetTerm([1, 2, 3])
        s2 = SetTerm([2, 3, 4])
        inter_var = Var()
        sols = self._capture("set_common", s1, s2, inter_var)
        assert sols[0][2] == SetTerm([2, 3])

    def test_set_member(self):
        s = SetTerm(["a", "b", "c"])
        e_var = Var()
        sols = self._capture("set_member", e_var, s)
        elems = {s[0] for s in sols}
        assert elems == {"a", "b", "c"}

    def test_splat_update(self):
        """splat_update/4 uses {**OLD, KEY: VALUE} sugar."""
        old = DictTerm({"x": 1, "y": 2})
        new_var = Var()
        sols = self._capture("splat_update", old, "z", 3, new_var)
        assert sols[0][3] == DictTerm({"x": 1, "y": 2, "z": 3})
