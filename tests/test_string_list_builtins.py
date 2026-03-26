"""Tests for Phase 4: polymorphic list builtins accept strings.

All list builtins now accept strings as character sequences. When all
sequence inputs are strings and the result is a valid char sequence,
the result is returned as a string.
"""

import pytest
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
from clausal.import_hook import _load_module
import tempfile
import os


@pytest.fixture(scope="module")
def mod():
    """Minimal module for calling builtins."""
    with tempfile.NamedTemporaryFile(suffix=".clausal", mode="w", delete=False) as f:
        f.write("-module(tmod, [])\n")
        f.flush()
        m = _load_module("tmod_phase4", f.name).__dict__["$module"]
    yield m
    os.unlink(f.name)


def _first(functor, *args, module):
    """Return the first result for a builtin call, or None."""
    for _ in call(functor, *args, module=module):
        return True
    return False


def _collect(var, functor, *args, module):
    """Collect all bindings of *var* across backtracking."""
    results = []
    for _ in call(functor, *args, module=module):
        results.append(deref(var))
    return results


# ── In/2 ────────────────────────────────────────────────────────────────────


class TestInString:
    def test_enumerate_chars(self, mod):
        V = Var()
        assert _collect(V, "In", V, "abc", module=mod) == ["a", "b", "c"]

    def test_member_check(self, mod):
        assert _first("In", "b", "abc", module=mod)

    def test_member_miss(self, mod):
        assert not _first("In", "z", "abc", module=mod)

    def test_empty_string(self, mod):
        V = Var()
        assert _collect(V, "In", V, "", module=mod) == []

    def test_list_still_works(self, mod):
        V = Var()
        assert _collect(V, "In", V, [1, 2], module=mod) == [1, 2]


class TestInCheckString:
    def test_memberchk_hit(self, mod):
        assert _first("InCheck", "l", "hello", module=mod)

    def test_memberchk_miss(self, mod):
        assert not _first("InCheck", "z", "hello", module=mod)


# ── Append/3 ────────────────────────────────────────────────────────────────


class TestAppendString:
    def test_concat_two_strings(self, mod):
        X = Var()
        r = _collect(X, "Append", "hel", "lo", X, module=mod)
        assert r == ["hello"]

    def test_prefix_match(self, mod):
        X = Var()
        r = _collect(X, "Append", "hel", X, "hello", module=mod)
        assert r == ["lo"]

    def test_suffix_match(self, mod):
        X = Var()
        r = _collect(X, "Append", X, "lo", "hello", module=mod)
        assert r == ["hel"]

    def test_enumerate_splits(self, mod):
        X, Y = Var(), Var()
        pairs = []
        for _ in call("Append", X, Y, "abc", module=mod):
            pairs.append((deref(X), deref(Y)))
        assert pairs == [
            ("", "abc"),
            ("a", "bc"),
            ("ab", "c"),
            ("abc", ""),
        ]

    def test_concat_string_with_list(self, mod):
        """Mixed types: string + list → list result."""
        X = Var()
        r = _collect(X, "Append", "ab", [1, 2], X, module=mod)
        assert r == [["a", "b", 1, 2]]

    def test_empty_strings(self, mod):
        X = Var()
        r = _collect(X, "Append", "", "", X, module=mod)
        assert r == [""]

    def test_list_still_works(self, mod):
        X = Var()
        r = _collect(X, "Append", [1, 2], [3], X, module=mod)
        assert r == [[1, 2, 3]]


# ── Length/2 ────────────────────────────────────────────────────────────────


class TestLengthString:
    def test_length(self, mod):
        X = Var()
        assert _collect(X, "Length", "hello", X, module=mod) == [5]

    def test_empty(self, mod):
        X = Var()
        assert _collect(X, "Length", "", X, module=mod) == [0]


# ── Reverse/2 ──────────────────────────────────────────────────────────────


class TestReverseString:
    def test_reverse(self, mod):
        X = Var()
        assert _collect(X, "Reverse", "hello", X, module=mod) == ["olleh"]

    def test_reverse_empty(self, mod):
        X = Var()
        assert _collect(X, "Reverse", "", X, module=mod) == [""]

    def test_reverse_single(self, mod):
        X = Var()
        assert _collect(X, "Reverse", "a", X, module=mod) == ["a"]


# ── Last/2 ──────────────────────────────────────────────────────────────────


class TestLastString:
    def test_last_char(self, mod):
        X = Var()
        assert _collect(X, "Last", "hello", X, module=mod) == ["o"]

    def test_empty_fails(self, mod):
        X = Var()
        assert _collect(X, "Last", "", X, module=mod) == []


# ── GetItem/3 ──────────────────────────────────────────────────────────────


class TestGetItemString:
    def test_index(self, mod):
        X = Var()
        assert _collect(X, "GetItem", 1, "hello", X, module=mod) == ["e"]

    def test_enumerate(self, mod):
        N, E = Var(), Var()
        pairs = []
        for _ in call("GetItem", N, "ab", E, module=mod):
            pairs.append((deref(N), deref(E)))
        assert pairs == [(0, "a"), (1, "b")]


# ── Take/3, Drop/3, SplitAt/4 ─────────────────────────────────────────────


class TestTakeDropSplitAt:
    def test_take(self, mod):
        X = Var()
        assert _collect(X, "Take", 3, "hello", X, module=mod) == ["hel"]

    def test_drop(self, mod):
        X = Var()
        assert _collect(X, "Drop", 3, "hello", X, module=mod) == ["lo"]

    def test_split_at(self, mod):
        L, R = Var(), Var()
        for _ in call("SplitAt", 3, "hello", L, R, module=mod):
            assert deref(L) == "hel"
            assert deref(R) == "lo"

    def test_take_zero(self, mod):
        X = Var()
        assert _collect(X, "Take", 0, "hello", X, module=mod) == [""]

    def test_drop_all(self, mod):
        X = Var()
        assert _collect(X, "Drop", 5, "hello", X, module=mod) == [""]


# ── MergeSort/2, Sort/2 ───────────────────────────────────────────────────


class TestSortString:
    def test_msort(self, mod):
        X = Var()
        r = _collect(X, "MergeSort", "cba", X, module=mod)
        assert r == ["abc"]

    def test_msort_duplicates(self, mod):
        X = Var()
        r = _collect(X, "MergeSort", "abba", X, module=mod)
        assert r == ["aabb"]

    def test_sort_dedup(self, mod):
        X = Var()
        r = _collect(X, "Sort", "abba", X, module=mod)
        assert r == ["ab"]


# ── ToSet/2 ────────────────────────────────────────────────────────────────


class TestToSetString:
    def test_to_set(self, mod):
        X = Var()
        r = _collect(X, "ToSet", "abba", X, module=mod)
        assert r == ["ab"]


# ── Select/3 ──────────────────────────────────────────────────────────────


class TestSelectString:
    def test_select(self, mod):
        E, R = Var(), Var()
        pairs = []
        for _ in call("Select", E, "abc", R, module=mod):
            pairs.append((deref(E), deref(R)))
        assert pairs == [
            ("a", "bc"),
            ("b", "ac"),
            ("c", "ab"),
        ]


# ── Subtract/3, Intersection/3, Union/3 ───────────────────────────────────


class TestSetOpsString:
    def test_subtract(self, mod):
        X = Var()
        r = _collect(X, "Subtract", "abcd", "bd", X, module=mod)
        assert r == ["ac"]

    def test_intersection(self, mod):
        X = Var()
        r = _collect(X, "Intersection", "abcd", "bce", X, module=mod)
        assert r == ["bc"]

    def test_union(self, mod):
        X = Var()
        r = _collect(X, "Union", "abc", "cde", X, module=mod)
        assert r == ["abcde"]


# ── MaxList/2, MinList/2 ──────────────────────────────────────────────────


class TestMaxMinString:
    def test_max(self, mod):
        X = Var()
        r = _collect(X, "MaxList", "hello", X, module=mod)
        assert r == ["o"]

    def test_min(self, mod):
        X = Var()
        r = _collect(X, "MinList", "hello", X, module=mod)
        assert r == ["e"]


# ── Permutation/2 ─────────────────────────────────────────────────────────


class TestPermutationString:
    def test_permutations(self, mod):
        P = Var()
        results = _collect(P, "Permutation", "ab", P, module=mod)
        assert set(results) == {"ab", "ba"}
        assert all(isinstance(r, str) for r in results)


# ── Zip/3 ──────────────────────────────────────────────────────────────────


class TestZipString:
    def test_zip_strings(self, mod):
        X = Var()
        r = _collect(X, "Zip", "ab", "12", X, module=mod)
        assert r == [[["a", "1"], ["b", "2"]]]

    def test_zip_string_list(self, mod):
        X = Var()
        r = _collect(X, "Zip", "ab", [1, 2], X, module=mod)
        assert r == [[["a", 1], ["b", 2]]]


# ── SplitWith/3 ───────────────────────────────────────────────────────────


class TestSplitWithString:
    def test_split_by_comma(self, mod):
        X = Var()
        r = _collect(X, "SplitWith", ",", "a,b,c", X, module=mod)
        assert r == [["a", "b", "c"]]

    def test_split_no_sep(self, mod):
        X = Var()
        r = _collect(X, "SplitWith", ",", "abc", X, module=mod)
        assert r == [["abc"]]


# ── SameLength/2 ──────────────────────────────────────────────────────────


class TestSameLengthString:
    def test_same_length(self, mod):
        assert _first("SameLength", "abc", "xyz", module=mod)

    def test_different_length(self, mod):
        assert not _first("SameLength", "ab", "xyz", module=mod)

    def test_string_list_same_length(self, mod):
        assert _first("SameLength", "abc", [1, 2, 3], module=mod)


# ── IsChars/1 ─────────────────────────────────────────────────────────────


class TestIsChars:
    def test_string(self, mod):
        assert _first("IsChars", "hello", module=mod)

    def test_list(self, mod):
        assert _first("IsChars", [1, 2], module=mod)

    def test_int_fails(self, mod):
        assert not _first("IsChars", 42, module=mod)

    def test_is_list_string_still_fails(self, mod):
        """IsList('hello') still fails — exact type test."""
        assert not _first("IsList", "hello", module=mod)
