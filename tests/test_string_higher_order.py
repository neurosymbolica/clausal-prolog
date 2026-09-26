"""Tests for Phase 5: higher-order predicates accept strings."""

import pytest
from clausal.logic.atoms import char_atom, mint
from clausal.logic.cells import chars
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
            '-double_quotes(atom)\n-implicit_atoms\n'  # upper is a bare atom arg to char_type/2, not declared
            '-module(ho_str, [is_vowel(_c), is_upper(_c),'
            ' char_to_code(_c, _code), concat_chars(_c, _acc, _out)])\n'
            'is_vowel(_c) <- in_(_c, ["a", "e", "i", "o", "u"])\n'
            'is_upper(_c) <- (char_type(_c, upper))\n'
            'char_to_code(_c, _code) <- char_code(_c, _code)\n'
            'concat_chars(_c, _acc, _out) <- atom_concat(_acc, _c, _out)\n'
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


# ── include/3 ────────────────────────────────────────────────────────────────


class TestFilterString:
    def test_filter_vowels(self, mod):
        # nv
        R = Var()
        r = _collect(R, "include", mod.module_dict["is_vowel"], chars("hello"), R, module=mod)
        assert r == [chars("eo")]

    def test_filter_empty(self, mod):
        # nv
        R = Var()
        r = _collect(R, "include", mod.module_dict["is_vowel"], chars(""), R, module=mod)
        assert r == [chars("")]

    def test_filter_none_match(self, mod):
        # nv
        R = Var()
        r = _collect(R, "include", mod.module_dict["is_vowel"], chars("xyz"), R, module=mod)
        assert r == [chars("")]

    def test_filter_all_match(self, mod):
        # nv
        R = Var()
        r = _collect(R, "include", mod.module_dict["is_vowel"], chars("aeiou"), R, module=mod)
        assert r == [chars("aeiou")]

    def test_filter_list_still_works(self, mod):
        """include on a regular list is unchanged."""
        # nv
        R = Var()
        r = _collect(R, "include", mod.module_dict["is_vowel"],
                     [char_atom(c) for c in "abce"], R, module=mod)
        assert r == [[char_atom("a"), char_atom("e")]]


# ── exclude/3 ───────────────────────────────────────────────────────────────


class TestExcludeString:
    def test_exclude_vowels(self, mod):
        # nv
        R = Var()
        r = _collect(R, "exclude", mod.module_dict["is_vowel"], chars("hello"), R, module=mod)
        assert r == [chars("hll")]


# ── maplist/2 ───────────────────────────────────────────────────────────────


class TestMapListString:
    def test_maplist2_all_succeed(self, mod):
        # nv
        assert _first("maplist", mod.module_dict["is_vowel"], chars("aeiou"), module=mod)

    def test_maplist2_some_fail(self, mod):
        # nv
        assert not _first("maplist", mod.module_dict["is_vowel"], chars("hello"), module=mod)

    def test_maplist2_empty(self, mod):
        # nv
        assert _first("maplist", mod.module_dict["is_vowel"], chars(""), module=mod)


# ── maplist/3 ───────────────────────────────────────────────────────────────


class TestMapList3String:
    def test_maplist3_char_to_code(self, mod):
        # nv
        R = Var()
        r = _collect(R, "maplist", mod.module_dict["char_to_code"], chars("abc"), R, module=mod)
        assert r == [[97, 98, 99]]


# ── foldl/4 ──────────────────────────────────────────────────────────────


class TestFoldLeftString:
    def test_foldleft_concat_chars(self, mod):
        """Fold over string chars, concatenating into accumulator."""
        # nv
        R = Var()
        # ``atom_concat/3`` takes ATOMS (spec §6.6), so the seed is the
        # empty ATOM and the answer is the atom ("abc",).
        r = _collect(R, "foldl", mod.module_dict["concat_chars"],
                     chars("abc"), mint(""), R, module=mod)
        assert r == [mint("abc")]


# ── partition/4 ─────────────────────────────────────────────────────────────


class TestPartitionString:
    def test_partition_vowels(self, mod):
        # nv — the INPUT is a string; both halves come back as strings
        # (a list of char atoms IS the string it denotes, spec §6.2).
        Y, N = Var(), Var()
        results = []
        for _ in call("partition", mod.module_dict["is_vowel"], chars("hello"), Y, N, module=mod):
            results.append((deref(Y), deref(N)))
        assert results == [(chars("eo"), chars("hll"))]


# ── take_while/3 ─────────────────────────────────────────────────────────────


class TestTakeWhileString:
    def test_take_while_vowels(self, mod):
        # nv
        R = Var()
        r = _collect(R, "take_while", mod.module_dict["is_vowel"], chars("aeibc"), R, module=mod)
        assert r == [chars("aei")]

    def test_take_while_none(self, mod):
        # nv
        R = Var()
        r = _collect(R, "take_while", mod.module_dict["is_vowel"], chars("xyz"), R, module=mod)
        assert r == [chars("")]


# ── drop_while/3 ─────────────────────────────────────────────────────────────


class TestDropWhileString:
    def test_drop_while_vowels(self, mod):
        # nv
        R = Var()
        r = _collect(R, "drop_while", mod.module_dict["is_vowel"], chars("aeibc"), R, module=mod)
        assert r == [chars("bc")]


# ── span/4 ──────────────────────────────────────────────────────────────────


class TestSpanString:
    def test_span_vowels(self, mod):
        # nv — the INPUT is a string; both halves come back as strings
        # (a list of char atoms IS the string it denotes, spec §6.2).
        Y, N = Var(), Var()
        results = []
        for _ in call("span", mod.module_dict["is_vowel"], chars("aeibc"), Y, N, module=mod):
            results.append((deref(Y), deref(N)))
        assert results == [(chars("aei"), chars("bc"))]
