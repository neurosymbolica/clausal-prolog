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
from clausal.logic.atoms import is_atom, mint, spelling

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
        sols = self._capture(
            "get_name",
            DictTerm({mint("name"): "Alice", mint("age"): 30}),
            name_var,
        )
        assert sols
        assert sols[0][1] == "Alice"

    def test_is_admin(self):
        # nv
        from clausal.logic.solve import call as lc_call
        admin = DictTerm({mint("name"): "Bob", mint("role"): mint("admin")})
        user = DictTerm({mint("name"): "Alice", mint("role"): mint("user")})
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
        d = DictTerm({mint("x"): 42, mint("y"): 99})
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

    # ── the nil key enumerates in its canonical form (fix round 5, item 1) ──
    #
    # ``_in_iter`` was the last raw mapping reader: it iterated a caller's
    # PLAIN dict without folding, so ``K in {"": 1}`` yielded the key ``""``
    # while ``gen_dict/3`` and ``dict_keys/2`` over the same term yield
    # ``()``.  One term, two enumerations.

    def test_key_in_a_plain_dict_yields_the_canonical_nil_key(self):
        # nv
        d = {"": 1, mint("a"): 2}
        sols = self._capture("enum_keys", Var(), d)
        assert {s[0] for s in sols} == {(), mint("a")}

    def test_pair_in_a_plain_dict_yields_the_canonical_nil_key(self):
        # nv
        d = {"": 1, mint("a"): 2}
        sols = self._capture("enum_pairs", Var(), Var(), d)
        assert {s[0]: s[1] for s in sols} == {(): 1, mint("a"): 2}

    def test_a_plain_dict_enumerates_exactly_as_the_dictterm_does(self):
        """The whole point: ``in`` must agree with itself across the two
        flavours of one term, and with ``gen_dict/3``/``dict_keys/2``."""
        # nv
        plain, term = {"": 1, mint("a"): 2}, DictTerm({(): 1, mint("a"): 2})
        assert (sorted(map(repr, (s[0] for s in
                                  self._capture("enum_keys", Var(), plain))))
                == sorted(map(repr, (s[0] for s in
                                     self._capture("enum_keys", Var(), term)))))
        # …and with the key-listing builtins, which already folded (as a
        # SET: dict_keys/2 sorts, gen_dict/3 does not, and the order is not
        # what this pins).
        keys = Var()
        assert set(_sols("dict_keys", plain, keys)[0][1]) == {(), mint("a")}
        gen_keys = {s[0] for s in _sols("gen_dict", Var(), plain, Var())}
        assert gen_keys == {(), mint("a")}

    def test_a_nil_key_is_FOUND_by_every_spelling_through_in(self):
        """The membership direction, not just enumeration."""
        # nv
        for d in ({"": 1}, DictTerm({(): 1})):
            for key in ([], "", b"", ()):
                assert len(self._capture("enum_keys", key, d)) == 1, (d, key)
                assert len(self._capture("key_absent", key, d)) == 0, (d, key)

    def test_a_nil_free_plain_dict_is_not_copied(self):
        """``mapping_of``'s two O(1) membership tests, not a copy per
        enumeration: a nil-free dict is iterated IN PLACE.  A live
        ``dict_items`` view tracks its dict; a view over a copy would not."""
        # nv
        from clausal.logic.runtime.body_star_unify import _in_iter
        d = {mint("a"): 1}
        view = _in_iter(d, True)
        d[mint("b")] = 2
        assert dict(view) == {mint("a"): 1, mint("b"): 2}
        assert list(_in_iter(d, False)) == [mint("a"), mint("b")]


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


# ── Profile API accepts plain Python dicts ─────────────────────────────────────
#
# The strict read `V is P[K]` (_subscript) accepts DictTerm AND plain dict; the
# soft profile API (get/3, get/4, tri_get/3, delete/3) accepted only DictTerm
# and failed SILENTLY on a plain dict — so a Python caller passing {'k': v} got
# a partly working profile: subscript reads succeeded while every get/3 guard
# failed, flipping guarded clauses to their not-guarded fallbacks. See
# todo/done/get3-rejects-a-plain-dict-that-subscript-accepts.md.


class TestProfileAPIPlainDict:
    def test_get3_plain_dict_present(self):
        # nv
        assert _sols("get", {"k": 7}, "k", Var()) == [{2: 7}]

    def test_get3_plain_dict_absent_fails(self):
        # nv
        assert _fails("get", {"k": 7}, "missing", Var())

    def test_get3_matches_dictterm_behavior(self):
        # nv
        assert (_sols("get", {"k": 7}, "k", Var())
                == _sols("get", DictTerm({"k": 7}), "k", Var()))

    def test_get3_nondict_still_fails_softly(self):
        # nv
        assert _fails("get", "not_a_dict", "k", Var())

    def test_get4_plain_dict_present(self):
        # nv
        assert _sols("get", {"k": 7}, "k", Var(), 0) == [{2: 7}]

    def test_get4_plain_dict_default(self):
        # nv
        assert _sols("get", {"k": 7}, "missing", Var(), 0) == [{2: 0}]

    def test_tri_get_plain_dict_present(self):
        # nv
        assert _sols("tri_get", {"k": 7}, "k", Var()) == [{2: 7}]

    def test_tri_get_plain_dict_absent_undefined(self):
        # nv
        from clausal.terms import Undefined
        assert _sols("tri_get", {"k": 7}, "missing", Var()) == [{2: Undefined}]

    def test_delete_plain_dict_removes_key(self):
        # nv
        sols = _sols("delete", {"k": 7, "j": 8}, "k", Var())
        assert sols == [{2: DictTerm({"j": 8})}]

    # symmetry: plain dict and DictTerm behave identically for the whole family

    def test_get4_matches_dictterm_behavior(self):
        # nv
        for key in ("k", "missing"):
            assert (_sols("get", {"k": 7}, key, Var(), 0)
                    == _sols("get", DictTerm({"k": 7}), key, Var(), 0))

    def test_tri_get_matches_dictterm_behavior(self):
        # nv
        for key in ("k", "missing"):
            assert (_sols("tri_get", {"k": 7}, key, Var())
                    == _sols("tri_get", DictTerm({"k": 7}), key, Var()))

    def test_delete_matches_dictterm_behavior(self):
        # nv
        assert (_sols("delete", {"k": 7, "j": 8}, "k", Var())
                == _sols("delete", DictTerm({"k": 7, "j": 8}), "k", Var()))

    # error paths: plain dict keeps the family's documented strict/soft splits

    def test_delete_plain_dict_absent_key_throws_existence(self):
        # nv
        from clausal.logic.exceptions import LogicException
        with pytest.raises(LogicException, match="existence_error"):
            _sols("delete", {"k": 7}, "missing", Var())

    def test_delete_nondict_still_throws_type_error(self):
        # nv
        from clausal.logic.exceptions import LogicException
        with pytest.raises(LogicException, match="type_error"):
            _sols("delete", "not_a_dict", "k", Var())

    def test_get4_nondict_still_fails_softly(self):
        # nv
        assert _fails("get", "not_a_dict", "k", Var(), 0)

    def test_tri_get_nondict_still_fails_softly(self):
        # nv
        assert _fails("tri_get", "not_a_dict", "k", Var())


# ── in_/2 and in_check/2 accept dicts and sets like the ``in`` operator ────────
#
# The ``in`` OPERATOR iterates DictTerm/dict keys (pair mode: items) and
# SetTerm/set elements via _in_iter's iter() fallback; the PREDICATE spelling
# in_/2 went through the list-only _as_items path and failed SILENTLY on all
# of them, so the two spellings disagreed on the same collection. See
# todo/done/in-predicate-does-not-accept-a-dict.md.


class TestInPredicateDictSet:
    def test_in_dictterm_key_succeeds(self):
        # nv
        assert _succeeds("in_", "a", DictTerm({"a": 1, "b": 2}))

    def test_in_dictterm_absent_key_fails(self):
        # nv
        assert _fails("in_", "missing", DictTerm({"a": 1}))

    def test_in_dictterm_enumerates_keys_in_operator_order(self):
        # nv
        sols = _sols("in_", Var(), DictTerm({"b": 2, "a": 1, "c": 3}))
        assert [s[0] for s in sols] == ["b", "a", "c"]

    def test_in_dictterm_is_key_not_value(self):
        # nv
        assert _fails("in_", 1, DictTerm({"a": 1}))

    def test_in_plain_dict_key_succeeds(self):
        # nv
        assert _succeeds("in_", "a", {"a": 1, "b": 2})

    def test_in_plain_dict_enumerates_keys(self):
        # nv
        sols = _sols("in_", Var(), {"b": 2, "a": 1})
        assert [s[0] for s in sols] == ["b", "a"]

    def test_in_setterm_element_succeeds(self):
        # nv
        assert _succeeds("in_", 2, SetTerm([1, 2, 3]))

    def test_in_setterm_absent_fails(self):
        # nv
        assert _fails("in_", 9, SetTerm([1, 2, 3]))

    def test_in_plain_set_element_succeeds(self):
        # nv
        assert _succeeds("in_", 2, {1, 2, 3})

    def test_in_check_dictterm_key_succeeds_once(self):
        # nv
        assert _sols("in_check", "a", DictTerm({"a": 1})) == [{}]

    def test_in_check_setterm_element_succeeds(self):
        # nv
        assert _succeeds("in_check", 2, SetTerm([1, 2, 3]))

    def test_in_check_plain_dict_absent_fails(self):
        # nv
        assert _fails("in_check", "missing", {"a": 1})

    def test_in_list_unchanged(self):
        # nv
        assert _succeeds("in_", 2, [1, 2, 3])
        assert _fails("in_", 9, [1, 2, 3])

    # review round (roborev job 7): every widened type gets a present AND an
    # absent case on both predicates

    def test_in_frozenset_element_succeeds(self):
        # nv
        assert _succeeds("in_", 2, frozenset({1, 2, 3}))

    def test_in_frozenset_absent_fails(self):
        # nv
        assert _fails("in_", 9, frozenset({1, 2, 3}))

    def test_in_plain_set_absent_fails(self):
        # nv
        assert _fails("in_", 9, {1, 2, 3})

    def test_in_check_dictterm_absent_fails(self):
        # nv
        assert _fails("in_check", "missing", DictTerm({"a": 1}))

    def test_in_check_setterm_absent_fails(self):
        # nv
        assert _fails("in_check", 9, SetTerm([1, 2, 3]))

    def test_in_check_frozenset_element_succeeds(self):
        # nv
        assert _succeeds("in_check", 2, frozenset({1, 2, 3}))


# ── The nil key across the whole dict family (Task 15 fix round 4) ────────────
#
# Nil is ONE term with several spellings -- ``[]``, ``""``, ``b""``, ``()``
# (and ``'[]'``) -- of which ``()`` is the hashable dict-key form.  Fix round 3
# normalised the LOOKUP key of every key-taking builtin but left four readers
# indexing the mapping directly, so on a PLAIN dict ``{"": 1}`` the lookup key
# folded to ``()`` while the stored key did not: ``get/3`` failed silently,
# ``get/4`` returned the default, ``tri_get/3`` returned ``Undefined`` and
# ``delete/3`` raised ``existence_error(dict_key, [])`` -- while
# ``dict_get/3``, which goes through ``_dict_input``, hit.  The two BULK
# WRITERS had the mirror hole: they stored a raw key.

#: Every spelling of nil, as a caller may write it.
_NIL_SPELLINGS = ([], "", b"", ())


def _nil_dicts():
    """A plain dict and a ``DictTerm``, each holding ONE nil key → 1.

    The plain one is spelled ``""`` deliberately: it has NOT been through
    ``DictTerm.__init__``, so its stored key is un-normalised and any reader
    that indexes it directly with a folded key misses.
    """
    return ({"": 1}, DictTerm({(): 1}))


class TestNilKeyAcrossTheDictFamily:
    def test_get3_reads_a_nil_key_in_every_spelling(self):
        # nv
        for d in _nil_dicts():
            for key in _NIL_SPELLINGS:
                assert _sols("get", d, key, Var()) == [{2: 1}], (d, key)

    def test_get4_reads_a_nil_key_and_not_the_default(self):
        # nv
        for d in _nil_dicts():
            for key in _NIL_SPELLINGS:
                assert _sols("get", d, key, Var(), 99) == [{2: 1}], (d, key)

    def test_tri_get3_reads_a_nil_key_and_not_undefined(self):
        # nv
        for d in _nil_dicts():
            for key in _NIL_SPELLINGS:
                assert _sols("tri_get", d, key, Var()) == [{2: 1}], (d, key)

    def test_delete3_removes_a_nil_key_in_every_spelling(self):
        # nv
        for d in _nil_dicts():
            for key in _NIL_SPELLINGS:
                assert _sols("delete", d, key, Var()) == [{2: DictTerm({})}], (
                    d, key)

    def test_dict_get3_agrees_with_the_whole_family(self):
        """``dict_get/3`` already went through ``_dict_input``; the four above
        must give the SAME answer for the same term."""
        # nv
        for d in _nil_dicts():
            for key in _NIL_SPELLINGS:
                assert _sols("dict_get", key, d, Var()) == [{2: 1}], (d, key)

    def test_a_plain_dict_answers_exactly_as_the_dictterm_does(self):
        # nv
        plain, term = _nil_dicts()
        for key in _NIL_SPELLINGS:
            assert (_sols("get", plain, key, Var())
                    == _sols("get", term, key, Var()))
            assert (_sols("get", plain, key, Var(), 99)
                    == _sols("get", term, key, Var(), 99))
            assert (_sols("tri_get", plain, key, Var())
                    == _sols("tri_get", term, key, Var()))
            assert (_sols("delete", plain, key, Var())
                    == _sols("delete", term, key, Var()))

    def test_an_absent_key_still_takes_each_predicates_own_branch(self):
        """The fold must not turn a MISS into a hit: a dict with no nil key
        keeps ``get/3`` failing, ``get/4`` defaulting, ``tri_get/3``
        ``Undefined`` and ``delete/3`` throwing."""
        # nv
        from clausal.logic.exceptions import LogicException
        from clausal.terms import Undefined
        for d in ({"k": 7}, DictTerm({"k": 7})):
            for key in _NIL_SPELLINGS:
                assert _fails("get", d, key, Var()), (d, key)
                assert _sols("get", d, key, Var(), 99) == [{2: 99}], (d, key)
                assert _sols("tri_get", d, key, Var()) == [{2: Undefined}], (
                    d, key)
                with pytest.raises(LogicException, match="existence_error"):
                    _sols("delete", d, key, Var())

    # ── the two bulk WRITERS store the canonical key ──────────────────────

    def test_dict_pairs2_builds_the_canonical_nil_key(self):
        """``dict_pairs/2``'s Pairs→Dict arm raised ``type_error(hashable, [])``
        for a key the ruling makes legal."""
        # nv
        for key in _NIL_SPELLINGS:
            sols = _sols("dict_pairs", Var(), [[key, 1]])
            assert sols == [{0: DictTerm({(): 1})}], key
            assert list(sols[0][0].keys()) == [()], key

    def test_dict_put_pairs3_stores_the_canonical_nil_key(self):
        """``dict_put_pairs/3`` raised a raw (uncatchable) ``TypeError``."""
        # nv
        for key in _NIL_SPELLINGS:
            sols = _sols("dict_put_pairs", [[key, 1]], DictTerm({}), Var())
            assert sols == [{2: DictTerm({(): 1})}], key
            assert list(sols[0][2].keys()) == [()], key

    def test_a_bulk_written_nil_key_reads_back_in_every_spelling(self):
        """Writer and reader agree: what ``dict_pairs/2`` stores, ``get/3``
        finds under any spelling."""
        # nv
        built = _sols("dict_pairs", Var(), [[b"", 1]])[0][0]
        for key in _NIL_SPELLINGS:
            assert _sols("get", built, key, Var()) == [{2: 1}], key

    def test_a_genuinely_unhashable_key_still_raises_type_error(self):
        """Only NIL folds — a non-empty list key is still
        ``type_error(hashable, …)`` from ``dict_pairs/2`` (A09-F012)."""
        # nv
        from clausal.logic.exceptions import LogicException
        with pytest.raises(LogicException, match="type_error"):
            _sols("dict_pairs", Var(), [[[1, 2], 1]])
