"""Plain `dict`/`set` inputs to the KEY-first builtin families.

The trap shape (todo/dictterm-only-builtins-sweep.md): one spelling of an
operation accepts `DictTerm | dict` (subscript, `DictTerm.__unify__`,
structural `==`, the profile API `get/3` family), while a sibling spelling
accepts only `DictTerm` and fails SOFTLY — so a Python caller passing
`{'k': v}` gets a partly working profile and a silent wrong answer instead of
an error.  Same for `SetTerm` vs plain `set`.

Contract pinned here: every `dict_*` / `set_*` builtin accepts the plain type
wherever it accepts the Term type, mixed flavors included.  Outputs keep
binding the Term flavor (`DictTerm`/`SetTerm`), which unifies with either.
The `(K, V) in D` pair mode iterates ITEMS for a plain dict, not keys.
"""

from __future__ import annotations

import pytest

from clausal.logic.database import Module
from clausal.logic.solve import solve
from clausal.logic.variables import Var, Trail, deref
from clausal.terms import Call, LoadName, DictTerm, SetTerm
from clausal.import_hook import _load_module
from tests._suffix import SEAM


def _goal(name, *args):
    return Call(func=LoadName(name=name), args=list(args), kwargs=[])


def _succeeds(name, *args):
    return bool(list(solve(_goal(name, *args), Module("test"))))


def _sols(name, *args):
    var_positions = {i: a for i, a in enumerate(args) if isinstance(a, Var)}
    t = Trail()
    results = []
    for _ in solve(_goal(name, *args), Module("test"), t):
        results.append({i: deref(v) for i, v in var_positions.items()})
    return results


D = {"a": 1, "b": 2}


class TestPlainDictInputs:
    def test_is_dict(self):
        assert _succeeds("is_dict", dict(D))
        assert not _succeeds("is_dict", [1, 2])

    def test_dict_size(self):
        assert _sols("dict_size", dict(D), Var()) == [{1: 2}]

    def test_dict_keys(self):
        assert _sols("dict_keys", dict(D), Var()) == [{1: ["a", "b"]}]

    def test_dict_values(self):
        assert _sols("dict_values", dict(D), Var()) == [{1: [1, 2]}]

    def test_dict_pairs_decompose(self):
        assert _sols("dict_pairs", dict(D), Var()) == [{1: [("-", "a", 1), ("-", "b", 2)]}]

    def test_dict_get(self):
        assert _sols("dict_get", "a", dict(D), Var()) == [{2: 1}]

    def test_dict_put_leaves_the_plain_dict_alone(self):
        original = dict(D)
        [sol] = _sols("dict_put", "c", 3, original, Var())
        assert sol[3] == DictTerm({"a": 1, "b": 2, "c": 3})
        assert original == D, "dict_put must not mutate the caller's dict"

    def test_dict_put_pairs(self):
        [sol] = _sols("dict_put_pairs", [("-", "c", 3)], dict(D), Var())
        assert sol[2] == DictTerm({"a": 1, "b": 2, "c": 3})

    def test_dict_remove(self):
        [sol] = _sols("dict_remove", "a", dict(D), Var())
        assert sol[2] == DictTerm({"b": 2})

    @pytest.mark.parametrize("d1,d2", [
        (dict(D), {"c": 3}),
        (DictTerm(dict(D)), {"c": 3}),
        (dict(D), DictTerm({"c": 3})),
    ])
    def test_dict_merge_mixed_flavors(self, d1, d2):
        [sol] = _sols("dict_merge", d1, d2, Var())
        assert sol[2] == DictTerm({"a": 1, "b": 2, "c": 3})

    def test_gen_dict(self):
        k, v = Var(), Var()
        sols = _sols("gen_dict", k, dict(D), v)
        assert {(s[0], s[2]) for s in sols} == {("a", 1), ("b", 2)}

    @pytest.mark.parametrize("pattern,full", [
        ({"a": 1}, DictTerm(dict(D))),
        (DictTerm({"a": 1}), dict(D)),
        ({"a": 1}, dict(D)),
    ])
    def test_sub_dict_mixed_flavors(self, pattern, full):
        assert _succeeds("sub_dict", pattern, full)


class TestPlainDictPairModeIn:
    def test_pair_mode_in_iterates_items_not_keys(self, tmp_path):
        src = tmp_path / f"pmi{SEAM}"
        src.write_text(
            "pairs_of(D, P) <- (findall([K, V], ((K, V) in D), P))\n"
        )
        mod = _load_module("pmi", str(src))
        p = Var()
        for _ in solve(("pairs_of", dict(D), p), mod):
            assert sorted(deref(p)) == [["a", 1], ["b", 2]]
            break
        else:
            pytest.fail("pair-mode `in` yielded no solutions over a plain dict")

    def test_key_mode_in_still_iterates_keys(self, tmp_path):
        src = tmp_path / f"kmi{SEAM}"
        src.write_text("keys_of(D, P) <- (findall(K, (K in D), P))\n")
        mod = _load_module("kmi", str(src))
        p = Var()
        for _ in solve(("keys_of", dict(D), p), mod):
            assert sorted(deref(p)) == ["a", "b"]
            break
        else:
            pytest.fail("key-mode `in` yielded no solutions over a plain dict")


S = {1, 2, 3}


class TestPlainSetInputs:
    def test_is_set(self):
        assert _succeeds("is_set", set(S))
        assert not _succeeds("is_set", [1, 2])

    def test_set_size(self):
        assert _sols("set_size", set(S), Var()) == [{1: 3}]

    def test_set_list_decompose(self):
        [sol] = _sols("set_list", set(S), Var())
        assert sorted(sol[1]) == [1, 2, 3]

    @pytest.mark.parametrize("s1,s2", [
        (set(S), {3, 4}),
        (SetTerm(set(S)), {3, 4}),
        (set(S), SetTerm({3, 4})),
    ])
    def test_set_union_mixed_flavors(self, s1, s2):
        [sol] = _sols("set_union", s1, s2, Var())
        assert sol[2] == SetTerm({1, 2, 3, 4})

    def test_set_intersection(self):
        [sol] = _sols("set_intersection", set(S), {2, 3, 4}, Var())
        assert sol[2] == SetTerm({2, 3})

    def test_set_subtract(self):
        [sol] = _sols("set_subtract", set(S), {3}, Var())
        assert sol[2] == SetTerm({1, 2})

    def test_set_sym_diff(self):
        [sol] = _sols("set_sym_diff", set(S), {3, 4}, Var())
        assert sol[2] == SetTerm({1, 2, 4})

    def test_set_subset_and_disjoint(self):
        assert _succeeds("set_subset", {1, 2}, set(S))
        assert _succeeds("set_subset", SetTerm({1, 2}), set(S))
        assert _succeeds("set_disjoint", {9}, set(S))
        assert not _succeeds("set_disjoint", {1}, set(S))

    def test_set_add_and_remove(self):
        [sol] = _sols("set_add", 4, set(S), Var())
        assert sol[2] == SetTerm({1, 2, 3, 4})
        [sol] = _sols("set_remove", 1, set(S), Var())
        assert sol[2] == SetTerm({2, 3})

    def test_gen_set(self):
        sols = _sols("gen_set", Var(), set(S))
        assert {s[0] for s in sols} == {1, 2, 3}
