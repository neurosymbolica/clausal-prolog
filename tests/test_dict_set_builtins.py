"""Tests for Dict and Set builtins (Phase 3 + Phase 4).

Covers:
  - is_dict/1, dict_size/2, dict_keys/2, dict_values/2
  - dict_pairs/2 (both directions)
  - dict_get/3, dict_put/4, dict_put_pairs/3, dict_remove/3, dict_merge/3
  - gen_dict/3 (nondeterministic enumeration)
  - ``KEY in DICT`` and ``(KEY, VALUE) in DICT`` syntax
  - sub_dict/2 (partial dict matching)
  - is_set/1, set_size/2, set_list/2 (both directions)
  - set_union/3, set_intersection/3, set_subtract/3, set_sym_diff/3
  - set_subset/2, set_disjoint/2
  - set_add/3, set_remove/3
  - gen_set/2 (nondeterministic enumeration)
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


# ── is_dict ────────────────────────────────────────────────────────────────────


class TestIsDict:
    def test_is_dict_succeeds(self):
        # nv
        assert _succeeds("is_dict", DictTerm({"a": 1}))

    def test_is_dict_fails_on_atom(self):
        # nv
        assert _fails("is_dict", "not_a_dict")

    def test_is_dict_fails_on_set(self):
        # nv
        assert _fails("is_dict", SetTerm([1, 2]))

    def test_is_dict_fails_on_atom(self):
        # nv
        assert _fails("is_dict", "hello")

    def test_is_dict_fails_on_var(self):
        # nv
        assert _fails("is_dict", Var())


# ── dict_size ──────────────────────────────────────────────────────────────────


class TestDictSize:
    def test_size_empty(self):
        # nv
        v = Var()
        sols = _sols("dict_size", DictTerm({}), v)
        assert sols[0][1] == 0

    def test_size_three(self):
        # nv
        v = Var()
        d = DictTerm({"a": 1, "b": 2, "c": 3})
        sols = _sols("dict_size", d, v)
        assert sols[0][1] == 3

    def test_size_fails_on_non_dict(self):
        # nv
        assert _fails("dict_size", "not_a_dict", Var())


# ── dict_keys ──────────────────────────────────────────────────────────────────


class TestDictKeys:
    def test_keys_sorted(self):
        # nv
        v = Var()
        d = DictTerm({"c": 1, "a": 2, "b": 3})
        sols = _sols("dict_keys", d, v)
        assert sols[0][1] == ["a", "b", "c"]

    def test_keys_unify_succeeds(self):
        # nv
        d = DictTerm({"x": 1, "y": 2})
        assert _succeeds("dict_keys", d, ["x", "y"])

    def test_keys_wrong_order_fails(self):
        # nv
        d = DictTerm({"x": 1, "y": 2})
        assert _fails("dict_keys", d, ["y", "x"])


# ── dict_values ────────────────────────────────────────────────────────────────


class TestDictValues:
    def test_values_in_key_order(self):
        # nv
        v = Var()
        d = DictTerm({"b": 20, "a": 10})
        sols = _sols("dict_values", d, v)
        assert sols[0][1] == [10, 20]  # sorted by key: a→10, b→20


# ── dict_pairs ─────────────────────────────────────────────────────────────────


class TestDictPairs:
    def test_dict_to_pairs(self):
        # nv
        v = Var()
        d = DictTerm({"a": 1, "b": 2})
        sols = _sols("dict_pairs", d, v)
        assert sols[0][1] == [["a", 1], ["b", 2]]

    def test_pairs_to_dict(self):
        # nv
        v = Var()
        pairs = [["x", 10], ["y", 20]]
        sols = _sols("dict_pairs", v, pairs)
        assert sols[0][0] == DictTerm({"x": 10, "y": 20})

    def test_pairs_to_dict_unordered(self):
        # nv
        v = Var()
        pairs = [["b", 2], ["a", 1]]
        sols = _sols("dict_pairs", v, pairs)
        assert sols[0][0] == DictTerm({"a": 1, "b": 2})


# ── dict_get ───────────────────────────────────────────────────────────────────


class TestDictGet:
    def test_get_existing_key(self):
        # nv
        v = Var()
        d = DictTerm({"name": "Alice", "age": 30})
        sols = _sols("dict_get", "name", d, v)
        assert sols[0][2] == "Alice"

    def test_get_missing_key_fails(self):
        # nv
        d = DictTerm({"name": "Alice"})
        assert _fails("dict_get", "missing", d, Var())

    def test_get_value_unify_succeeds(self):
        # nv
        d = DictTerm({"x": 42})
        assert _succeeds("dict_get", "x", d, 42)

    def test_get_value_unify_fails(self):
        # nv
        d = DictTerm({"x": 42})
        assert _fails("dict_get", "x", d, 99)

    def test_get_fails_unbound_key(self):
        # nv
        d = DictTerm({"x": 1})
        assert _fails("dict_get", Var(), d, Var())


# ── dict_put ───────────────────────────────────────────────────────────────────


class TestDictPut:
    def test_put_new_key(self):
        # nv
        v = Var()
        old = DictTerm({"a": 1})
        sols = _sols("dict_put", "b", 2, old, v)
        assert sols[0][3] == DictTerm({"a": 1, "b": 2})

    def test_put_overwrite_key(self):
        # nv
        v = Var()
        old = DictTerm({"a": 1, "b": 99})
        sols = _sols("dict_put", "b", 2, old, v)
        assert sols[0][3] == DictTerm({"a": 1, "b": 2})

    def test_put_fails_unbound_key(self):
        # nv
        old = DictTerm({"a": 1})
        assert _fails("dict_put", Var(), 2, old, Var())


# ── dict_put_pairs ──────────────────────────────────────────────────────────────


class TestDictPutPairs:
    def test_put_pairs_bulk(self):
        # nv
        v = Var()
        old = DictTerm({"a": 1})
        pairs = [["b", 2], ["c", 3]]
        sols = _sols("dict_put_pairs", pairs, old, v)
        assert sols[0][2] == DictTerm({"a": 1, "b": 2, "c": 3})

    def test_put_pairs_overwrite(self):
        # nv
        v = Var()
        old = DictTerm({"a": 1, "b": 0})
        sols = _sols("dict_put_pairs", [["b", 99]], old, v)
        assert sols[0][2] == DictTerm({"a": 1, "b": 99})


# ── dict_remove ────────────────────────────────────────────────────────────────


class TestDictRemove:
    def test_remove_existing_key(self):
        # nv
        v = Var()
        old = DictTerm({"a": 1, "b": 2, "c": 3})
        sols = _sols("dict_remove", "b", old, v)
        assert sols[0][2] == DictTerm({"a": 1, "c": 3})

    def test_remove_missing_key_fails(self):
        # nv
        old = DictTerm({"a": 1})
        assert _fails("dict_remove", "x", old, Var())


# ── dict_merge ─────────────────────────────────────────────────────────────────


class TestDictMerge:
    def test_merge_disjoint(self):
        # nv
        v = Var()
        d1 = DictTerm({"a": 1})
        d2 = DictTerm({"b": 2})
        sols = _sols("dict_merge", d1, d2, v)
        assert sols[0][2] == DictTerm({"a": 1, "b": 2})

    def test_merge_d2_overrides(self):
        # nv
        v = Var()
        d1 = DictTerm({"a": 1, "b": 1})
        d2 = DictTerm({"b": 99, "c": 3})
        sols = _sols("dict_merge", d1, d2, v)
        assert sols[0][2] == DictTerm({"a": 1, "b": 99, "c": 3})

    def test_merge_empty_d1(self):
        # nv
        v = Var()
        d2 = DictTerm({"x": 5})
        sols = _sols("dict_merge", DictTerm({}), d2, v)
        assert sols[0][2] == DictTerm({"x": 5})


# ── gen_dict ───────────────────────────────────────────────────────────────────


class TestGenDict:
    def test_gen_dict_all_pairs(self):
        # nv
        d = DictTerm({"a": 1, "b": 2, "c": 3})
        k_var, v_var = Var(), Var()
        t = Trail()
        pairs = {}
        for _ in solve(_goal("gen_dict", k_var, d, v_var), fresh_mod(), t):
            pairs[deref(k_var)] = deref(v_var)
        assert pairs == {"a": 1, "b": 2, "c": 3}

    def test_gen_dict_count(self):
        # nv
        d = DictTerm({"x": 10, "y": 20})
        sols = list(solve(_goal("gen_dict", Var(), d, Var()), fresh_mod()))
        assert len(sols) == 2

    def test_gen_dict_filter_by_key(self):
        # nv
        d = DictTerm({"a": 1, "b": 2})
        v = Var()
        sols = _sols("gen_dict", "a", d, v)
        assert len(sols) == 1
        assert sols[0][2] == 1

    def test_gen_dict_empty(self):
        # nv
        d = DictTerm({})
        assert _fails("gen_dict", Var(), d, Var())


# ── sub_dict ───────────────────────────────────────────────────────────────────


class TestSubDict:
    def test_subdict_exact_match(self):
        # nv
        pat = DictTerm({"a": 1})
        full = DictTerm({"a": 1, "b": 2})
        assert _succeeds("sub_dict", pat, full)

    def test_subdict_with_var_binds_value(self):
        # nv
        v = Var()
        pat = DictTerm({"name": v})
        full = DictTerm({"name": "Alice", "age": 30})
        t = Trail()
        captured = []
        for _ in solve(_goal("sub_dict", pat, full), fresh_mod(), t):
            captured.append(deref(v))
        assert captured == ["Alice"]

    def test_subdict_fails_missing_key(self):
        # nv
        pat = DictTerm({"x": 1, "z": 99})
        full = DictTerm({"x": 1, "y": 2})
        assert _fails("sub_dict", pat, full)

    def test_subdict_fails_value_mismatch(self):
        # nv
        pat = DictTerm({"a": 99})
        full = DictTerm({"a": 1})
        assert _fails("sub_dict", pat, full)

    def test_subdict_empty_pattern_always_succeeds(self):
        # nv
        full = DictTerm({"a": 1, "b": 2})
        assert _succeeds("sub_dict", DictTerm({}), full)

    def test_subdict_fails_non_dict_pattern(self):
        # nv
        assert _fails("sub_dict", "not_a_dict", DictTerm({"a": 1}))

    def test_subdict_fails_non_dict_full(self):
        # nv
        assert _fails("sub_dict", DictTerm({"a": 1}), "not_a_dict")

    def test_subdict_backtracking_undo(self):
        """Failed sub_dict does not leave bindings on var in pattern."""
        # nv
        v = Var()
        pat = DictTerm({"a": v, "z": 99})  # z missing from full → fails
        full = DictTerm({"a": 1, "b": 2})
        t = Trail()
        mark = t.mark()
        list(solve(_goal("sub_dict", pat, full), fresh_mod(), t))
        # After failure, v should be unbound
        assert isinstance(deref(v), Var)


# ── is_set ─────────────────────────────────────────────────────────────────────


class TestIsSet:
    def test_is_set_succeeds(self):
        # nv
        assert _succeeds("is_set", SetTerm([1, 2, 3]))

    def test_is_set_fails_on_list(self):
        # nv
        assert _fails("is_set", [1, 2, 3])

    def test_is_set_fails_on_dict(self):
        # nv
        assert _fails("is_set", DictTerm({"a": 1}))

    def test_is_set_fails_on_var(self):
        # nv
        assert _fails("is_set", Var())


# ── set_size ───────────────────────────────────────────────────────────────────


class TestSetSize:
    def test_size(self):
        # nv
        v = Var()
        s = SetTerm([1, 2, 3])
        sols = _sols("set_size", s, v)
        assert sols[0][1] == 3

    def test_size_empty(self):
        # nv
        v = Var()
        sols = _sols("set_size", SetTerm([]), v)
        assert sols[0][1] == 0


# ── set_list ───────────────────────────────────────────────────────────────────


class TestSetList:
    def test_set_to_list(self):
        # nv
        v = Var()
        s = SetTerm([3, 1, 2])
        sols = _sols("set_list", s, v)
        lst = sols[0][1]
        assert sorted(lst) == [1, 2, 3]

    def test_list_to_set(self):
        # nv
        v = Var()
        sols = _sols("set_list", v, [1, 2, 3])
        assert sols[0][0] == SetTerm([1, 2, 3])

    def test_list_to_set_deduplicates(self):
        # nv
        v = Var()
        sols = _sols("set_list", v, [1, 1, 2])
        assert sols[0][0] == SetTerm([1, 2])


# ── set_union ──────────────────────────────────────────────────────────────────


class TestSetUnion:
    def test_union(self):
        # nv
        v = Var()
        s1 = SetTerm([1, 2])
        s2 = SetTerm([2, 3])
        sols = _sols("set_union", s1, s2, v)
        assert sols[0][2] == SetTerm([1, 2, 3])

    def test_union_disjoint(self):
        # nv
        v = Var()
        sols = _sols("set_union", SetTerm([1]), SetTerm([2]), v)
        assert sols[0][2] == SetTerm([1, 2])


# ── set_intersection ───────────────────────────────────────────────────────────


class TestSetIntersection:
    def test_intersection(self):
        # nv
        v = Var()
        s1 = SetTerm([1, 2, 3])
        s2 = SetTerm([2, 3, 4])
        sols = _sols("set_intersection", s1, s2, v)
        assert sols[0][2] == SetTerm([2, 3])

    def test_intersection_empty(self):
        # nv
        v = Var()
        sols = _sols("set_intersection", SetTerm([1]), SetTerm([2]), v)
        assert sols[0][2] == SetTerm([])


# ── set_subtract ───────────────────────────────────────────────────────────────


class TestSetSubtract:
    def test_subtract(self):
        # nv
        v = Var()
        s1 = SetTerm([1, 2, 3])
        s2 = SetTerm([2, 3])
        sols = _sols("set_subtract", s1, s2, v)
        assert sols[0][2] == SetTerm([1])

    def test_subtract_all(self):
        # nv
        v = Var()
        sols = _sols("set_subtract", SetTerm([1, 2]), SetTerm([1, 2, 3]), v)
        assert sols[0][2] == SetTerm([])


# ── set_sym_diff ────────────────────────────────────────────────────────────────


class TestSetSymDiff:
    def test_symdiff(self):
        # nv
        v = Var()
        s1 = SetTerm([1, 2, 3])
        s2 = SetTerm([2, 3, 4])
        sols = _sols("set_sym_diff", s1, s2, v)
        assert sols[0][2] == SetTerm([1, 4])

    def test_symdiff_disjoint(self):
        # nv
        v = Var()
        sols = _sols("set_sym_diff", SetTerm([1]), SetTerm([2]), v)
        assert sols[0][2] == SetTerm([1, 2])


# ── set_subset / set_disjoint ───────────────────────────────────────────────────


class TestSetSubsetDisjoint:
    def test_subset_true(self):
        # nv
        assert _succeeds("set_subset", SetTerm([1, 2]), SetTerm([1, 2, 3]))

    def test_subset_false(self):
        # nv
        assert _fails("set_subset", SetTerm([1, 4]), SetTerm([1, 2, 3]))

    def test_subset_equal(self):
        # nv
        assert _succeeds("set_subset", SetTerm([1, 2]), SetTerm([1, 2]))

    def test_empty_is_subset_of_anything(self):
        # nv
        assert _succeeds("set_subset", SetTerm([]), SetTerm([1, 2, 3]))

    def test_disjoint_true(self):
        # nv
        assert _succeeds("set_disjoint", SetTerm([1, 2]), SetTerm([3, 4]))

    def test_disjoint_false(self):
        # nv
        assert _fails("set_disjoint", SetTerm([1, 2]), SetTerm([2, 3]))

    def test_disjoint_empty(self):
        # nv
        assert _succeeds("set_disjoint", SetTerm([]), SetTerm([1, 2]))


# ── set_add / set_remove ────────────────────────────────────────────────────────


class TestSetAddRemove:
    def test_add(self):
        # nv
        v = Var()
        old = SetTerm([1, 2])
        sols = _sols("set_add", 3, old, v)
        assert sols[0][2] == SetTerm([1, 2, 3])

    def test_add_existing_is_noop(self):
        # nv
        v = Var()
        old = SetTerm([1, 2])
        sols = _sols("set_add", 2, old, v)
        assert sols[0][2] == SetTerm([1, 2])

    def test_remove(self):
        # nv
        v = Var()
        old = SetTerm([1, 2, 3])
        sols = _sols("set_remove", 2, old, v)
        assert sols[0][2] == SetTerm([1, 3])

    def test_remove_absent_is_noop(self):
        # nv
        v = Var()
        old = SetTerm([1, 2])
        sols = _sols("set_remove", 99, old, v)
        assert sols[0][2] == SetTerm([1, 2])


# ── gen_set ────────────────────────────────────────────────────────────────────


class TestGenSet:
    def test_gen_set_all(self):
        # nv
        s = SetTerm([1, 2, 3])
        e_var = Var()
        t = Trail()
        elems = set()
        for _ in solve(_goal("gen_set", e_var, s), fresh_mod(), t):
            elems.add(deref(e_var))
        assert elems == {1, 2, 3}

    def test_gen_set_count(self):
        # nv
        s = SetTerm(["a", "b"])
        sols = list(solve(_goal("gen_set", Var(), s), fresh_mod()))
        assert len(sols) == 2

    def test_gen_set_empty(self):
        # nv
        assert _fails("gen_set", Var(), SetTerm([]))


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
        """get_name/2 uses sub_dict to extract a name field."""
        # nv
        name_var = Var()
        sols = self._capture("get_name", DictTerm({"name": "Alice", "age": 30}), name_var)
        assert sols
        assert sols[0][1] == "Alice"

    def test_is_admin(self):
        # nv
        from clausal.logic.solve import call as lc_call
        admin = DictTerm({"name": "Bob", "role": "admin"})
        user = DictTerm({"name": "Alice", "role": "user"})
        assert list(lc_call("is_admin", admin, module=self.logic_mod))
        assert not list(lc_call("is_admin", user, module=self.logic_mod))

    def test_update_field(self):
        # nv
        new_var = Var()
        old = DictTerm({"x": 1, "y": 2})
        sols = self._capture("update_field", "x", 99, old, new_var)
        assert sols[0][3] == DictTerm({"x": 99, "y": 2})

    def test_dict_member(self):
        # nv
        d = DictTerm({"a": 1, "b": 2})
        k_var, v_var = Var(), Var()
        sols = self._capture("dict_member", k_var, d, v_var)
        pairs = {s[0]: s[2] for s in sols}
        assert pairs == {"a": 1, "b": 2}

    def test_set_common(self):
        # nv
        s1 = SetTerm([1, 2, 3])
        s2 = SetTerm([2, 3, 4])
        inter_var = Var()
        sols = self._capture("set_common", s1, s2, inter_var)
        assert sols[0][2] == SetTerm([2, 3])

    def test_set_member(self):
        # nv
        s = SetTerm(["a", "b", "c"])
        e_var = Var()
        sols = self._capture("set_member", e_var, s)
        elems = {s[0] for s in sols}
        assert elems == {"a", "b", "c"}

    def test_dict_key(self):
        """dict_key/2 uses ``KEY in DICT`` to enumerate keys."""
        # nv
        d = DictTerm({"a": 1, "b": 2, "c": 3})
        k_var = Var()
        sols = self._capture("dict_key", k_var, d)
        keys = {s[0] for s in sols}
        assert keys == {"a", "b", "c"}

    def test_splat_update(self):
        """splat_update/4 uses {**OLD, KEY: VALUE} sugar."""
        # nv
        old = DictTerm({"x": 1, "y": 2})
        new_var = Var()
        sols = self._capture("splat_update", old, "z", 3, new_var)
        assert sols[0][3] == DictTerm({"x": 1, "y": 2, "z": 3})


# ── ``in`` operator with dicts and sets ──────────────────────────────────────


class TestInOperatorDictSet:
    """Test ``KEY in DICT`` and ``(KEY, VALUE) in DICT`` syntax."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        src = tmp_path / "in_dict.clausal"
        src.write_text(
            "# predicates\n"
            "\n"
            "# Enumerate keys\n"
            "enum_keys(KEY, DICT) <- (KEY in DICT)\n"
            "\n"
            "# Enumerate key-value pairs\n"
            "enum_pairs(KEY, VALUE, DICT) <- ((KEY, VALUE) in DICT)\n"
            "\n"
            "# include by key\n"
            'find_value(VALUE, DICT) <- (("x", VALUE) in DICT)\n'
            "\n"
            "# Key not in dict\n"
            "key_absent(KEY, DICT) <- (KEY not in DICT)\n"
            "\n"
            "# Pair not in dict\n"
            "pair_absent(KEY, VALUE, DICT) <- ((KEY, VALUE) not in DICT)\n"
        )
        mod = _load_module("in_dict", str(src))
        self.logic_mod = mod.__dict__["$module"]

    def _capture(self, pred_name, *args):
        from clausal.logic.solve import call as lc_call
        var_positions = {i: a for i, a in enumerate(args) if isinstance(a, Var)}
        results = []
        for _ in lc_call(pred_name, *args, module=self.logic_mod):
            results.append({i: deref(v) for i, v in var_positions.items()})
        return results

    def test_key_in_dict_enumerates_keys(self):
        # nv
        d = DictTerm({"a": 1, "b": 2, "c": 3})
        k = Var()
        sols = self._capture("enum_keys", k, d)
        keys = {s[0] for s in sols}
        assert keys == {"a", "b", "c"}

    def test_key_in_dict_filters(self):
        # nv
        d = DictTerm({"a": 1, "b": 2})
        sols = self._capture("enum_keys", "a", d)
        assert len(sols) == 1

    def test_key_in_dict_empty(self):
        # nv
        d = DictTerm({})
        sols = self._capture("enum_keys", Var(), d)
        assert len(sols) == 0

    def test_pair_in_dict_enumerates_pairs(self):
        # nv
        d = DictTerm({"x": 10, "y": 20})
        k, v = Var(), Var()
        sols = self._capture("enum_pairs", k, v, d)
        pairs = {s[0]: s[1] for s in sols}
        assert pairs == {"x": 10, "y": 20}

    def test_pair_in_dict_filter_by_key(self):
        # nv
        d = DictTerm({"x": 42, "y": 99})
        v = Var()
        sols = self._capture("find_value", v, d)
        assert len(sols) == 1
        assert sols[0][0] == 42

    def test_pair_in_dict_unifies_value(self):
        # nv
        d = DictTerm({"a": 1, "b": 2})
        k, v = Var(), Var()
        sols = self._capture("enum_pairs", k, v, d)
        assert len(sols) == 2
        for s in sols:
            assert s[0] in ("a", "b")

    def test_pair_in_dict_empty(self):
        # nv
        d = DictTerm({})
        sols = self._capture("enum_pairs", Var(), Var(), d)
        assert len(sols) == 0

    def test_key_not_in_dict(self):
        # nv
        d = DictTerm({"a": 1, "b": 2})
        sols = self._capture("key_absent", "c", d)
        assert len(sols) == 1  # "c" not in dict, so succeeds

    def test_key_not_in_dict_fails(self):
        # nv
        d = DictTerm({"a": 1, "b": 2})
        sols = self._capture("key_absent", "a", d)
        assert len(sols) == 0  # "a" in dict, so fails

    def test_pair_not_in_dict(self):
        # nv
        d = DictTerm({"a": 1, "b": 2})
        sols = self._capture("pair_absent", "c", 99, d)
        assert len(sols) == 1  # ("c", 99) not in dict

    def test_pair_not_in_dict_wrong_value(self):
        # nv
        d = DictTerm({"a": 1, "b": 2})
        sols = self._capture("pair_absent", "a", 99, d)
        assert len(sols) == 1  # ("a", 99) not in dict (value doesn't match)


# ── Symmetric equality: DictTerm/dict and SetTerm/set ─────────────────────────
#
# DictTerm / SetTerm are Clausal's unification-aware wrappers; a
# bidirectional predicate's backward direction or a library call might
# return a plain Python dict / set equivalent. Clausal `==` (structural_eq)
# and `unify` must treat the two representations as equal so fixtures can
# write `TREE is {"a": 1}, REBUILT == TREE` without forcing a ++({...}).


class TestDictTermPlainDictEquality:
    def test_python_eq_dictterm_vs_dict(self):
        # nv
        assert DictTerm({"a": 1, "b": 2}) == {"a": 1, "b": 2}

    def test_python_eq_dict_vs_dictterm(self):
        # nv
        assert {"a": 1, "b": 2} == DictTerm({"a": 1, "b": 2})

    def test_python_eq_differs_on_keys(self):
        # nv
        assert DictTerm({"a": 1}) != {"b": 1}
        assert {"a": 1} != DictTerm({"b": 1})

    def test_python_eq_differs_on_values(self):
        # nv
        assert DictTerm({"a": 1}) != {"a": 2}
        assert {"a": 1} != DictTerm({"a": 2})

    def test_structural_eq_dictterm_vs_dict(self):
        # nv
        from clausal.logic.constraints import structural_eq
        assert structural_eq(DictTerm({"a": 1, "b": 2}), {"a": 1, "b": 2})
        assert structural_eq({"a": 1, "b": 2}, DictTerm({"a": 1, "b": 2}))

    def test_structural_eq_nested(self):
        # nv
        from clausal.logic.constraints import structural_eq
        dt = DictTerm({"a": [1, 2], "b": 3})
        d = {"a": [1, 2], "b": 3}
        assert structural_eq(dt, d)
        assert structural_eq(d, dt)

    def test_unify_dictterm_and_dict(self):
        # nv
        t = Trail()
        assert unify(DictTerm({"a": 1, "b": 2}), {"a": 1, "b": 2}, t)

    def test_unify_dict_and_dictterm(self):
        # nv
        t = Trail()
        assert unify({"a": 1, "b": 2}, DictTerm({"a": 1, "b": 2}), t)

    def test_unify_dictterm_with_var_value_vs_dict(self):
        # nv — Vars inside DictTerm values unify with corresponding dict values
        t = Trail()
        v = Var()
        assert unify(DictTerm({"a": v, "b": 2}), {"a": 42, "b": 2}, t)
        assert deref(v) == 42


class TestSetTermPlainSetEquality:
    def test_python_eq_setterm_vs_set(self):
        # nv
        assert SetTerm([1, 2, 3]) == {1, 2, 3}

    def test_python_eq_set_vs_setterm(self):
        # nv
        assert {1, 2, 3} == SetTerm([1, 2, 3])

    def test_python_eq_setterm_vs_frozenset(self):
        # nv
        assert SetTerm([1, 2, 3]) == frozenset([1, 2, 3])
        assert frozenset([1, 2, 3]) == SetTerm([1, 2, 3])

    def test_python_eq_differs(self):
        # nv
        assert SetTerm([1, 2]) != {1, 2, 3}
        assert {1, 2, 3} != SetTerm([1, 2])

    def test_structural_eq_setterm_vs_set(self):
        # nv
        from clausal.logic.constraints import structural_eq
        assert structural_eq(SetTerm([1, 2, 3]), {1, 2, 3})
        assert structural_eq({1, 2, 3}, SetTerm([1, 2, 3]))

    def test_structural_eq_setterm_vs_frozenset(self):
        # nv
        from clausal.logic.constraints import structural_eq
        assert structural_eq(SetTerm([1, 2, 3]), frozenset([1, 2, 3]))
        assert structural_eq(frozenset([1, 2, 3]), SetTerm([1, 2, 3]))

    def test_unify_setterm_and_set(self):
        # nv
        t = Trail()
        assert unify(SetTerm([1, 2, 3]), {1, 2, 3}, t)

    def test_unify_set_and_setterm(self):
        # nv
        t = Trail()
        assert unify({1, 2, 3}, SetTerm([1, 2, 3]), t)
