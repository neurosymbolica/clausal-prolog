"""Tests for Phase 5: higher-order predicates accept strings."""

import pytest
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
from clausal.import_hook import _load_module
import tempfile
import os


@pytest.fixture(scope="module")
def mod():
    """Module with character-level predicates for higher-order tests."""
    with tempfile.NamedTemporaryFile(suffix=".clausal", mode="w", delete=False) as f:
        f.write(
            '-module(ho_str, [is_vowel(C_), is_upper(C_),'
            ' char_to_code(C_, Code_), concat_chars(C_, Acc_, Out_)])\n'
            'is_vowel(C_) <- In(C_, ["a", "e", "i", "o", "u"])\n'
            'is_upper(C_) <- (CharType(C_, upper))\n'
            'char_to_code(C_, Code_) <- CharCode(C_, Code_)\n'
            'concat_chars(C_, Acc_, Out_) <- AtomConcat(Acc_, C_, Out_)\n'
        )
        f.flush()
        m = _load_module("ho_str", f.name).__dict__["$module"]
    yield m
    os.unlink(f.name)


def _collect(var, functor, *args, module):
    results = []
    for _ in call(functor, *args, module=module):
        results.append(deref(var))
    return results


def _first(functor, *args, module):
    for _ in call(functor, *args, module=module):
        return True
    return False


# ── Filter/3 ────────────────────────────────────────────────────────────────


class TestFilterString:
    def test_filter_vowels(self, mod):
        R = Var()
        r = _collect(R, "Filter", mod.module_dict["is_vowel"], "hello", R, module=mod)
        assert r == ["eo"]

    def test_filter_empty(self, mod):
        R = Var()
        r = _collect(R, "Filter", mod.module_dict["is_vowel"], "", R, module=mod)
        assert r == [""]

    def test_filter_none_match(self, mod):
        R = Var()
        r = _collect(R, "Filter", mod.module_dict["is_vowel"], "xyz", R, module=mod)
        assert r == [""]

    def test_filter_all_match(self, mod):
        R = Var()
        r = _collect(R, "Filter", mod.module_dict["is_vowel"], "aeiou", R, module=mod)
        assert r == ["aeiou"]

    def test_filter_list_still_works(self, mod):
        """Filter on a regular list is unchanged."""
        R = Var()
        r = _collect(R, "Filter", mod.module_dict["is_vowel"],
                     ["a", "b", "c", "e"], R, module=mod)
        assert r == [["a", "e"]]


# ── Exclude/3 ───────────────────────────────────────────────────────────────


class TestExcludeString:
    def test_exclude_vowels(self, mod):
        R = Var()
        r = _collect(R, "Exclude", mod.module_dict["is_vowel"], "hello", R, module=mod)
        assert r == ["hll"]


# ── MapList/2 ───────────────────────────────────────────────────────────────


class TestMapListString:
    def test_maplist2_all_succeed(self, mod):
        assert _first("MapList", mod.module_dict["is_vowel"], "aeiou", module=mod)

    def test_maplist2_some_fail(self, mod):
        assert not _first("MapList", mod.module_dict["is_vowel"], "hello", module=mod)

    def test_maplist2_empty(self, mod):
        assert _first("MapList", mod.module_dict["is_vowel"], "", module=mod)


# ── MapList/3 ───────────────────────────────────────────────────────────────


class TestMapList3String:
    def test_maplist3_char_to_code(self, mod):
        R = Var()
        r = _collect(R, "MapList", mod.module_dict["char_to_code"], "abc", R, module=mod)
        assert r == [[97, 98, 99]]


# ── FoldLeft/4 ──────────────────────────────────────────────────────────────


class TestFoldLeftString:
    def test_foldleft_concat_chars(self, mod):
        """Fold over string chars, concatenating into accumulator."""
        R = Var()
        r = _collect(R, "FoldLeft", mod.module_dict["concat_chars"],
                     "abc", "", R, module=mod)
        assert r == ["abc"]


# ── Partition/4 ─────────────────────────────────────────────────────────────


class TestPartitionString:
    def test_partition_vowels(self, mod):
        Y, N = Var(), Var()
        for _ in call("Partition", mod.module_dict["is_vowel"], "hello", Y, N, module=mod):
            assert deref(Y) == "eo"
            assert deref(N) == "hll"


# ── TakeWhile/3 ─────────────────────────────────────────────────────────────


class TestTakeWhileString:
    def test_take_while_vowels(self, mod):
        R = Var()
        r = _collect(R, "TakeWhile", mod.module_dict["is_vowel"], "aeibc", R, module=mod)
        assert r == ["aei"]

    def test_take_while_none(self, mod):
        R = Var()
        r = _collect(R, "TakeWhile", mod.module_dict["is_vowel"], "xyz", R, module=mod)
        assert r == [""]


# ── DropWhile/3 ─────────────────────────────────────────────────────────────


class TestDropWhileString:
    def test_drop_while_vowels(self, mod):
        R = Var()
        r = _collect(R, "DropWhile", mod.module_dict["is_vowel"], "aeibc", R, module=mod)
        assert r == ["bc"]


# ── Span/4 ──────────────────────────────────────────────────────────────────


class TestSpanString:
    def test_span_vowels(self, mod):
        Y, N = Var(), Var()
        for _ in call("Span", mod.module_dict["is_vowel"], "aeibc", Y, N, module=mod):
            assert deref(Y) == "aei"
            assert deref(N) == "bc"
